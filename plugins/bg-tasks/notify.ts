import type { NotifyKind, TaskEvent } from "./tasks.ts"

type Synthetic = (input: { sessionID: string; text: string }) => Promise<unknown>

/** Send one synthetic message to the session and report the outcome as a `notified` event. */
export async function deliver(
  synthetic: Synthetic,
  emit: (event: TaskEvent) => void,
  msg: { taskID: string; sessionID: string; kind: NotifyKind; text: string },
  now: () => number = Date.now,
): Promise<void> {
  try {
    await synthetic({ sessionID: msg.sessionID, text: msg.text })
    emit({ type: "notified", taskID: msg.taskID, kind: msg.kind, ok: true, at: now() })
  } catch (err) {
    emit({
      type: "notified",
      taskID: msg.taskID,
      kind: msg.kind,
      ok: false,
      error: err instanceof Error ? err.message : String(err),
      at: now(),
    })
  }
}
