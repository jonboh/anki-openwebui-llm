# anki-nvim-llm configuration

## `nvim_socket`
Path to the Unix socket used for the dedicated Neovim window.

Leave empty to use the default: `~/.local/share/anki-nvim-llm/nvim.sock`

The addon manages this socket itself — you do not need to start Neovim manually.
On first use a new terminal window is spawned running:
```
<editor> --listen <socket> <chat-file>
```
On subsequent card sends the addon detects the socket is alive and sends the
new chat file to the existing window instead of opening another one.

---

## `editor`
The Neovim-compatible binary to use. Leave empty to default to `nvim`.

Set this if your Neovim is not on `PATH` as `nvim` — for example a nixvim
wrapper with a different name:

```json
"editor": "mynixvim"
```

Used both for `--server` remote calls to an existing session and for spawning
a new window.

---

## `terminal`
Terminal emulator used to open the dedicated Neovim window.

Leave empty to auto-detect from a built-in list (kitty, alacritty, wezterm,
foot, gnome-terminal, xfce4-terminal, konsole, xterm, …).

Set explicitly if auto-detection picks the wrong one, e.g. `"kitty"`.

---

## `gp_chat_dir`
Directory where gp.nvim stores its chat files.

Leave empty to use the default: `~/.local/share/nvim/gp/chats/`

Must match the `chat_dir` you have configured in gp.nvim.

---

## `agent`
The gp.nvim agent name to activate when opening the chat.

Must exactly match one of the agent `name` values in your gp.nvim config.
From your nixvim setup the available chat agents are:

- `"AnkiClaude-Sonnet"` (default) — dedicated tutor agent for this plugin
- `"ChatClaude-Sonnet-4-6"`
- `"ChatClaude-Opus-4-6"`
- `"ChatGPT5.4"`
- `"ChatGPT5.4-mini"`

> **Note:** The `model` / `provider` fields that gp.nvim writes into chat files
> are metadata only — the active agent controls which model actually responds.
> This plugin sets the agent explicitly rather than relying on whatever was last
> active in the session.

---

## `system_prompt`
The role / system message placed at the top of each chat.

---

## Shortcut

`Ctrl+G` while in the reviewer sends the current card to gp.nvim.
