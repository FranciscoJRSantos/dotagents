import type { ExitReason, Task, TaskEvent } from "./tasks.ts"

export type UiState = {
  tasks: Record<string, Task>
  /** Tasks whose exit result is still shown in the footer. */
  flash: Record<string, true>
  /** Latest delivery outcome per task. */
  notified: Record<string, { ok: boolean; error?: string; at: number }>
}

export type UiAction = TaskEvent | { type: "snapshot"; tasks: Task[] } | { type: "flash-expired"; taskID: string }

export function reduce(state: UiState, action: UiAction): UiState {
  switch (action.type) {
    case "snapshot":
      return { ...state, tasks: Object.fromEntries(action.tasks.map((t) => [t.id, t])), flash: {} }
    case "started":
      return { ...state, tasks: { ...state.tasks, [action.task.id]: action.task } }
    case "exited":
      return {
        ...state,
        tasks: { ...state.tasks, [action.task.id]: action.task },
        flash: { ...state.flash, [action.task.id]: true },
      }
    case "notified":
      return { ...state, notified: { ...state.notified, [action.taskID]: { ok: action.ok, error: action.error, at: action.at } } }
    case "flash-expired": {
      const { [action.taskID]: _gone, ...flash } = state.flash
      return { ...state, flash }
    }
    default:
      return state
  }
}

export const failed = (t: Task) => t.status === "killed" || t.signal != null || (t.exitCode ?? 0) !== 0

export function footerText(state: UiState, sessionID: string): string {
  const mine = Object.values(state.tasks).filter((t) => t.sessionID === sessionID)
  const running = mine.filter((t) => t.status === "running").length
  if (running > 0) return `⚙ ${running} running`
  const flashed = mine.filter((t) => state.flash[t.id])
  if (flashed.length === 0) return ""
  return flashed.some(failed) ? "✗ failed" : "✓ done"
}

export type Toast = { message: string; variant: "success" | "error" | "warning" }

function exitMessage(t: Task, reason: ExitReason | undefined): Toast {
  if (reason === "timeout") return { message: `bg task ${t.id} hit its timeout`, variant: "warning" }
  if (failed(t)) return { message: `bg task ${t.id} failed (exit ${t.exitCode ?? t.signal ?? "?"})`, variant: "error" }
  return { message: `bg task ${t.id} finished`, variant: "success" }
}

export function toastFor(event: TaskEvent): Toast | undefined {
  if (event.type === "exited") {
    if (event.reason === "reload") return undefined // routine config reload, not a failure
    return exitMessage(event.task, event.reason)
  }
  if (event.type === "notified" && !event.ok) {
    return { message: `bg task ${event.taskID}: agent not notified (${event.error ?? "unknown error"})`, variant: "error" }
  }
  return undefined
}

export function formatElapsed(ms: number): string {
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m${String(s % 60).padStart(2, "0")}s`
  return `${Math.floor(s / 3600)}h${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}m`
}

export function truncate(text: string, max: number): string {
  const flat = text.replace(/\s+/g, " ").trim()
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat
}

const hhmm = (at: number) => {
  const d = new Date(at)
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
}

export type SidebarRow = { id: string; main: string; notice?: string }

export function sidebarRows(state: UiState, sessionID: string, now: number): SidebarRow[] {
  return Object.values(state.tasks)
    .filter((t) => t.sessionID === sessionID)
    .sort((a, b) => a.startedAt - b.startedAt)
    .map((t) => {
      const icon = t.status === "running" ? "⚙" : failed(t) ? "✗" : "✓"
      const elapsed = formatElapsed(Math.max(0, (t.endedAt ?? now) - t.startedAt))
      const n = state.notified[t.id]
      const notice = n ? (n.ok ? `↳ agent notified ${hhmm(n.at)} ✓` : `↳ ✗ delivery failed: ${n.error ?? "unknown error"}`) : undefined
      return { id: t.id, main: `${icon} ${t.id} ${elapsed}  ${truncate(t.command, 40)}`, notice }
    })
}

/** Blurred-terminal notification: natural exit, failure and timeout only (not matches, delivery, user kills or reloads). */
export function attentionFor(event: TaskEvent): { title: string; message: string } | undefined {
  if (event.type !== "exited" || event.reason === "reload" || event.reason === "killed") return undefined
  return { title: "OpenCode background task", message: exitMessage(event.task, event.reason).message }
}
