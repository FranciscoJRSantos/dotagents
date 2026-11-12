import { Rpc } from "@opencode/plugin/rpc"

const str = { type: "string" }
const num = { type: "number" }
const obj = (properties: Record<string, unknown>, required: string[]) => ({
  type: "object",
  properties,
  required,
  additionalProperties: false,
})

const task = obj(
  {
    id: str,
    sessionID: str,
    command: str,
    pid: num,
    log: str,
    startedAt: num,
    status: { enum: ["running", "exited", "killed"] },
    exitCode: { type: ["number", "null"] },
    signal: { type: ["string", "null"] },
  },
  ["id", "sessionID", "command", "pid", "log", "startedAt", "status"],
)

export const BgTasks = Rpc.define({
  id: "bg-tasks",
  methods: {
    list: { output: obj({ tasks: { type: "array", items: task } }, ["tasks"]) },
    output: {
      input: obj({ id: str, bytes: num }, ["id"]),
      output: obj({ text: str }, ["text"]),
      errors: { unknown_task: obj({ id: str }, ["id"]) },
    },
    kill: {
      input: obj({ id: str }, ["id"]),
      output: obj({ task }, ["task"]),
      errors: { unknown_task: obj({ id: str }, ["id"]) },
    },
  },
  events: {
    started: { schema: obj({ task }, ["task"]) },
    matched: { schema: obj({ taskID: str, line: str }, ["taskID", "line"]) },
    exited: {
      schema: obj({ task, reason: { enum: ["exit", "timeout", "killed", "error"] }, detail: str }, ["task"]),
    },
    notified: {
      schema: obj(
        { taskID: str, kind: { enum: ["exit", "match", "timeout"] }, ok: { type: "boolean" }, error: str, at: num },
        ["taskID", "kind", "ok", "at"],
      ),
    },
  },
})
