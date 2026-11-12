import { Plugin } from "@opencode/plugin/tui"
import { createSignal, For, Show } from "solid-js"
import { BgTasks } from "./rpc.ts"
import { footerText, reduce, sidebarRows, toastFor, type UiAction, type UiState } from "./tui-state.ts"

const FLASH_MS = 5_000

export default Plugin.define({
  id: "local.bg-tasks.tui",
  async setup(context) {
    const rpc = context.client.rpc(BgTasks)
    const [state, setState] = createSignal<UiState>({ tasks: {}, flash: {}, notified: {} })
    const apply = (action: UiAction) => setState((s) => reduce(s, action))

    // Events are live-only: seed from `list` so a late-connecting TUI is correct.
    try {
      const { tasks } = await rpc.list()
      apply({ type: "snapshot", tasks: tasks as any })
    } catch {}

    const stops = (["started", "matched", "exited", "notified"] as const).map((name) =>
      (rpc.events as any).on(name, (event: { data: any }) => {
        const action = { type: name, ...event.data } as UiAction
        apply(action)
        const toast = toastFor(action as any)
        if (toast) context.ui.toast.show({ title: "Background task", ...toast })
        if (name === "exited") {
          const id = event.data.task.id
          setTimeout(() => apply({ type: "flash-expired", taskID: id }), FLASH_MS)
        }
      }),
    )

    const unslot = context.ui.slot({
      append: "prompt.footer.status",
      render: ({ sessionID }: { sessionID?: string }) => {
        const text = () => (sessionID ? footerText(state(), sessionID) : "")
        return text() ? <text fg={context.theme.text.base}>{text()}</text> : null
      },
    })

    const [now, setNow] = createSignal(Date.now())
    const ticker = setInterval(() => setNow(Date.now()), 1_000)

    const unSidebar = context.ui.slot({
      append: "sidebar.content",
      render: ({ sessionID }: { sessionID?: string }) => {
        const rows = () => (sessionID ? sidebarRows(state(), sessionID, now()) : [])
        return (
          <Show when={rows().length > 0}>
            <box flexDirection="column">
              <text fg={context.theme.text.base}>Background tasks</text>
              <For each={rows()}>
                {(row) => (
                  <box flexDirection="column">
                    <text fg={context.theme.text.base}>{row.main}</text>
                    <Show when={row.notice}>
                      <text fg={context.theme.text.base}>{row.notice}</text>
                    </Show>
                  </box>
                )}
              </For>
            </box>
          </Show>
        )
      },
    })

    return () => {
      clearInterval(ticker)
      unSidebar?.()
      stops.forEach((stop: () => void) => stop())
      unslot?.()
    }
  },
})
