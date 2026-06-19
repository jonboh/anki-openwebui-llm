# anki-openui-llm configuration

## `open_webui_url`

Base URL of your Open WebUI instance.

Default: `https://eva-chat.jonboh.dev`

Set this to the URL of your Open WebUI server. The addon creates chat
sessions here and opens your browser to this URL when you press the shortcut.

---

## `open_webui_api_key_command`

A shell command that prints the Open WebUI API key to stdout.

**Required.** The addon will not work without a valid key.

Example commands:

| Setup | Value |
|---|---|
| `pass` | `pass show eva-chat/anki-api-key` |
| `sops` | `sops -d /run/secrets/anki-openui-key` |
| Static file (via SOPS) | `cat /run/secrets/anki-openui-api-key` |

The command is run via ``shell=True`` with a 5-second timeout.  The
first line of stdout (trimmed) is used as the bearer token.  Because
the secret comes from a command rather than config.json, it never
enters the Nix store.

---

## `system_prompt`

The system message injected at the start of every new chat session.

Default:
```
You are a knowledgeable tutor helping a student understand
the Anki card shown below. Respond with clear explanations,
use examples, and render any mathematical expressions in
LaTeX notation so they display correctly.
```

Change this if you want a different tone, language, or role. For example,
to make responses more concise:

```json
"system_prompt": "You are a terse tutor. Answer in 1–2 sentences. Use LaTeX for all math."
```

---

## Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+G` | Open (or reuse) the persistent Open WebUI chat for the current card |
| `Ctrl+Shift+G` | Force-create a fresh chat session for the current card |

On first use a new persistent chat is created via the Open WebUI API.
Your default browser opens to that chat's URL so you can ask follow-ups
in the full KaTeX-enabled interface.

The card → chat mapping is saved locally at
`~/.local/share/anki-openui-llm/chats.json` so it survives Anki restarts.
