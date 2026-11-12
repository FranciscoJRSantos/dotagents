import { test } from "node:test"
import assert from "node:assert/strict"
import { reduce, footerText, toastFor, type UiState } from "../tui-state.ts"
import type { Task } from "../tasks.ts"

const task = (over: Partial<Task> = {}): Task => ({
  id: "bg1",
  sessionID: "s1",
  command: "sleep 5",
  pid: 1,
  log: "/tmp/x",
  startedAt: 0,
  status: "running",
  ...over,
})

const empty: UiState = { tasks: {}, flash: {} }

test("footer is empty when the session has no tasks", () => {
  assert.equal(footerText(empty, "s1"), "")
})

test("footer counts running tasks of the current session only", () => {
  let s = reduce(empty, { type: "started", task: task() })
  s = reduce(s, { type: "started", task: task({ id: "bg2" }) })
  s = reduce(s, { type: "started", task: task({ id: "bg3", sessionID: "other" }) })
  assert.equal(footerText(s, "s1"), "⚙ 2 running")
})

test("footer flashes done or failed after exit, then goes back to quiet", () => {
  let s = reduce(empty, { type: "started", task: task() })
  s = reduce(s, { type: "exited", task: task({ status: "exited", exitCode: 0 }) })
  assert.equal(footerText(s, "s1"), "✓ done")
  s = reduce(empty, { type: "started", task: task() })
  s = reduce(s, { type: "exited", task: task({ status: "exited", exitCode: 2 }) })
  assert.equal(footerText(s, "s1"), "✗ failed")
  s = reduce(s, { type: "flash-expired", taskID: "bg1" })
  assert.equal(footerText(s, "s1"), "")
})

test("toasts fire on exit, timeout and delivery failure but not on matches", () => {
  const t = task({ status: "exited", exitCode: 0 })
  assert.match(toastFor({ type: "exited", task: t })!.message, /bg1/)
  assert.equal(toastFor({ type: "exited", task: t })!.variant, "success")
  assert.equal(toastFor({ type: "exited", task: { ...t, exitCode: 1 } })!.variant, "error")
  assert.equal(toastFor({ type: "exited", task: t, reason: "timeout" })!.variant, "warning")
  assert.equal(toastFor({ type: "matched", taskID: "bg1", line: "x" }), undefined)
  assert.equal(toastFor({ type: "started", task: task() }), undefined)
  assert.equal(toastFor({ type: "notified", taskID: "bg1", kind: "exit", ok: true, at: 1 }), undefined)
  const failed = toastFor({ type: "notified", taskID: "bg1", kind: "exit", ok: false, error: "boom", at: 1 })!
  assert.equal(failed.variant, "error")
  assert.match(failed.message, /boom/)
})

test("list snapshot seeds state", () => {
  const s = reduce(empty, { type: "snapshot", tasks: [task(), task({ id: "bg2", status: "exited", exitCode: 0 })] })
  assert.equal(footerText(s, "s1"), "⚙ 1 running")
})

test("a task ended by an external signal counts as failed", () => {
  let s = reduce(empty, { type: "started", task: task() })
  const t = task({ status: "exited", exitCode: null, signal: "SIGKILL" })
  s = reduce(s, { type: "exited", task: t })
  assert.equal(footerText(s, "s1"), "✗ failed")
  assert.equal(toastFor({ type: "exited", task: t })!.variant, "error")
})

test("a plugin reload does not raise an error toast", () => {
  const t = task({ status: "killed" })
  assert.equal(toastFor({ type: "exited", task: t, reason: "reload", detail: "killed: plugin reload" }), undefined)
})
