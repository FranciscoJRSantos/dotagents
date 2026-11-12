import { Plugin } from "@opencode/plugin"
import { homedir } from "node:os"
import { basename, join } from "node:path"
import { deliver } from "./notify.ts"
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

    const synthetic = (input: { sessionID: string; text: string }) => ctx.session.synthetic(input)
    const mgr = createTaskManager({
      root,
      cwd: ctx.location.directory,
      emit(event) {
        publish(event)
        if (event.type === "matched") {
          const task = mgr.get(event.taskID)
          void deliver(synthetic, publish, {
            taskID: task.id,
            sessionID: task.sessionID,
            kind: "match",
            text: `Background task ${task.id} matched its watch pattern: ${event.line}`,
          })
        }
        if (event.type === "exited") {
          const t = event.task
          const timeout = event.reason === "timeout"
          const secs = ((Date.now() - t.startedAt) / 1000).toFixed(1)
          const text = event.reason === "error"
            ? `Background task ${t.id} failed to start: ${event.detail}`
            : `Background task ${t.id} ${timeout ? "hit its timeout and was killed" : t.status} after ${secs}s (exit=${t.exitCode ?? "none"}${t.signal ? `, signal=${t.signal}` : ""}).\nCommand: ${t.command}\nLog: ${t.log}\nLast output:\n${tail(t.log, 2_000)}`
          void deliver(synthetic, publish, {
            taskID: t.id,
            sessionID: t.sessionID,
            kind: timeout ? "timeout" : "exit",
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
          },
          ["command"],
        ),
        execute: async (input: any, context: any) => {
          const task = mgr.start(input, context.sessionID)
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

    return () => mgr.shutdown()
  },
})
