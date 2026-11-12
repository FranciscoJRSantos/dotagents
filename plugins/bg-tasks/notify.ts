import type { NotifyKind, TaskEvent } from "./tasks.ts"

export const PREFIX = "[bg-tasks] "

type SyntheticInput = {
  sessionID: string
  text: string
  description?: string
  metadata?: Record<string, unknown>
  delivery?: "queue"
  resume?: boolean
}
type Synthetic = (input: SyntheticInput) => Promise<unknown>

export type Message = {
  taskID: string
  sessionID: string
  kind: NotifyKind
  text: string
  /** One-line summary, shown by the TUI if it renders synthetic descriptions. */
  description: string
  /** Matches only: wake an idle agent. Exit and timeout always do. */
  wake?: boolean
}

type DeliverOpts = {
  now?: () => number
  retryMs?: number
  sleep?: (ms: number) => Promise<void>
}

/**
 * Send one synthetic message and report the final outcome as a single `notified` event.
 * Retries once after `retryMs`; there is no persistent queue.
 */
export async function deliver(
  synthetic: Synthetic,
  emit: (event: TaskEvent) => void,
  msg: Message,
  { now = Date.now, retryMs = 2_000, sleep = (ms) => new Promise<void>((r) => setTimeout(r, ms)) }: DeliverOpts = {},
): Promise<void> {
  const isMatch = msg.kind === "match"
  const input: SyntheticInput = {
    sessionID: msg.sessionID,
    text: PREFIX + msg.text,
    description: msg.description,
    metadata: { source: "bg-tasks", taskID: msg.taskID, kind: msg.kind },
    resume: isMatch ? msg.wake === true : true,
    ...(isMatch && msg.wake !== true ? { delivery: "queue" as const } : {}),
  }
  let error: unknown
  for (let attempt = 0; attempt < 2; attempt++) {
    if (attempt > 0) await sleep(retryMs)
    try {
      await synthetic(input)
      emit({ type: "notified", taskID: msg.taskID, kind: msg.kind, ok: true, at: now() })
      return
    } catch (err) {
      error = err
    }
  }
  emit({
    type: "notified",
    taskID: msg.taskID,
    kind: msg.kind,
    ok: false,
    error: error instanceof Error ? error.message : String(error),
    at: now(),
  })
}

/** Collect watch matches and flush them together once per window. */
export function createMatchBatcher(opts: { windowMs: number; flush: (lines: string[]) => void }) {
  let lines: string[] = []
  let timer: ReturnType<typeof setTimeout> | undefined
  const flushNow = () => {
    if (timer) clearTimeout(timer)
    timer = undefined
    if (lines.length === 0) return
    const batch = lines
    lines = []
    opts.flush(batch)
  }
  return {
    add(line: string) {
      lines.push(line)
      timer ??= setTimeout(flushNow, opts.windowMs)
    },
    flushNow,
  }
}
