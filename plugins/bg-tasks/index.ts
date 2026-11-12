import { Plugin } from "@opencode/plugin"
import { homedir } from "node:os"
import { basename, join } from "node:path"
import { createMatchBatcher, deliver } from "./notify.ts"
import { BgTasks } from "./rpc.ts"
import { createTaskManager, tail, TAIL_BYTES, type Task, type TaskEvent } from "./tasks.ts"

const schema = (properties: Record<string, unknown>, required: string[] = []) => ({
  type: "object",
  properties,
  required,
  additionalProperties: false,
})

const summary = (t: Task) =>
  `${t.id} [${t.status}${t.exitCode != null ? ` exit=${t.exitCode}` : ""}${t.signal ? ` signal=${t.signal}` : ""}] pid=${t.pid} log=${t.log}\n  $ ${t.command}`

export default Plugin.define({
  id: "local.bg-tasks",
  async setup(ctx) {
    const root = join(
      process.env.XDG_DATA_HOME ?? join(homedir(), ".local", "share"),
      "opencode",
      "bg-tasks",
      basename(ctx.location.project.canonical || ctx.location.directory),
    )

    let registration: Awaited<ReturnType<typeof ctx.rpc.register>> | undefined
    const publish = (event: TaskEvent) => {
      const { type, ...data } = event
      void (registration?.events.emit as any)?.(type, data)?.catch?.(() => {})
    }

    const synthetic = (input: any) => ctx.session.synthetic(input)
    let closed = false
    const wakeOnMatch = new Set<string>()
    const batchers = new Map<string, ReturnType<typeof createMatchBatcher>>()
    const batcherFor = (taskID: string) => {
      let b = batchers.get(taskID)
      if (!b) {
        b = createMatchBatcher({
          windowMs: 5_000,
          flush(lines) {
            if (closed) return
            const task = mgr.get(taskID)
            void deliver(synthetic, publish, {
              taskID,
              sessionID: task.sessionID,
              kind: "match",
              wake: wakeOnMatch.has(taskID),
              description: `bg task ${taskID} matched its watch pattern (${lines.length} line${lines.length === 1 ? "" : "s"})`,
              text: `Background task ${taskID} matched its watch pattern:\n${lines.join("\n")}`,
            })
          },
        })
        batchers.set(taskID, b)
      }
      return b
    }

    const mgr = createTaskManager({
      root,
      cwd: ctx.location.directory,
      emit(event) {
        publish(event)
        if (event.type === "matched") batcherFor(event.taskID).add(event.line)
        if (event.type === "exited") {
          const t = event.task
          batchers.get(t.id)?.flushNow()
          batchers.delete(t.id)
          wakeOnMatch.delete(t.id)
          if (event.reason === "reload" || closed) return // plugin is unloading; cannot deliver
          const timeout = event.reason === "timeout"
          const secs = ((Date.now() - t.startedAt) / 1000).toFixed(1)
          const what = timeout ? "hit its timeout" : event.reason === "error" ? "failed to start" : t.status
          const text = event.reason === "error"
            ? `Background task ${t.id} failed to start: ${event.detail}`
            : `Background task ${t.id} ${timeout ? "hit its timeout and was killed" : t.status} after ${secs}s (exit=${t.exitCode ?? "none"}${t.signal ? `, signal=${t.signal}` : ""}).\nCommand: ${t.command}\nLog: ${t.log}\nLast output:\n${tail(t.log, 2_000)}`
          void deliver(synthetic, publish, {
            taskID: t.id,
            sessionID: t.sessionID,
            kind: timeout ? "timeout" : "exit",
            description: `bg task ${t.id} ${what} (exit ${t.exitCode ?? t.signal ?? "?"}, ${secs}s)`,
            text,
          })
        }
      },
    })

    registration = await ctx.rpc.register(BgTasks, {
      list: async () => ({ tasks: mgr.list() }),
      output: async (input: any, context: any) => {
        try {
          return { text: mgr.output(input.id, input.bytes) }
        } catch {
          return context.error("unknown_task", `Unknown background task: ${input.id}`, { id: input.id })
        }
      },
      kill: async (input: any, context: any) => {
        try {
          return { task: mgr.kill(input.id) }
        } catch {
          return context.error("unknown_task", `Unknown background task: ${input.id}`, { id: input.id })
        }
      },
    } as any)

    void ctx.tool.transform((editor) => {
      editor.add({
        name: "background_bash",
        description:
          "Run a shell command in the background (detached). Returns immediately with a task id. When it exits, a synthetic message with the exit code and log path is added to the session. Use for long waits (CI, sweeps, servers).",
        input: schema(
          {
            command: { type: "string", description: "Shell command, run via /bin/sh -lc" },
            cwd: { type: "string", description: "Working directory (defaults to project directory)" },
            watch: {
              type: "string",
              description:
                "Optional JS regex. Each new log line matching it sends a notification to the session (max 20), like a monitor.",
            },
            timeout: { type: "number", description: "Optional seconds after which the task is killed" },
            wake: {
              type: "boolean",
              description: "Watch matches wake an idle agent (default false: matches are queued until the agent's next turn).",
            },
          },
          ["command"],
        ),
        execute: async (input: any, context: any) => {
          const task = mgr.start(input, context.sessionID)
          if (input.wake) wakeOnMatch.add(task.id)
          return { content: `Started ${summary(task)}` }
        },
      })

      editor.add({
        name: "background_output",
        description: "Read the tail of a background task's log.",
        input: schema(
          {
            id: { type: "string" },
            bytes: { type: "number", description: `Max bytes from the end (default ${TAIL_BYTES})` },
          },
          ["id"],
        ),
        execute: async (input: any) => ({
          content: `${summary(mgr.get(input.id))}\n---\n${mgr.output(input.id, input.bytes)}`,
        }),
      })

      editor.add({
        name: "background_tasks",
        description: "List background tasks started in this OpenCode server process.",
        input: schema({}),
        execute: async () => {
          const all = mgr.list()
          return { content: all.length ? all.map(summary).join("\n") : "No background tasks." }
        },
      })

      editor.add({
        name: "background_kill",
        description: "Kill a running background task (whole process group): SIGTERM, then SIGKILL after a 5s grace.",
        input: schema({ id: { type: "string" } }, ["id"]),
        execute: async (input: any) => {
          const task = mgr.get(input.id)
          if (task.status !== "running") return { content: `Already finished: ${summary(task)}` }
          mgr.kill(input.id)
          return { content: `Sent SIGTERM to ${task.id} (SIGKILL after 5s if it ignores it)` }
        },
      })
    })

    return () => {
      closed = true // drop pending batches and retries instead of delivering into a torn-down context
      mgr.shutdown()
    }
  },
})
