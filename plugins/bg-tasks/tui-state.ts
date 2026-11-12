import type { Task, TaskEvent } from "./tasks.ts"

export type UiState = {
  tasks: Record<string, Task>
  /** Tasks whose exit result is still shown in the footer. */
  flash: Record<string, true>
}

export type UiAction = TaskEvent | { type: "snapshot"; tasks: Task[] } | { type: "flash-expired"; taskID: string }

export function reduce(state: UiState, action: UiAction): UiState {
  switch (action.type) {
    case "snapshot":
      return { tasks: Object.fromEntries(action.tasks.map((t) => [t.id, t])), flash: {} }
    case "started":
      return { ...state, tasks: { ...state.tasks, [action.task.id]: action.task } }
    case "exited":
      return {
        tasks: { ...state.tasks, [action.task.id]: action.task },
        flash: { ...state.flash, [action.task.id]: true },
      }
    case "flash-expired": {
      const { [action.taskID]: _gone, ...flash } = state.flash
      return { ...state, flash }
    }
    default:
      return state
  }
}

const failed = (t: Task) => t.status === "killed" || t.signal != null || (t.exitCode ?? 0) !== 0

export function footerText(state: UiState, sessionID: string): string {
  const mine = Object.values(state.tasks).filter((t) => t.sessionID === sessionID)
  const running = mine.filter((t) => t.status === "running").length
  if (running > 0) return `⚙ ${running} running`
  const flashed = mine.filter((t) => state.flash[t.id])
  if (flashed.length === 0) return ""
  return flashed.some(failed) ? "✗ failed" : "✓ done"
}

export type Toast = { message: string; variant: "success" | "error" | "warning" }

export function toastFor(event: TaskEvent): Toast | undefined {
  if (event.type === "exited") {
    const t = event.task
    if (event.reason === "timeout") return { message: `bg task ${t.id} hit its timeout`, variant: "warning" }
    if (failed(t)) return { message: `bg task ${t.id} failed (exit ${t.exitCode ?? t.signal ?? "?"})`, variant: "error" }
    return { message: `bg task ${t.id} finished`, variant: "success" }
  }
  if (event.type === "notified" && !event.ok) {
    return { message: `bg task ${event.taskID}: agent not notified (${event.error ?? "unknown error"})`, variant: "error" }
  }
  return undefined
}
