import { test } from "node:test"
import assert from "node:assert/strict"
import { reduce, footerText, toastFor, attentionFor, sidebarRows, formatElapsed, truncate, type UiState } from "../tui-state.ts"
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

const empty: UiState = { tasks: {}, flash: {}, notified: {} }

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

test("formatElapsed", () => {
  assert.equal(formatElapsed(12_400), "12s")
  assert.equal(formatElapsed(185_000), "3m05s")
  assert.equal(formatElapsed(3_720_000), "1h02m")
})

test("truncate collapses whitespace and adds an ellipsis", () => {
  assert.equal(truncate("a   b\n c", 10), "a b c")
  assert.equal(truncate("x".repeat(50), 10), "xxxxxxxxx…")
})

test("sidebar lists this session's tasks with status, elapsed and command", () => {
  let s = reduce(empty, { type: "started", task: task({ startedAt: 1_000, command: "sleep 100" }) })
  s = reduce(s, { type: "started", task: task({ id: "bg9", sessionID: "other" }) })
  const rows = sidebarRows(s, "s1", 13_000)
  assert.equal(rows.length, 1)
  assert.equal(rows[0].main, "⚙ bg1 12s  sleep 100")
  assert.equal(rows[0].notice, undefined)
})

test("finished tasks use endedAt for elapsed and show their outcome icon", () => {
  const t = task({ status: "exited", exitCode: 1, startedAt: 0, endedAt: 5_000 })
  const s = reduce(empty, { type: "exited", task: t })
  assert.equal(sidebarRows(s, "s1", 999_999)[0].main, "✗ bg1 5s  sleep 5")
})

test("sidebar shows the delivery outcome per task", () => {
  const at = new Date(2026, 10, 12, 12, 4).getTime()
  let s = reduce(empty, { type: "started", task: task() })
  s = reduce(s, { type: "notified", taskID: "bg1", kind: "exit", ok: true, at })
  assert.equal(sidebarRows(s, "s1", 0)[0].notice, "↳ agent notified 12:04 ✓")
  s = reduce(s, { type: "notified", taskID: "bg1", kind: "exit", ok: false, error: "boom", at })
  assert.equal(sidebarRows(s, "s1", 0)[0].notice, "↳ ✗ delivery failed: boom")
})

test("snapshot keeps already-known delivery notices", () => {
  let s = reduce(empty, { type: "notified", taskID: "bg1", kind: "exit", ok: true, at: 1 })
  s = reduce(s, { type: "snapshot", tasks: [task()] })
  assert.ok(sidebarRows(s, "s1", 0)[0].notice)
})

test("elapsed never goes negative for a task newer than the last tick", () => {
  const s = reduce(empty, { type: "started", task: task({ startedAt: 5_000 }) })
  assert.match(sidebarRows(s, "s1", 4_000)[0].main, /^⚙ bg1 0s /)
})

test("attention fires on exit and timeout only", () => {
  const t = task({ status: "exited", exitCode: 0 })
  assert.match(attentionFor({ type: "exited", task: t })!.message, /bg1.*finished/)
  assert.match(attentionFor({ type: "exited", task: { ...t, exitCode: 2 } })!.message, /failed/)
  assert.match(attentionFor({ type: "exited", task: t, reason: "timeout" })!.message, /timeout/)
  assert.equal(attentionFor({ type: "matched", taskID: "bg1", line: "x" }), undefined)
  assert.equal(attentionFor({ type: "started", task: task() }), undefined)
  assert.equal(attentionFor({ type: "notified", taskID: "bg1", kind: "exit", ok: false, at: 1 }), undefined)
  assert.equal(attentionFor({ type: "exited", task: t, reason: "reload" }), undefined)
  assert.equal(attentionFor({ type: "exited", task: { ...t, status: "killed" }, reason: "killed" }), undefined)
})
