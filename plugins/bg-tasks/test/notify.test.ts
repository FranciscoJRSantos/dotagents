import { test } from "node:test"
import assert from "node:assert/strict"
import { createMatchBatcher, deliver, PREFIX } from "../notify.ts"
import type { TaskEvent } from "../tasks.ts"

const msg = { taskID: "bg1", sessionID: "s1", kind: "exit" as const, text: "done", description: "bg task bg1 exited (exit 0, 1.0s)" }
const opts = { now: () => 42, retryMs: 1, sleep: async () => {} }

test("deliver emits notified ok:true when the synthetic call succeeds", async () => {
  const events: TaskEvent[] = []
  await deliver(async () => ({}), (e) => events.push(e), msg, opts)
  assert.deepEqual(events, [{ type: "notified", taskID: "bg1", kind: "exit", ok: true, at: 42 }])
})

test("deliver sets description, metadata and the [bg-tasks] prefix", async () => {
  const sent: any[] = []
  await deliver(async (i) => sent.push(i), () => {}, msg, opts)
  assert.equal(sent.length, 1)
  assert.equal(sent[0].description, msg.description)
  assert.deepEqual(sent[0].metadata, { source: "bg-tasks", taskID: "bg1", kind: "exit" })
  assert.ok(sent[0].text.startsWith(PREFIX))
  assert.ok(sent[0].text.includes("done"))
})

test("exit and timeout resume the agent; match defaults to queue without resume", async () => {
  const sent: any[] = []
  const syn = async (i: any) => sent.push(i)
  await deliver(syn, () => {}, msg, opts)
  await deliver(syn, () => {}, { ...msg, kind: "timeout" }, opts)
  await deliver(syn, () => {}, { ...msg, kind: "match" }, opts)
  await deliver(syn, () => {}, { ...msg, kind: "match", wake: true }, opts)
  assert.deepEqual(sent.map((s) => s.resume), [true, true, false, true])
  assert.equal(sent[2].delivery, "queue")
  assert.equal(sent[3].delivery, undefined) // a waking match is delivered as a normal turn
  assert.equal(sent[0].delivery, undefined)
})

test("deliver retries once, then succeeds with a single notified ok:true", async () => {
  const events: TaskEvent[] = []
  let calls = 0
  await deliver(
    async () => {
      if (calls++ === 0) throw new Error("flaky")
    },
    (e) => events.push(e),
    msg,
    opts,
  )
  assert.equal(calls, 2)
  assert.deepEqual(events, [{ type: "notified", taskID: "bg1", kind: "exit", ok: true, at: 42 }])
})

test("deliver gives up after one retry and emits notified ok:false with the error", async () => {
  const events: TaskEvent[] = []
  let calls = 0
  await deliver(
    async () => {
      calls++
      throw new Error("session gone")
    },
    (e) => events.push(e),
    msg,
    opts,
  )
  assert.equal(calls, 2)
  assert.deepEqual(events, [{ type: "notified", taskID: "bg1", kind: "exit", ok: false, error: "session gone", at: 42 }])
})

test("batcher groups matches inside one window into a single flush", async () => {
  const flushed: string[][] = []
  const b = createMatchBatcher({ windowMs: 30, flush: (lines) => flushed.push(lines) })
  b.add("a")
  b.add("b")
  assert.equal(flushed.length, 0)
  await new Promise((r) => setTimeout(r, 80))
  assert.deepEqual(flushed, [["a", "b"]])
  b.add("c")
  await new Promise((r) => setTimeout(r, 80))
  assert.deepEqual(flushed, [["a", "b"], ["c"]])
})

test("batcher flushNow drains pending lines and cancels the timer", async () => {
  const flushed: string[][] = []
  const b = createMatchBatcher({ windowMs: 1000, flush: (lines) => flushed.push(lines) })
  b.add("a")
  b.flushNow()
  b.flushNow()
  assert.deepEqual(flushed, [["a"]])
})
