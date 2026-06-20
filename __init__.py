"""
anki-openui-llm — Send the current review card to Open WebUI for LLM chat.

Workflow
--------
Ctrl+G       — Open the persistent Open WebUI chat for the current card
               (created on first use, keyed by card ID). Conversation history
               is preserved in Open WebUI across sessions.
Ctrl+Shift+G — Always create a fresh Open WebUI chat for the current card.

On first use, a new persistent chat session is created via the Open WebUI API
with the card content as the initial message.  Your default browser opens to
that chat's URL so you can ask follow-ups in Open WebUI's full KaTeX-enabled
interface.

Requirements
------------
- A running Open WebUI instance (default: https://eva-chat.jonboh.dev)
- An API key with write access to create chat sessions
  Generate one in Open WebUI Settings → Account → API Keys
"""

import html
import json
import os
import re
import time
import uuid
import urllib.error
import urllib.request
import webbrowser

from aqt import gui_hooks, mw
from aqt.utils import tooltip


# ---------------------------------------------------------------------------
# HTML → light markdown
# ---------------------------------------------------------------------------

def _html_to_markdown(raw: str) -> str:
    """Best-effort conversion of Anki card HTML to readable markdown text.

    Preserves **bold**, *italic*, `` code ``, fenced code blocks with
    their language hint, and line breaks.  Drops unknown tags and
    unescapes HTML entities.

    Anki cards use highlight.js style ``<pre><code class="language-X">``
    — the language tag is extracted so Open WebUI can colour the syntax.
    """
    if not raw:
        return ""

    text = raw

    # 1. Fenced code blocks first — before the inline <code> rule fires.
    #    Match <pre><code class="language-XXX"> ... </code></pre>
    text = re.sub(
        r"<pre[^>]*>\s*<code[^>]*class=\"language-(\w+)\"[^>]*>(.*?)</code>\s*</pre>",
        r"\n```\1\n\2\n```\n",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    #    Match <pre><code> ... </code></pre> without language hint
    text = re.sub(
        r"<pre[^>]*>\s*<code[^>]*>(.*?)</code>\s*</pre>",
        r"\n```\n\1\n```\n",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    #    Catch any remaining bare <pre> that wasn't wrapped in <code>
    text = re.sub(
        r"<pre[^>]*>(.*?)</pre>",
        r"\n```\n\1\n```\n",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # 2. Line-break tags
    text = re.sub(r"<br\s*/?>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(p|div|li|tr)[^>]*>\s*", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?ul[^>]*>|</?ol[^>]*>\s*", "\n", text, flags=re.IGNORECASE)

    # 2.5 Block math — Anki's MathJax stores display math either as
    #     <anki-mathjax block="true"> or as literal \[...\] in the field.
    #     Both need \n\n isolation so Open WebUI renders them as display.
    text = re.sub(
        r"<anki-mathjax\s+block\s*=\s*[\"']true[\"'][^>]*>(.*?)</anki-mathjax>",
        r"\n\n\1\n\n",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r'\s*\\\[(.+?)\\\]\s*',
        lambda m: f'\n\n\\[{m.group(1)}\\]\n\n',
        text,
        flags=re.DOTALL,
    )

    # 2.6 Inline math — just strip tags, keep content as-is
    text = re.sub(
        r"<anki-mathjax>(.*?)</anki-mathjax>",
        r"\1",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # 3. Inline formatting
    text = re.sub(r"<b[^>]*>(.*?)</b>", r"**\1**", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<strong[^>]*>(.*?)</strong>", r"**\1**", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<i[^>]*>(.*?)</i>", r"*\1*", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<em[^>]*>(.*?)</em>", r"*\1*", text, flags=re.IGNORECASE | re.DOTALL)

    # 4. Inline code (safe now — fenced blocks were already removed)
    text = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", text, flags=re.IGNORECASE | re.DOTALL)

    # 5. Cleanup: strip remaining HTML, unescape entities, normalise whitespace
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _config() -> dict:
    return mw.addonManager.getConfig(__name__) or {}


def _state_file() -> str:
    """Path to the JSON file mapping card IDs to Open WebUI chat IDs.

    Lives under ~/.local/share/anki-openui-llm/ so it survives restarts.
    """
    state_dir = os.path.expanduser("~/.local/share/anki-openui-llm")
    os.makedirs(state_dir, exist_ok=True)
    return os.path.join(state_dir, "chats.json")


def _load_state() -> dict:
    """Load card → {chat_id, title} mapping from disk."""
    path = _state_file()
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_state(state: dict) -> None:
    """Persist card → chat mapping to disk."""
    with open(_state_file(), "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)


# ---------------------------------------------------------------------------
# Open WebUI API
# ---------------------------------------------------------------------------

def _open_webui_url() -> str:
    """Base URL of the Open WebUI instance (no trailing slash)."""
    url = _config().get("open_webui_url", "https://eva-chat.jonboh.dev")
    return url.rstrip("/")


def _api_key() -> str:
    """Read the API key from a SOPS-managed env file.

    Looks for ``OPEN_WEBUI_API_KEY=value`` in the file pointed to by
    ``open_webui_api_key_env`` in config.json.  The file is parsed as
    simple ``KEY=value`` lines (no quoting, no continuation).
    """
    env_path = _config().get("open_webui_api_key_env", "")
    if not env_path:
        return ""
    path = os.path.expanduser(env_path)
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("OPEN_WEBUI_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def _api_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    key = _api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _system_prompt() -> str:
    return _config().get(
        "system_prompt",
        "You are a knowledgeable tutor helping a student understand "
        "the Anki card shown below. Respond with clear explanations, "
        "use examples, and render any mathematical expressions in "
        "LaTeX notation so they display correctly.",
    )


def _model() -> str:
    """Open WebUI model name to use for chat sessions."""
    return _config().get("model", "hermes-agent")


def _create_chat_session(card_content: str, title: str = "Anki card") -> str | None:
    """Create a new persistent chat session on Open WebUI.

    The card content is embedded as the first user message so it's visible
    in the conversation history.

    Returns the Open WebUI chat *id* on success, *None* on failure.
    """
    model_name = _model()
    chat_id = str(uuid.uuid4())
    sys_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())

    payload = json.dumps({
        "chat": {
            "id": chat_id,
            "title": title,
            "models": [model_name],
            "params": {},
            "history": {
                "messages": {
                    sys_id: {
                        "id": sys_id,
                        "parentId": None,
                        "childrenIds": [user_id],
                        "role": "system",
                        "content": _system_prompt(),
                    },
                    user_id: {
                        "id": user_id,
                        "parentId": sys_id,
                        "childrenIds": [],
                        "role": "user",
                        "content": (
                            "Here is an Anki card I'm reviewing. "
                            "Please help me understand it.\n\n"
                            f"{card_content}"
                        ),
                    },
                },
                "currentId": user_id,
            },
            "tags": [],
            "timestamp": int(time.time() * 1000),
        },
    }).encode()

    url = f"{_open_webui_url()}/api/v1/chats/new"
    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers=_api_headers(),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("id")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        tooltip(f"Open WebUI error ({e.code}): {body[:120]}")
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        tooltip(f"Could not reach Open WebUI: {e}")
    return None


def _get_chat_title(chat_id: str) -> str | None:
    """Fetch an existing chat's title from Open WebUI.

    Used when re-opening a previous chat to show the user its topic.
    Returns None if the chat can't be fetched (may have been deleted).
    """
    url = f"{_open_webui_url()}/api/v1/chats/{chat_id}"
    try:
        req = urllib.request.Request(url, headers=_api_headers(), method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("title")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def _open_in_browser(chat_id: str) -> None:
    """Open the Open WebUI chat page in the user's default browser."""
    url = f"{_open_webui_url()}/c/{chat_id}"
    webbrowser.open(url)


# ---------------------------------------------------------------------------
# Card content extraction
# ---------------------------------------------------------------------------

def _extract_card_markdown(card) -> str:
    """Convert every field of the current card to readable markdown.

    Fields are rendered as **FieldName** followed by the converted content,
    separated by horizontal rules.  LaTeX in Anki's ``\\( ... \\)`` or
    ``\\[ ... \\]`` notation passes through unchanged so Open WebUI's
    KaTeX renderer can display it.
    """
    note = mw.col.get_note(card.nid)
    model = note.note_type()

    sections = []
    for field in model["flds"]:
        name = field["name"]
        md = _html_to_markdown(note[name])
        if md:
            sections.append(f"**{name}**\n\n{md}")

    return "\n\n---\n\n".join(sections)


def _get_card_title(card) -> str:
    """Produce a short title from the card's first field (typically Front).

    Strips HTML tags so you get clean text like "Adjunction — definition"
    instead of "Anki card".  Falls back to "Anki card" if the field is
    empty or the card has no fields.
    """
    note = mw.col.get_note(card.nid)
    model = note.note_type()
    flds = model.get("flds", [])
    if not flds:
        return "Anki card"

    raw = note[flds[0]["name"]]
    text = re.sub(r"<[^>]+>", "", raw)
    text = html.unescape(text).strip()
    if not text:
        return "Anki card"

    # Truncate to ~80 chars, prefer a clean word boundary at the cut.
    if len(text) > 80:
        text = text[:77].rsplit(" ", 1)[0] + "…"
    return text


# ---------------------------------------------------------------------------
# Main actions
# ---------------------------------------------------------------------------

def _open_card_chat(force_new: bool) -> None:
    """Core action: create or reuse an Open WebUI chat for the current card."""

    # --- preflight ---------------------------------------------------------
    if mw.state != "review" or not mw.reviewer.card:
        tooltip("No card is currently being reviewed.")
        return

    if not _api_key():
        tooltip(
            "Open WebUI API key not configured.\n"
            "Set \"open_webui_api_key_env\" in the addon config."
        )
        return

    card = mw.reviewer.card
    card_title = _get_card_title(card)
    card_md = _extract_card_markdown(card)

    # --- try to reuse an existing chat ------------------------------------
    if not force_new:
        state = _load_state()
        card_key = str(card.id)
        entry = state.get(card_key)

        if entry is not None:
            chat_id = entry.get("chat_id")
            # Verify the chat still exists on the server
            if chat_id and _get_chat_title(chat_id) is not None:
                _open_in_browser(chat_id)
                tooltip("Reopening your previous chat for this card.")
                return

            # Chat was deleted on the server — remove stale mapping
            state.pop(card_key, None)
            _save_state(state)

    # --- create a new chat ------------------------------------------------
    chat_id = _create_chat_session(card_md, card_title)
    if chat_id is None:
        tooltip(
            "Could not create Open WebUI chat.\n"
            "Is the instance running and the API key valid?"
        )
        return

    # Persist the mapping
    state = _load_state()
    state[str(card.id)] = {
        "chat_id": chat_id,
        "title": card_title,
    }
    _save_state(state)

    _open_in_browser(chat_id)
    tooltip("Card sent to Hermes Chat – ask away!")


def open_card_chat():
    """Ctrl+G — open (or reuse) the persistent chat for the current card."""
    _open_card_chat(force_new=False)


def open_card_chat_new():
    """Ctrl+Shift+G — always create a fresh chat for the current card."""
    _open_card_chat(force_new=True)


# ---------------------------------------------------------------------------
# Shortcut registration
# ---------------------------------------------------------------------------

def _add_reviewer_shortcuts(state, shortcuts):
    if state == "review":
        shortcuts.append(("Ctrl+G", open_card_chat))
        shortcuts.append(("Ctrl+Shift+G", open_card_chat_new))


gui_hooks.state_shortcuts_will_change.append(_add_reviewer_shortcuts)
