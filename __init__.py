"""
anki-nvim-llm — Send the current review card to a gp.nvim chat in Neovim.

Workflow
--------
Ctrl+G  — Open the persistent chat for the current card (created on first use,
           keyed by card ID so it survives card edits). Conversation history is
           preserved across sessions.
Ctrl+Shift+G — Force-create a new chat file for the current card, regardless of
           whether a previous one exists.

In both cases:
- If the dedicated Neovim window is already open (socket alive), the file is
  sent there and reused.
- If not, a new terminal window is spawned running the editor with --listen so
  future cards are sent to the same session.
"""

import html
import os
import re
import shutil
import subprocess

from aqt import gui_hooks, mw
from aqt.utils import tooltip


# ---------------------------------------------------------------------------
# HTML → light markdown
# ---------------------------------------------------------------------------

def _html_to_markdown(raw: str) -> str:
    """Best-effort conversion of Anki card HTML to readable markdown text."""
    if not raw:
        return ""

    text = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
    text = re.sub(r"</?(p|div|li|tr)[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?ul[^>]*>|</?ol[^>]*>", "\n", text, flags=re.IGNORECASE)

    text = re.sub(r"<b[^>]*>(.*?)</b>", r"**\1**", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<strong[^>]*>(.*?)</strong>", r"**\1**", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<i[^>]*>(.*?)</i>", r"*\1*", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<em[^>]*>(.*?)</em>", r"*\1*", text, flags=re.IGNORECASE | re.DOTALL)

    text = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<pre[^>]*>(.*?)</pre>", r"\n```\n\1\n```\n", text, flags=re.IGNORECASE | re.DOTALL)

    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _config() -> dict:
    return mw.addonManager.getConfig(__name__) or {}


def _gp_chat_dir() -> str:
    d = _config().get("gp_chat_dir", "")
    return os.path.expanduser(d) if d else os.path.expanduser("~/.local/share/nvim/gp/chats")


def _addon_socket() -> str:
    """Path to the dedicated socket for the addon-owned Neovim window."""
    s = _config().get("nvim_socket", "")
    if s:
        return os.path.expanduser(s)
    state_dir = os.path.expanduser("~/.local/share/anki-nvim")
    os.makedirs(state_dir, exist_ok=True)
    return os.path.join(state_dir, "nvim.sock")


def _editor() -> str:
    """Return the editor binary from config, defaulting to 'nvim'."""
    return _config().get("editor", "") or "nvim"


def _terminal() -> str | None:
    """Return the terminal from config, or auto-detect one."""
    t = _config().get("terminal", "")
    if t:
        return t

    candidates = [
        "kitty", "alacritty", "wezterm", "foot",
        "x-terminal-emulator", "gnome-terminal", "xfce4-terminal",
        "konsole", "urxvt", "rxvt", "xterm",
    ]
    for t in candidates:
        if shutil.which(t):
            return t
    return None


# ---------------------------------------------------------------------------
# gp.nvim chat-file management
# ---------------------------------------------------------------------------

def _card_chat_paths(card_id: int) -> list[str]:
    """
    Return all existing chat files for *card_id*, sorted by counter ascending.
    Files are named anki-<card_id>-<N>.md (N is a positive integer).
    """
    chat_dir = _gp_chat_dir()
    os.makedirs(chat_dir, exist_ok=True)
    prefix = f"anki-{card_id}-"
    results = []
    for name in os.listdir(chat_dir):
        if name.startswith(prefix) and name.endswith(".md"):
            stem = name[len(prefix):-3]
            if stem.isdigit():
                results.append((int(stem), os.path.join(chat_dir, name)))
    results.sort(key=lambda t: t[0])
    return [path for _, path in results]


def _next_chat_path(card_id: int) -> str:
    """Return the path for the next counter file for *card_id*."""
    existing = _card_chat_paths(card_id)
    if not existing:
        n = 1
    else:
        last = os.path.basename(existing[-1])          # anki-<id>-N.md
        n = int(last[len(f"anki-{card_id}-"):-3]) + 1
    return os.path.join(_gp_chat_dir(), f"anki-{card_id}-{n}.md")


def _write_chat_file(filepath: str, card_content: str) -> None:
    """Write a fresh gp.nvim chat file to *filepath*."""
    filename = os.path.basename(filepath)
    cfg = _config()
    system = cfg.get(
        "system_prompt",
        "You are a knowledgeable tutor helping a student understand the Anki card shown below.",
    )

    # Card content must live inside the 💬: block — gp.nvim only sends
    # message-block content to the API; anything before the first 💬: is
    # treated as file metadata and excluded from the conversation.
    content = (
        f"# topic: ?\n\n"
        f"- file: {filename}\n"
        f"- role: {system}\n\n"
        f"---\n\n"
        f"\U0001f4ac:\n"
        f"**Card content:**\n\n"
        f"{card_content}\n\n"
        f"---\n\n"
        f"My question: "
    )

    with open(filepath, "w", encoding="utf-8") as fh:
        fh.write(content)


def _ensure_chat_file(card_id: int, card_content: str, force_new: bool) -> str:
    """
    Return the path to the chat file to open, creating it if necessary.

    force_new=False: open the highest-numbered anki-<card_id>-N.md, creating
                     anki-<card_id>-1.md if no file exists yet.
    force_new=True:  always create anki-<card_id>-(N+1).md.
    """
    if force_new:
        filepath = _next_chat_path(card_id)
        _write_chat_file(filepath, card_content)
        return filepath

    existing = _card_chat_paths(card_id)
    if existing:
        return existing[-1]   # latest conversation, not rewritten

    filepath = _next_chat_path(card_id)   # creates -1.md
    _write_chat_file(filepath, card_content)
    return filepath


# ---------------------------------------------------------------------------
# Neovim communication
# ---------------------------------------------------------------------------

def _try_remote_open(filepath: str, socket: str) -> bool:
    """
    Ask an already-running Neovim (listening on *socket*) to open *filepath*
    in a new tab via gp.open_buf(), set the agent, then drop into insert mode.
    Returns True if the command succeeded.
    """
    agent = _config().get("agent", "AnkiClaude-Sonnet")

    lua = (
        f"local gp = require('gp'); "
        f"gp.open_buf('{filepath}', gp.BufTarget.tabnew, nil, false); "
        f"gp.cmd.Agent({{args = '{agent}'}}); "
        f"vim.schedule(function() vim.api.nvim_feedkeys('Go', 'n', true) end)"
    )
    try:
        result = subprocess.run(
            [_editor(), "--server", socket, "--remote-send", f"<C-\\><C-n>:lua {lua}<CR>"],
            timeout=3,
            capture_output=True,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _spawn_nvim_window(filepath: str, socket: str) -> bool:
    """
    Open a new terminal window running Neovim with *filepath* pre-loaded and
    listening on *socket* so future cards can be sent to the same session.
    """
    terminal = _terminal()
    if terminal is None:
        tooltip(
            "Could not find a terminal emulator. "
            "Set \"terminal\" in the addon config."
        )
        return False

    agent = _config().get("agent", "AnkiClaude-Sonnet")
    nvim_args = [
        _editor(), "--listen", socket,
        "-c", f"lua require('gp').cmd.Agent({{args = '{agent}'}})",
        "-c", "lua vim.schedule(function() vim.api.nvim_feedkeys('Go', 'n', true) end)",
        filepath,
    ]

    terminal_bin = terminal.split()[0]

    if terminal_bin in ("kitty", "alacritty", "foot", "st", "urxvt", "rxvt", "xterm", "uxterm"):
        cmd = [terminal, "--"] + nvim_args
    elif terminal_bin == "wezterm":
        cmd = [terminal, "start", "--"] + nvim_args
    elif terminal_bin in ("gnome-terminal", "xfce4-terminal", "mate-terminal"):
        cmd = [terminal, "--"] + nvim_args
    elif terminal_bin == "konsole":
        cmd = [terminal, "-e"] + nvim_args
    else:
        cmd = [terminal, "-e"] + nvim_args

    try:
        subprocess.Popen(
            cmd,
            stdin=None,
            stdout=None,
            stderr=None,
            start_new_session=True,
        )
        return True
    except (FileNotFoundError, OSError):
        return False


def _open_in_nvim(filepath: str):
    socket = _addon_socket()

    if os.path.exists(socket) and _try_remote_open(filepath, socket):
        tooltip("Card chat opened — switch to your Neovim window!")
        return

    # Socket file may be stale — remove it so the editor can bind cleanly.
    if os.path.exists(socket):
        try:
            os.remove(socket)
        except OSError:
            pass

    if _spawn_nvim_window(filepath, socket):
        tooltip("Opened Neovim window with card chat — ask away!")
    else:
        tooltip(
            f"Chat file written to:\n{filepath}\n"
            "Could not open Neovim. Check the \"terminal\" config option."
        )


# ---------------------------------------------------------------------------
# Card content extraction
# ---------------------------------------------------------------------------

def _extract_card_markdown(card) -> str:
    note = mw.col.get_note(card.nid)
    model = note.note_type()

    sections = []
    for field in model["flds"]:
        name = field["name"]
        md = _html_to_markdown(note[name])
        if md:
            sections.append(f"**{name}**\n\n{md}")

    return "\n\n---\n\n".join(sections)


# ---------------------------------------------------------------------------
# Main actions
# ---------------------------------------------------------------------------

def _open_card_chat(force_new: bool):
    if mw.state != "review" or not mw.reviewer.card:
        tooltip("No card is currently being reviewed.")
        return

    card = mw.reviewer.card
    card_md = _extract_card_markdown(card)
    filepath = _ensure_chat_file(card.id, card_md, force_new)
    _open_in_nvim(filepath)


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
