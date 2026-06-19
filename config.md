# anki-openui-llm configuration

## `open_webui_url`

Base URL of your Open WebUI instance.

Default: `https://eva-chat.jonboh.dev`

Set this to the URL of your Open WebUI server. The addon creates chat
sessions here and opens your browser to this URL when you press the shortcut.

---

## `open_webui_api_key`

API key for authenticating with Open WebUI.

**Required.** The addon will not work without a valid API key.

Generate one in Open WebUI:
1. Click your avatar → **Settings** → **Account**
2. Scroll to **API Keys** → **Generate API Key**
3. Copy the key and paste it here

This key is stored in your Anki profile and never sent anywhere except to
your Open WebUI instance.

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
