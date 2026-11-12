import { test } from "node:test"
import assert from "node:assert/strict"
import { deliver } from "../notify.ts"
import type { TaskEvent } from "../tasks.ts"

const msg = { taskID: "bg1", sessionID: "s1", kind: "exit" as const, text: "done" }

test("deliver emits notified ok:true when the synthetic call succeeds", async () => {
  const events: TaskEvent[] = []
  await deliver(async () => ({}), (e) => events.push(e), msg, () => 42)
  assert.deepEqual(events, [{ type: "notified", taskID: "bg1", kind: "exit", ok: true, at: 42 }])
})

test("deliver emits notified ok:false with the error instead of swallowing it", async () => {
  const events: TaskEvent[] = []
  await deliver(
    async () => {
      throw new Error("session gone")
    },
    (e) => events.push(e),
    msg,
    () => 7,
  )
  assert.deepEqual(events, [{ type: "notified", taskID: "bg1", kind: "exit", ok: false, error: "session gone", at: 7 }])
})
