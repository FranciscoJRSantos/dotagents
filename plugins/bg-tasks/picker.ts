import { failed, formatElapsed, truncate, type Toast, type UiState } from "./tui-state.ts"

export type PickerOption = { title: string; value: string; description: string; category: "Running" | "Finished" }

export function pickerOptions(state: UiState, sessionID: string | undefined, now: number): PickerOption[] {
  // No current session (e.g. on the home route): show every task of the project.
  const mine = Object.values(state.tasks).filter((t) => sessionID === undefined || t.sessionID === sessionID)
  const running = mine.filter((t) => t.status === "running").sort((a, b) => a.startedAt - b.startedAt)
  const finished = mine.filter((t) => t.status !== "running").sort((a, b) => (b.endedAt ?? 0) - (a.endedAt ?? 0))
  const option = (t: (typeof mine)[number], category: PickerOption["category"]): PickerOption => {
    const icon = category === "Running" ? "⚙" : failed(t) ? "✗" : "✓"
    const elapsed = formatElapsed(Math.max(0, (t.endedAt ?? now) - t.startedAt))
    return { title: `${icon} ${t.id} ${elapsed}`, value: t.id, description: truncate(t.command, 60), category }
  }
  return [...running.map((t) => option(t, "Running")), ...finished.map((t) => option(t, "Finished"))]
}

/** RPC failures are plain objects (not Error instances), so `String(err)` would print "[object Object]". */
export function errorText(err: unknown): string {
  if (err && typeof err === "object") {
    const e = err as { message?: unknown; type?: unknown }
    const text = typeof e.message === "string" ? e.message : JSON.stringify(err)
    // The server forgets every task when its plugin reloads, while the TUI keeps listing them.
    return e.type === "unknown_task" ? `${text} (the server plugin was reloaded since it ran)` : text
  }
  return String(err)
}

/** Kill through RPC (not the agent). Never throws: the result is shown as a toast. */
export async function killSelected(
  rpc: { kill: (input: { id: string }) => Promise<unknown> },
  state: UiState,
  id: string,
): Promise<Toast> {
  const task = state.tasks[id]
  if (!task) return { message: `unknown bg task ${id}`, variant: "error" }
  if (task.status !== "running") return { message: `bg task ${id} already finished`, variant: "warning" }
  try {
    await rpc.kill({ id })
    return { message: `sent SIGTERM to bg task ${id} (SIGKILL after 5s)`, variant: "warning" }
  } catch (err) {
    return { message: `could not kill bg task ${id}: ${errorText(err)}`, variant: "error" }
  }
}
