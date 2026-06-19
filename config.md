# anki-openui-llm configuration

## `open_webui_url`

Base URL of your Open WebUI instance.

Default: `https://eva-chat.jonboh.dev`

Set this to the URL of your Open WebUI server. The addon creates chat
sessions here and opens your browser to this URL when you press the shortcut.

---

## `open_webui_api_key_env`

Path to a ``KEY=value`` env file containing ``OPEN_WEBUI_API_KEY=***.

Leave empty if you don't need API auth.

The file is parsed at runtime — simple ``KEY=value`` lines, one per
line.  Typical use with SOPS:

```nix
# In your NixOS module for the addon:
open_webui_api_key_env = "/run/secrets/anki-openui-env";
```

where ``anki-openui-env`` is a SOPS-encrypted dotenv file containing:

```env
OPEN_WEBUI_API_KEY=sk-...
```

Because the env file is decrypted by SOPS at deploy time and the config
only holds a path, the secret never enters the Nix store.

---

## `model`

The Open WebUI model to use when creating chat sessions.

Default: `"default"`

Set this to any model name your Open WebUI instance supports — e.g.,
`"gpt-4o"`, `"claude-sonnet-4"`, or a custom model. The value is passed
directly in the chat creation API request.

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