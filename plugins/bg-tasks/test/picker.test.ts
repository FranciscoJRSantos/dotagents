import { test } from "node:test"
import assert from "node:assert/strict"
import { killSelected, pickerOptions } from "../picker.ts"
import { reduce, type UiState } from "../tui-state.ts"
import type { Task } from "../tasks.ts"

const task = (over: Partial<Task> = {}): Task => ({
  id: "bg1",
  sessionID: "s1",
  command: "sleep 100",
  pid: 1,
  log: "/tmp/x",
  startedAt: 0,
  status: "running",
  ...over,
})
const empty: UiState = { tasks: {}, flash: {}, notified: {} }

test("options list this session's tasks, running first, with status and command", () => {
  let s = reduce(empty, { type: "started", task: task({ id: "old", status: "exited", exitCode: 0, endedAt: 3_000 }) })
  s = reduce(s, { type: "started", task: task({ id: "live", startedAt: 1_000, command: "npm run dev" }) })
  s = reduce(s, { type: "started", task: task({ id: "x", sessionID: "other" }) })
  const opts = pickerOptions(s, "s1", 11_000)
  assert.deepEqual(opts.map((o) => o.value), ["live", "old"])
  assert.equal(opts[0].title, "⚙ live 10s")
  assert.equal(opts[0].description, "npm run dev")
  assert.equal(opts[0].category, "Running")
  assert.equal(opts[1].category, "Finished")
})

test("killSelected calls rpc.kill for a running task", async () => {
  const s = reduce(empty, { type: "started", task: task() })
  const calls: string[] = []
  const r = await killSelected({ kill: async ({ id }) => void calls.push(id) }, s, "bg1")
  assert.deepEqual(calls, ["bg1"])
  assert.equal(r.variant, "warning")
  assert.match(r.message, /bg1/)
})

test("killSelected does not call rpc for a finished or unknown task", async () => {
  const s = reduce(empty, { type: "started", task: task({ status: "exited", exitCode: 0 }) })
  const calls: string[] = []
  const rpc = { kill: async ({ id }: { id: string }) => void calls.push(id) }
  assert.match((await killSelected(rpc, s, "bg1")).message, /already finished/)
  assert.match((await killSelected(rpc, s, "nope")).message, /unknown/i)
  assert.deepEqual(calls, [])
})

test("killSelected reports an rpc failure instead of throwing", async () => {
  const s = reduce(empty, { type: "started", task: task() })
  const r = await killSelected({ kill: async () => { throw new Error("offline") } }, s, "bg1")
  assert.equal(r.variant, "error")
  assert.match(r.message, /offline/)
})

test("without a session, options cover every session", () => {
  let s = reduce(empty, { type: "started", task: task({ id: "a" }) })
  s = reduce(s, { type: "started", task: task({ id: "b", sessionID: "other" }) })
  assert.equal(pickerOptions(s, undefined, 0).length, 2)
})
