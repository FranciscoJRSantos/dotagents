import { Plugin } from "@opencode/plugin/tui"
import { createSignal, For, Show } from "solid-js"
import { BgTasks } from "./rpc.ts"
import { errorText, killSelected, pickerOptions } from "./picker.ts"
import { attentionFor, footerText, reduce, sidebarRows, toastFor, type UiAction, type UiState } from "./tui-state.ts"

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

    const flashTimers = new Map<string, ReturnType<typeof setTimeout>>()
    const stops = (["started", "matched", "exited", "notified"] as const).map((name) =>
      (rpc.events as any).on(name, (event: { data: any }) => {
        const action = { type: name, ...event.data } as UiAction
        apply(action)
        const toast = toastFor(action as any)
        if (toast) context.ui.toast.show({ title: "Background task", ...toast })
        const attention = attentionFor(action as any)
        if (attention) {
          void context.attention
            .notify({ ...attention, notification: { when: "blurred" } })
            .catch((err: unknown) => console.error("bg-tasks attention:", err))
        }
        if (name === "exited" && event.data.reason !== "reload") {
          const id = event.data.task.id
          clearTimeout(flashTimers.get(id))
          flashTimers.set(
            id,
            setTimeout(() => {
              flashTimers.delete(id)
              apply({ type: "flash-expired", taskID: id })
            }, FLASH_MS),
          )
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

    const currentSession = () => {
      const route = context.ui.router.current() as { type?: string; sessionID?: string } | undefined
      return route?.type === "session" ? route.sessionID : undefined
    }

    async function openPicker() {
      const options = pickerOptions(state(), currentSession(), Date.now())
      if (options.length === 0) {
        context.ui.toast.show({ title: "Background tasks", message: "No background tasks in this session", variant: "warning" })
        return
      }
      const id = await context.ui.dialog.select({
        title: "Background tasks  (enter: log tail, ctrl+k: kill)",
        options,
        actions: [
          {
            bind: "ctrl+k",
            title: "Kill",
            onTrigger: async (value: string) => {
              context.ui.dialog.clear() // settle the picker first so a later Enter cannot race the kill
              const toast = await killSelected(rpc as any, state(), value)
              context.ui.toast.show({ title: "Background task", ...toast })
            },
          },
        ],
      } as any)
      if (!id) return
      let text = ""
      try {
        text = (await rpc.output({ id: id as string, bytes: 4_000 })).text
      } catch (err) {
        text = `could not read log: ${errorText(err)}`
      }
      await context.ui.dialog.alert({ title: `bg task ${id}`, message: text || "(no output yet)" })
      await openPicker()
    }

    context.keymap.layer(() => ({
      mode: "global",
      commands: [
        {
          id: "bg-tasks.open",
          title: "Background tasks",
          group: "Background tasks",
          palette: true,
          slash: { name: "bg" },
          run: () => void openPicker().catch((err) => console.error("bg-tasks picker:", err)),
        },
      ],
    }))

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
      flashTimers.forEach(clearTimeout)
      clearInterval(ticker)
      unSidebar?.()
      stops.forEach((stop: () => void) => stop())
      unslot?.()
    }
  },
})
