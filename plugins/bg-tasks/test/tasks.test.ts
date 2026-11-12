import { test } from "node:test"
import assert from "node:assert/strict"
import { mkdtempSync, readFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { createTaskManager, validateWatch, type TaskEvent } from "../tasks.ts"

function setup(graceMs = 200) {
  const events: TaskEvent[] = []
  const root = mkdtempSync(join(tmpdir(), "bg-tasks-"))
  const mgr = createTaskManager({ root, cwd: root, graceMs, emit: (e) => events.push(e) })
  return { events, mgr, root }
}

const until = async (pred: () => boolean, ms = 5000) => {
  const end = Date.now() + ms
  while (!pred()) {
    if (Date.now() > end) throw new Error("timed out waiting for condition")
    await new Promise((r) => setTimeout(r, 25))
  }
}

test("validateWatch rejects an invalid regex with a clean error", () => {
  assert.throws(() => validateWatch("(unclosed"), /Invalid watch regex/)
  assert.equal(validateWatch(undefined), undefined)
  assert.ok(validateWatch("ok|done") instanceof RegExp)
})

test("start() with an invalid regex does not spawn or register a task", () => {
  const { mgr, events } = setup()
  assert.throws(() => mgr.start({ command: "sleep 30", watch: "(" }, "ses1"), /Invalid watch regex/)
  assert.equal(mgr.list().length, 0)
  assert.equal(events.length, 0)
})

test("a finished task emits started then exited and keeps its exit code", async () => {
  const { mgr, events } = setup()
  const task = mgr.start({ command: "echo hi; exit 3" }, "ses1")
  await until(() => events.some((e) => e.type === "exited"))
  assert.deepEqual(events.map((e) => e.type), ["started", "exited"])
  const t = mgr.get(task.id)
  assert.equal(t.status, "exited")
  assert.equal(t.exitCode, 3)
  assert.match(readFileSync(t.log, "utf8"), /hi/)
})

test("kill() escalates to SIGKILL for a process that ignores SIGTERM", async () => {
  const { mgr, events } = setup(200)
  const task = mgr.start({ command: "trap '' TERM; while :; do sleep 0.1; done" }, "ses1")
  await new Promise((r) => setTimeout(r, 300))
  mgr.kill(task.id)
  // status stays running until the process is actually gone
  assert.equal(mgr.get(task.id).status, "running")
  await until(() => events.some((e) => e.type === "exited"))
  const t = mgr.get(task.id)
  assert.equal(t.status, "killed")
  assert.equal(t.signal, "SIGKILL")
})

test("timeout kills the task and the exit event carries kind timeout", async () => {
  const { mgr, events } = setup(100)
  mgr.start({ command: "sleep 30", timeout: 0.2 }, "ses1")
  await until(() => events.some((e) => e.type === "exited"))
  const exited = events.find((e) => e.type === "exited")
  assert.ok(exited && exited.type === "exited")
  assert.equal(exited.reason, "timeout")
})

test("list() returns every task with its sessionID", () => {
  const { mgr } = setup()
  mgr.start({ command: "sleep 0.1" }, "a")
  mgr.start({ command: "sleep 0.1" }, "b")
  assert.deepEqual(mgr.list().map((t) => t.sessionID).sort(), ["a", "b"])
})

test("a failed spawn never signals PID 1 and leaves no watch timer behind", async () => {
  const { mgr, events } = setup()
  const real = process.kill
  const targets: number[] = []
  process.kill = ((pid: number, sig?: any) => (targets.push(pid), real(pid, sig))) as typeof process.kill
  try {
    const task = mgr.start({ command: "echo hi", cwd: "/nonexistent-dir", watch: "hi" }, "ses1")
    mgr.kill(task.id)
    await until(() => events.some((e) => e.type === "exited"))
    mgr.shutdown()
  } finally {
    process.kill = real
  }
  assert.ok(!targets.includes(1), `signalled PID 1: ${targets}`)
  const exited = events.find((e) => e.type === "exited")
  assert.ok(exited && exited.type === "exited" && exited.reason === "error")
})

test("a task that exits cleanly during the kill grace window is exited, not killed", async () => {
  const { mgr, events } = setup(5000)
  const task = mgr.start({ command: "trap 'exit 0' TERM; while :; do sleep 0.1; done" }, "ses1")
  await new Promise((r) => setTimeout(r, 300))
  mgr.kill(task.id)
  await until(() => events.some((e) => e.type === "exited"))
  assert.equal(mgr.get(task.id).status, "exited")
  assert.equal(mgr.get(task.id).exitCode, 0)
})

test("shutdown emits exited with reason reload before signalling, and nothing after", async () => {
  const { mgr, events } = setup()
  const task = mgr.start({ command: "sleep 30" }, "ses1")
  mgr.shutdown()
  const exited = events.filter((e) => e.type === "exited")
  assert.equal(exited.length, 1)
  const e = exited[0]
  assert.ok(e.type === "exited")
  assert.equal(e.reason, "reload")
  assert.equal(e.detail, "killed: plugin reload")
  assert.equal(e.task.status, "killed")
  await new Promise((r) => setTimeout(r, 300))
  assert.equal(events.filter((x) => x.type === "exited").length, 1)
  assert.equal(mgr.get(task.id).status, "killed")
})

test("no matched events are emitted after shutdown", async () => {
  const { mgr, events } = setup(100)
  mgr.start({ command: "sleep 0.2; echo hit; sleep 5", watch: "hit" }, "ses1")
  mgr.shutdown()
  await new Promise((r) => setTimeout(r, 1500))
  assert.equal(events.filter((e) => e.type === "matched").length, 0)
})

test("an exited task records endedAt", async () => {
  const { mgr, events } = setup()
  const task = mgr.start({ command: "true" }, "ses1")
  await until(() => events.some((e) => e.type === "exited"))
  const t = mgr.get(task.id)
  assert.ok(typeof t.endedAt === "number" && t.endedAt >= t.startedAt)
})
