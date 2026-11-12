import { spawn } from "node:child_process"
import { closeSync, fstatSync, mkdirSync, openSync, readSync, statSync } from "node:fs"
import { join } from "node:path"

export type Task = {
  id: string
  sessionID: string
  command: string
  pid: number
  log: string
  startedAt: number
  endedAt?: number
  status: "running" | "exited" | "killed"
  exitCode?: number | null
  signal?: string | null
}

export type ExitReason = "exit" | "timeout" | "killed" | "error" | "reload"
export type NotifyKind = "exit" | "match" | "timeout"

export type TaskEvent =
  | { type: "started"; task: Task }
  | { type: "matched"; taskID: string; line: string }
  | { type: "exited"; task: Task; reason?: ExitReason; detail?: string }
  | { type: "notified"; taskID: string; kind: NotifyKind; ok: boolean; error?: string; at: number }

export type StartInput = { command: string; cwd?: string; watch?: string; timeout?: number }

export const TAIL_BYTES = 8_000
const MATCH_LIMIT = 20
const POLL_CAP = 1 << 20 // per-tick read bound; bursts beyond it are skipped, not buffered

export function tail(path: string, bytes = TAIL_BYTES): string {
  try {
    const size = statSync(path).size
    const text = readFrom(path, Math.max(0, size - bytes)).toString("utf8")
    return size > bytes ? `…(truncated)\n${text}` : text
  } catch {
    return ""
  }
}

/** Read from `start` to EOF without loading the bytes before it. */
function readFrom(path: string, start: number, max = Infinity): Buffer {
  const fd = openSync(path, "r")
  try {
    const len = Math.min(fstatSync(fd).size - start, max)
    if (len <= 0) return Buffer.alloc(0)
    const buf = Buffer.alloc(len)
    const n = readSync(fd, buf, 0, len, start)
    return buf.subarray(0, n)
  } finally {
    closeSync(fd)
  }
}

export function validateWatch(source: string | undefined): RegExp | undefined {
  if (!source) return undefined
  try {
    return new RegExp(source)
  } catch (err) {
    throw new Error(`Invalid watch regex /${source}/: ${(err as Error).message}`)
  }
}

export function createTaskManager(opts: {
  root: string
  cwd: string
  emit: (event: TaskEvent) => void
  graceMs?: number
}) {
  const graceMs = opts.graceMs ?? 5_000
  const tasks = new Map<string, Task>()
  const kills = new Map<string, { reason: ExitReason; escalate?: ReturnType<typeof setTimeout> }>()
  const stops = new Map<string, () => void>()
  let counter = 0
  let closed = false
  mkdirSync(opts.root, { recursive: true })

  const find = (id: string) => {
    const task = tasks.get(id)
    if (!task) throw new Error(`Unknown background task: ${id}`)
    return task
  }

  const signalGroup = (task: Task, signal: NodeJS.Signals) => {
    if (task.pid <= 1) return false // failed spawn leaves pid -1; -(-1) would signal PID 1
    try {
      process.kill(-task.pid, signal)
      return true
    } catch {
      return false
    }
  }

  function kill(id: string, reason: ExitReason = "killed") {
    const task = find(id)
    if (task.status !== "running" || kills.has(id)) return task
    // Status flips only once the process is really gone (see the exit handler).
    const entry: { reason: ExitReason; escalate?: ReturnType<typeof setTimeout> } = { reason }
    kills.set(id, entry)
    signalGroup(task, "SIGTERM")
    entry.escalate = setTimeout(() => signalGroup(task, "SIGKILL"), graceMs)
    return task
  }

  function start(input: StartInput, sessionID: string): Task {
    const re = validateWatch(input.watch) // before spawn: a bad regex must not leave a task running
    const id = `bg${Date.now().toString(36)}${process.pid.toString(36)}${(counter++).toString(36)}`
    const log = join(opts.root, `${id}.log`)
    const fd = openSync(log, "a")
    const child = spawn("/bin/sh", ["-lc", input.command], {
      cwd: input.cwd ?? opts.cwd,
      detached: true,
      stdio: ["ignore", fd, fd],
    })
    closeSync(fd)
    child.unref()
    const task: Task = {
      id,
      sessionID,
      command: input.command,
      pid: child.pid ?? -1,
      log,
      startedAt: Date.now(),
      status: "running",
    }
    tasks.set(id, task)
    const timers: { stop: () => void }[] = []
    const snapshot = (): Task => ({ ...task })

    if (re) {
      let offset = 0
      let partial = ""
      let sent = 0
      const poll = () => {
        let chunk: Buffer
        let size: number
        try {
          size = statSync(log).size
          chunk = readFrom(log, offset, POLL_CAP)
        } catch {
          return
        }
        if (chunk.length === 0) return
        const lines = (partial + chunk.toString("utf8")).split("\n")
        offset += chunk.length
        partial = lines.pop() ?? ""
        if (size > offset) {
          offset = size // burst larger than the cap: drop the rest, matches past MATCH_LIMIT are discarded anyway
          partial = ""
        }
        for (const line of lines) {
          if (closed) return
          const bounded = line.slice(0, 500) // caps regex backtracking input on the server's main loop
          if (sent >= MATCH_LIMIT || !re.test(bounded)) continue
          sent++
          opts.emit({ type: "matched", taskID: id, line: bounded })
        }
      }
      const t = setInterval(poll, 1000)
      timers.push({ stop: () => clearInterval(t) })
      stops.set(id, poll)
    }

    if (input.timeout) {
      const t = setTimeout(() => {
        if (task.status === "running") kill(id, "timeout")
      }, input.timeout * 1000)
      timers.push({ stop: () => clearTimeout(t) })
    }

    const cleanup = () => {
      timers.forEach((t) => t.stop())
      const k = kills.get(id)
      if (k?.escalate) clearTimeout(k.escalate)
      kills.delete(id)
      return k
    }

    child.on("exit", (code, signal) => {
      stops.get(id)?.()
      stops.delete(id)
      const k = cleanup()
      if (closed) return // shutdown() already reported this task
      // "killed" only when a signal really ended it; a clean exit during the grace window is "exited".
      task.endedAt = Date.now()
      task.status = k && signal ? "killed" : "exited"
      task.exitCode = code
      task.signal = signal
      opts.emit({ type: "exited", task: snapshot(), reason: k?.reason ?? "exit" })
    })
    child.on("error", (err) => {
      stops.delete(id)
      cleanup()
      if (closed) return
      task.endedAt = Date.now()
      task.status = "exited"
      task.exitCode = -1
      opts.emit({ type: "exited", task: snapshot(), reason: "error", detail: err.message })
    })

    opts.emit({ type: "started", task: snapshot() })
    return snapshot()
  }

  return {
    start,
    kill,
    get: (id: string) => ({ ...find(id) }),
    list: () => [...tasks.values()].map((t) => ({ ...t })),
    output: (id: string, bytes = TAIL_BYTES) => tail(find(id).log, bytes),
    /** SIGTERM every running task (plugin unload). */
    shutdown() {
      closed = true
      for (const t of tasks.values()) {
        if (t.status !== "running") continue
        // Report first so the cause is visible even though the unloading plugin can no longer deliver.
        t.status = "killed"
        t.endedAt = Date.now()
        opts.emit({ type: "exited", task: { ...t }, reason: "reload", detail: "killed: plugin reload" })
        signalGroup(t, "SIGTERM")
        setTimeout(() => signalGroup(t, "SIGKILL"), graceMs).unref() // survives unload; no-op if already gone
      }
    },
  }
}
