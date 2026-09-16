#!/usr/bin/env python3
"""nvim-keys — GTK4 window listing every Neovim keymap, grouped by plugin.

Left pane: sources in sections (yours, Neovim, plugins).
Right pane: keymaps, human-readable, with the original vim notation below.
Top: search across key, description, plugin and command, a language switch
(EN/RU) and a capture mode that answers "what does this chord do?".
"""

from __future__ import annotations

import json
import locale
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk, Pango  # noqa: E402

APP_ID = "dev.local.nvim-keys"

CACHE = Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else os.path.expanduser("~/.cache/nvim-keys/keymaps.json")
)

CONFIG_DIR = Path(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
) / "nvim-keys"
SETTINGS = CONFIG_DIR / "gui.json"


def find_dumper() -> str:
    """Locate the nvim-keys script: next to this file, or in PATH."""
    sibling = Path(__file__).resolve().parent.parent / "bin" / "nvim-keys"
    if sibling.exists():
        return str(sibling)
    installed = Path(os.path.expanduser("~/.local/bin/nvim-keys"))
    if installed.exists():
        return str(installed)
    return "nvim-keys"


DUMPER = find_dumper()

# ── i18n ────────────────────────────────────────────────────────────────────

STRINGS = {
    "en": {
        "title": "Neovim keymaps",
        "search": "Search: key, command, plugin…",
        "all_modes": "All modes",
        "all_sources": "All sources",
        "$config": "My config",
        "$neovim": "Neovim built-ins",
        "$other": "Other",
        "$recipes": "Recipes",
        "group_mine": "Mine",
        "group_builtin": "Neovim",
        "group_plugins": "Plugins",
        "group_other": "Other",
        "needs": "needs {plugin}",
        "example_tip": "Example: {example}",
        "refresh": "Rebuild the list (Ctrl+R)",
        "help": "How to read the notation (F1)",
        "lang_tip": "Language of the interface and descriptions",
        "capture_tip": "What does this chord do? (Ctrl+K)",
        "capture_hint": "Press a chord — Backspace erases, Esc leaves",
        "capture_empty": "Press the keys…",
        "capture_status": "Chord: {seq} · {shown} matches · Esc — leave",
        "capture_loose": "Chord: {seq} · nothing is mapped to it, {shown} mentions",
        "leader": "Leader",
        "space": "Space",
        "empty_title": "Nothing found",
        "empty_body": "Change the query or pick another source",
        "no_desc": "(no description)",
        "shown": "Showing {shown} of {total} · {scope} · {stamp}",
        "updated": "updated {stamp}",
        "no_cache": "cache not built",
        "copied": "Copied: {text}",
        "rebuilding": "Rebuilding… (headless Neovim is running)",
        "rebuild_failed": "Rebuild failed: {err}",
        "lazy": "lazy",
        "lazy_tip": "Plugin loads on first use of this key",
        "seq_tip": "Press the keys one after another",
        "copy_tip": "Enter / double click — copy the key",
        "notation": "vim notation: {lhs}  ·  mode: {mode}",
        "help_title": "How to read the notation",
        "help_body": (
            "Chips on the left are the actual key presses. The › between them means "
            "the keys are pressed one after another, not together.\n\n"
            "Greyed out under the description is the source of the mapping and the "
            "original notation from your Neovim config:\n"
            "  <C-x> — Ctrl+X\n"
            "  <M-x>, <A-x> — Alt+X\n"
            "  <S-x> — Shift+X\n"
            "  <D-x> — Super\n"
            "  <leader> — the leader key, yours is {leader}\n"
            "  <CR>, <BS>, <Esc>, <Tab> — Enter, Backspace, Esc, Tab\n"
            "  <C-W> is plain Ctrl+W: Neovim uppercases Ctrl chords, real Shift is "
            "spelled out as <C-S-w>\n\n"
            "Modes:\n"
            "  n — normal, i — insert, v/x/s — visual and select,\n"
            "  o — operator pending (after d, y, c), t — terminal, c — command line\n\n"
            "Ctrl+K — capture mode: press a chord and the list shows what it does "
            "in Neovim. Backspace erases the last press, Esc leaves the mode.\n\n"
            "EN/RU switches the language of the interface and of the descriptions. "
            "Descriptions that come from plugins are translated by a dictionary; "
            "untranslated ones stay in English.\n\n"
            "“Recipes” in the source list is a hand-written cheatsheet: jumps, "
            "search, undo and file operations, each with an example. Rows starting "
            "with “:” are Ex commands — type them in the command line and press "
            "Enter.\n\n"
            "Enter — copy the key, Ctrl+R — rebuild, Esc — close."
        ),
        "help_ok": "Got it",
    },
    "ru": {
        "title": "Сочетания клавиш Neovim",
        "search": "Поиск: клавиша, команда, плагин…",
        "all_modes": "Все режимы",
        "all_sources": "Все источники",
        "$config": "Моя конфигурация",
        "$neovim": "Neovim (встроенные)",
        "$other": "Прочее",
        "$recipes": "Приёмы",
        "group_mine": "Моё",
        "group_builtin": "Neovim",
        "group_plugins": "Плагины",
        "group_other": "Прочее",
        "needs": "нужен {plugin}",
        "example_tip": "Пример: {example}",
        "refresh": "Пересобрать список (Ctrl+R)",
        "help": "Как читать обозначения (F1)",
        "lang_tip": "Язык интерфейса и описаний",
        "capture_tip": "Что делает это сочетание? (Ctrl+K)",
        "capture_hint": "Нажимайте сочетание — Backspace стирает, Esc выходит",
        "capture_empty": "Нажмите клавиши…",
        "capture_status": "Сочетание: {seq} · совпадений {shown} · Esc — выйти",
        "capture_loose": "Сочетание: {seq} · маппинга нет, упоминаний {shown}",
        "leader": "Leader",
        "space": "Пробел",
        "empty_title": "Ничего не найдено",
        "empty_body": "Измените запрос или выберите другой источник",
        "no_desc": "(без описания)",
        "shown": "Показано {shown} из {total} · {scope} · {stamp}",
        "updated": "обновлено {stamp}",
        "no_cache": "кэш не собран",
        "copied": "Скопировано: {text}",
        "rebuilding": "Пересобираю список… (запущен headless nvim)",
        "rebuild_failed": "Не удалось обновить: {err}",
        "lazy": "lazy",
        "lazy_tip": "Плагин загружается по этому сочетанию",
        "seq_tip": "Нажатия идут последовательно, одно за другим",
        "copy_tip": "Enter / двойной клик — скопировать сочетание",
        "notation": "vim-запись: {lhs}  ·  режим: {mode}",
        "help_title": "Как читать обозначения",
        "help_body": (
            "Чипы слева — реальные нажатия. Знак › между ними значит, что клавиши "
            "нажимаются последовательно, а не вместе.\n\n"
            "Серым под описанием — источник сочетания и исходная запись из конфига "
            "Neovim:\n"
            "  <C-x> — Ctrl+X\n"
            "  <M-x>, <A-x> — Alt+X\n"
            "  <S-x> — Shift+X\n"
            "  <D-x> — Super (Win)\n"
            "  <leader> — leader, у тебя это {leader}\n"
            "  <CR>, <BS>, <Esc>, <Tab> — Enter, Backspace, Esc, Tab\n"
            "  <C-W> — это просто Ctrl+W: Neovim пишет Ctrl-сочетания заглавной "
            "буквой, настоящий Shift указан отдельно, как <C-S-w>\n\n"
            "Режимы:\n"
            "  n — обычный, i — вставка, v/x/s — визуальный и выделение,\n"
            "  o — ожидание объекта (после d, y, c), t — терминал, c — командная строка\n\n"
            "Ctrl+K — режим захвата: нажимаешь сочетание, список показывает, что "
            "оно делает в Neovim. Backspace стирает последнее нажатие, Esc выходит.\n\n"
            "EN/RU переключает язык интерфейса и описаний. Описания из плагинов "
            "переводятся по словарю; то, чего в словаре нет, остаётся на английском.\n\n"
            "«Приёмы» в списке источников — это шпаргалка, написанная руками: "
            "прыжки, поиск, отмена и операции с файлами, каждый пункт с примером. "
            "Строки, начинающиеся с «:», — это Ex-команды: набираются в командной "
            "строке и подтверждаются Enter.\n\n"
            "Enter — скопировать сочетание, Ctrl+R — пересобрать, Esc — закрыть."
        ),
        "help_ok": "Понятно",
    },
}

LANGS = ["en", "ru"]
LANG_LABELS = ["EN", "RU"]


def load_settings() -> dict:
    try:
        data = json.loads(SETTINGS.read_text())
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_settings(**values) -> None:
    data = load_settings()
    data.update(values)
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    except OSError:
        pass  # a read-only home is no reason to refuse to start


def pick_language() -> str:
    """Saved choice first, then the environment, then the system locale."""
    saved = load_settings().get("lang")
    if saved in STRINGS:
        return saved
    env = os.environ.get("NVIM_KEYS_LANG")
    if env in STRINGS:
        return env
    try:
        code = (locale.getlocale()[0] or os.environ.get("LANG") or "")[:2].lower()
    except (ValueError, TypeError):
        code = ""
    return code if code in STRINGS else "en"


LANG = pick_language()
T = STRINGS[LANG]


def tr(key: str, **kwargs) -> str:
    text = T.get(key, STRINGS["en"].get(key, key))
    return text.format(**kwargs) if kwargs else text


MODE_LABELS: dict[str, str] = {}
MODE_ORDER = ["all", "n", "i", "v", "x", "s", "o", "t", "c"]
NAMED_KEYS: dict[str, str] = {}


def rebuild_tables() -> None:
    """Tables that embed translated words; refreshed on every language change."""
    MODE_LABELS.clear()
    MODE_LABELS.update(
        {
            "all": tr("all_modes"),
            "n": "Normal",
            "i": "Insert",
            "v": "Visual + Select",
            "x": "Visual",
            "s": "Select",
            "o": "Operator",
            "t": "Terminal",
            "c": "Command",
        }
    )
    NAMED_KEYS.clear()
    NAMED_KEYS.update(
        {
            "cr": "Enter",
            "return": "Enter",
            "enter": "Enter",
            "esc": "Esc",
            "escape": "Esc",
            "bs": "Backspace",
            "tab": "Tab",
            "space": tr("space"),
            "del": "Delete",
            "up": "↑",
            "down": "↓",
            "left": "←",
            "right": "→",
            "home": "Home",
            "end": "End",
            "pageup": "PgUp",
            "pagedown": "PgDn",
            "insert": "Insert",
            "leader": tr("leader"),
            "localleader": "LocalLeader",
            "lt": "<",
            "nop": "—",
            "nul": "Ctrl+Space",
        }
    )


def set_language(code: str) -> None:
    global LANG, T
    LANG = code if code in STRINGS else "en"
    T = STRINGS[LANG]
    rebuild_tables()


rebuild_tables()

CSS = b"""
.keychip {
  font-family: monospace;
  font-weight: bold;
  padding: 2px 8px;
  border-radius: 6px;
  background: alpha(@accent_bg_color, 0.18);
  color: @accent_color;
}
.modechip {
  font-family: monospace;
  font-size: 0.8em;
  padding: 1px 6px;
  border-radius: 6px;
  background: alpha(currentColor, 0.10);
  opacity: 0.75;
}
.cmdchip {
  font-family: monospace;
  padding: 2px 8px;
  border-radius: 6px;
  background: alpha(currentColor, 0.12);
}
.example {
  font-family: monospace;
  font-size: 0.85em;
  opacity: 0.7;
}
.srcheader {
  font-size: 0.78em;
  font-weight: bold;
  opacity: 0.55;
  margin: 12px 10px 2px 10px;
}
.capture {
  padding: 4px 10px;
  border-radius: 8px;
  background: alpha(@accent_bg_color, 0.12);
}
.plugin-name { font-weight: bold; }
.dim { opacity: 0.6; }
"""

# ── key notation ────────────────────────────────────────────────────────────

MODIFIERS = {"C": "Ctrl", "M": "Alt", "A": "Alt", "S": "Shift", "D": "Super", "T": "Meta"}


def split_lhs(lhs: str) -> list[str]:
    """Split a mapping into single presses: 'gco' → g, c, o."""
    parts: list[str] = []
    i = 0
    while i < len(lhs):
        if lhs[i] == "<":
            close = lhs.find(">", i)
            if close != -1:
                parts.append(lhs[i : close + 1])
                i = close + 1
                continue
        parts.append(lhs[i])
        i += 1
    return parts


def humanize_key(token: str) -> str:
    """One press in human form: '<C-/>' → 'Ctrl + /', 'E' → 'Shift + E'."""
    if token.startswith("<") and token.endswith(">") and len(token) > 2:
        inner = token[1:-1]
        mods: list[str] = []
        while len(inner) > 2 and inner[1] == "-" and inner[0].upper() in MODIFIERS:
            mods.append(MODIFIERS[inner[0].upper()])
            inner = inner[2:]
        base = NAMED_KEYS.get(inner.lower(), inner)
        if mods and len(base) == 1 and base.isalpha():
            # Neovim writes Ctrl chords with a capital letter (<C-W> is Ctrl+W,
            # no Shift); a real Shift always appears as its own modifier
            base = base.upper()
        return " + ".join(mods + [base]) if mods else base
    if token == " ":
        return tr("space")
    if token.isalpha() and token.isupper():
        return f"Shift + {token}"
    return token


def humanize(lhs: str) -> list[str]:
    return [humanize_key(t) for t in split_lhs(lhs)]


# ── capturing a chord from the keyboard ─────────────────────────────────────

MODIFIER_KEYVALS = {
    Gdk.KEY_Shift_L, Gdk.KEY_Shift_R, Gdk.KEY_Control_L, Gdk.KEY_Control_R,
    Gdk.KEY_Alt_L, Gdk.KEY_Alt_R, Gdk.KEY_Super_L, Gdk.KEY_Super_R,
    Gdk.KEY_Meta_L, Gdk.KEY_Meta_R, Gdk.KEY_Hyper_L, Gdk.KEY_Hyper_R,
    Gdk.KEY_Caps_Lock, Gdk.KEY_Num_Lock, Gdk.KEY_ISO_Level3_Shift,
    Gdk.KEY_ISO_Level5_Shift, Gdk.KEY_Mode_switch,
}

SPECIAL_KEYVALS = {
    Gdk.KEY_Return: "CR",
    Gdk.KEY_KP_Enter: "CR",
    Gdk.KEY_Tab: "Tab",
    Gdk.KEY_ISO_Left_Tab: "Tab",
    Gdk.KEY_space: "Space",
    Gdk.KEY_Delete: "Del",
    Gdk.KEY_Insert: "Insert",
    Gdk.KEY_Home: "Home",
    Gdk.KEY_End: "End",
    Gdk.KEY_Page_Up: "PageUp",
    Gdk.KEY_Page_Down: "PageDown",
    Gdk.KEY_Up: "Up",
    Gdk.KEY_Down: "Down",
    Gdk.KEY_Left: "Left",
    Gdk.KEY_Right: "Right",
}


def vim_token(keyval: int, state: Gdk.ModifierType, leader: str) -> str | None:
    """A key press in Neovim notation: Ctrl+I → '<C-I>', Space → '<leader>'."""
    if keyval in MODIFIER_KEYVALS:
        return None

    mods: list[str] = []
    if state & Gdk.ModifierType.SUPER_MASK:
        mods.append("D")
    if state & Gdk.ModifierType.ALT_MASK:
        mods.append("M")
    if state & Gdk.ModifierType.CONTROL_MASK:
        mods.append("C")

    base = SPECIAL_KEYVALS.get(keyval)
    name = Gdk.keyval_name(keyval) or ""
    if base is None and re.fullmatch(r"F\d{1,2}", name):
        base = name
    shift = bool(state & Gdk.ModifierType.SHIFT_MASK)

    if base is not None:
        if base == "Space" and not mods:
            # Space is the usual leader; search for the spelled-out form
            return "<leader>" if leader.lower() in ("<space>", " ") else "<Space>"
        if shift:
            mods.append("S")
        return "<" + "-".join(mods + [base]) + ">"

    code = Gdk.keyval_to_unicode(keyval)
    if not code:
        return None
    char = chr(code)
    if not char.isprintable():
        return None
    if char == " ":
        return "<leader>" if leader.lower() in ("<space>", " ") else "<Space>"
    if not mods:
        return char
    if len(char) == 1 and char.isalpha():
        # <C-w> and <C-W> are the same press; Neovim spells it uppercase
        char = char.upper() if "C" in mods else char.lower()
        if shift and "C" in mods:
            mods.append("S")
    return "<" + "-".join(mods + [char]) + ">"


# ── descriptions ────────────────────────────────────────────────────────────


def data_files(name: str, env_var: str) -> list[Path]:
    """Shipped data file plus the user's own override, in that order."""
    paths: list[Path] = []
    env = os.environ.get(env_var)
    if env:
        paths.append(Path(env).expanduser())
    else:
        checkout = Path(__file__).resolve().parent.parent / "data" / name
        home = os.environ.get("NVIM_KEYS_HOME") or os.path.join(
            os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
            "nvim-keys",
        )
        paths.append(checkout if checkout.exists() else Path(home) / name)
    paths.append(CONFIG_DIR / name)
    return [p for p in paths if p.exists()]


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


class Descriptions:
    """Turns a raw keymap description into something a human can read."""

    def __init__(self):
        self.noise: list[re.Pattern] = []
        self.rewrite: list[tuple[re.Pattern, dict]] = []
        self.phrases: dict[str, dict[str, str]] = {}
        self.words: dict[str, dict[str, str]] = {}
        self.tails: dict[str, dict[str, str]] = {}
        self.by_key: dict[str, dict[str, str]] = {}

        for path in data_files("descriptions.json", "NVIM_KEYS_DESCRIPTIONS"):
            self._merge(read_json(path))

    def _merge(self, data: dict) -> None:
        for pat in data.get("noise", []):
            try:
                self.noise.append(re.compile(pat, re.IGNORECASE))
            except re.error:
                continue
        for entry in data.get("rewrite", []):
            try:
                self.rewrite.append((re.compile(entry["match"]), entry))
            except (re.error, KeyError):
                continue
        for keys, texts in (data.get("by_key") or {}).items():
            self.by_key.setdefault(keys, {}).update(texts)
        for lang, tables in (data.get("translations") or {}).items():
            for field, target in (
                ("phrases", self.phrases),
                ("words", self.words),
                ("tails", self.tails),
            ):
                for src, text in (tables.get(field) or {}).items():
                    target.setdefault(src.lower(), {})[lang] = text

    # ── lookup helpers ────────────────────────────────────────────────────
    def is_noise(self, desc: str) -> bool:
        return any(pat.search(desc) for pat in self.noise)

    def _rewritten(self, desc: str) -> str | None:
        for pat, entry in self.rewrite:
            m = pat.search(desc)
            if not m:
                continue
            text = entry.get(LANG) or entry.get("en") or ""
            for idx, group in enumerate(m.groups(), start=1):
                text = text.replace("{%d}" % idx, group or "")
            return text
        return None

    def _from_table(self, table: dict, key: str) -> str | None:
        return (table.get(key) or {}).get(LANG)

    def _translate_words(self, text: str) -> str | None:
        parts = re.split(r"(\W+)", text)
        out: list[str] = []
        translated = False
        for part in parts:
            if not part or not part.strip() or not part[0].isalnum():
                out.append(part)
                continue
            word = self._from_table(self.words, part.lower())
            if word is None:
                return None
            out.append(word)
            translated = True
        if not translated:
            return None
        result = "".join(out).strip()
        return result[:1].upper() + result[1:] if result else None

    def _translate(self, desc: str) -> str | None:
        """Phrase first, then phrase + trailing '(…)', then word by word."""
        exact = self._from_table(self.phrases, desc.lower())
        if exact:
            return exact

        m = re.fullmatch(r"(.+?)\s*\((.+)\)\s*", desc)
        if m:
            head, tail = m.group(1), m.group(2)
            head_ru = self._from_table(self.phrases, head.lower()) or (
                self._translate_words(head)
            )
            if head_ru:
                tail_ru = self._from_table(self.tails, tail.lower()) or tail
                return f"{head_ru} ({tail_ru})"

        return self._translate_words(desc)

    def text(self, desc: str) -> str:
        """Localized description, or '' when the raw text says nothing."""
        desc = (desc or "").strip()
        if not desc:
            return ""
        rewritten = self._rewritten(desc)
        if rewritten is not None:
            return rewritten
        if self.is_noise(desc):
            return ""
        if LANG == "en":
            return desc
        return self._translate(desc) or desc


DESCRIPTIONS = Descriptions()


def describe(item: dict) -> str:
    """What to show as the description: the desc, else the command it runs."""
    text = DESCRIPTIONS.text(item.get("desc", ""))
    if not text:
        text = DESCRIPTIONS.text(item.get("rhs", ""))
    if not text:
        known = DESCRIPTIONS.by_key.get(item.get("display", ""), {})
        text = known.get(LANG) or known.get("en", "")
    return text or tr("no_desc")


# ── data ────────────────────────────────────────────────────────────────────


def source_label(name: str) -> str:
    return tr(name) if name.startswith("$") else name


def load_keymaps() -> tuple[list[dict], str, str]:
    if not CACHE.exists():
        return [], tr("no_cache"), ""
    try:
        data = json.loads(CACHE.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return [], f"{exc}", ""
    stamp = GLib.DateTime.new_from_unix_local(int(data.get("generated_at", 0))).format(
        "%d.%m.%Y %H:%M"
    )
    return data.get("keymaps", []), tr("updated", stamp=stamp), data.get("mapleader", "")


SRC_RECIPES = "$recipes"


def pick_text(value) -> str:
    """Recipe texts are {"en": …, "ru": …}; plain strings are allowed too."""
    if isinstance(value, dict):
        return value.get(LANG) or value.get("en") or next(iter(value.values()), "")
    return value or ""


def load_recipes() -> list[dict]:
    """Hand-written cheatsheet entries, shaped like keymap rows."""
    items: list[dict] = []
    for path in data_files("recipes.json", "NVIM_KEYS_RECIPES"):
        data = read_json(path)
        for cat in data.get("categories", []):
            category = pick_text(cat.get("title"))
            for it in cat.get("items", []):
                keys = it.get("keys") or ""
                if not keys:
                    continue
                items.append(
                    {
                        "mode": it.get("mode", "n"),
                        "lhs": keys,
                        "display": keys,
                        "rhs": "",
                        "desc": pick_text(it.get("desc")),
                        "plugin": SRC_RECIPES,
                        "source": str(path),
                        "pending": False,
                        "kind": it.get("kind", "key"),
                        "example": pick_text(it.get("example")),
                        "category": category,
                        "needs": it.get("needs", ""),
                        "order": len(items),
                    }
                )
    return items


# ── source list: sections ───────────────────────────────────────────────────

SEC_ALL, SEC_MINE, SEC_BUILTIN, SEC_PLUGINS, SEC_OTHER = range(5)

SECTION_LABELS = {
    SEC_MINE: "group_mine",
    SEC_BUILTIN: "group_builtin",
    SEC_PLUGINS: "group_plugins",
    SEC_OTHER: "group_other",
}


def section_of(name: str) -> int:
    if name in ("$config", SRC_RECIPES):
        return SEC_MINE
    if name == "$neovim":
        return SEC_BUILTIN
    if name == "$other":
        return SEC_OTHER
    return SEC_PLUGINS


def sort_sources(counts: dict[str, int]) -> list[str]:
    """Grouped: your own first, then Neovim, then plugins by keymap count."""
    inner = {"$config": 0, SRC_RECIPES: 1}

    def key(name: str):
        return (
            section_of(name),
            inner.get(name, 0),
            -counts[name],
            source_label(name).lower(),
        )

    return sorted(counts, key=key)


class KeyRow(Gtk.ListBoxRow):
    def __init__(self, item: dict):
        super().__init__()
        self.item = item
        self.human = humanize(item["display"])
        self.desc = describe(item)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(10)
        box.set_margin_end(10)

        chips = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        chips.set_size_request(300, -1)
        chips.set_valign(Gtk.Align.CENTER)
        for idx, part in enumerate(self.human[:6]):
            if idx:
                sep = Gtk.Label(label="›")
                sep.add_css_class("dim")
                chips.append(sep)
            chip = Gtk.Label(label=part)
            chip.add_css_class("keychip")
            chips.append(chip)
        if len(self.human) > 6:
            more = Gtk.Label(label="…")
            more.add_css_class("dim")
            chips.append(more)
        box.append(chips)

        mode = Gtk.Label(label=item["mode"])
        mode.add_css_class("modechip")
        mode.set_tooltip_text(MODE_LABELS.get(item["mode"], item["mode"]))
        box.append(mode)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1, hexpand=True)
        desc = Gtk.Label(label=self.desc, xalign=0)
        desc.set_ellipsize(Pango.EllipsizeMode.END)
        text.append(desc)
        sub = Gtk.Label(
            label=f"{source_label(item['plugin'])} · {item['display']}", xalign=0
        )
        sub.add_css_class("dim")
        sub.set_ellipsize(Pango.EllipsizeMode.END)
        text.append(sub)
        box.append(text)

        if item.get("pending"):
            lazy = Gtk.Label(label=tr("lazy"))
            lazy.add_css_class("modechip")
            lazy.set_tooltip_text(tr("lazy_tip"))
            box.append(lazy)

        self.set_child(box)
        self.set_tooltip_text(self._tooltip())

    def _tooltip(self) -> str:
        it = self.item
        tip = [
            " › ".join(self.human),
            tr(
                "notation",
                lhs=it["display"],
                mode=MODE_LABELS.get(it["mode"], it["mode"]),
            ),
        ]
        if len(self.human) > 1:
            tip.append(tr("seq_tip"))
        tip.append(self.desc)
        rhs = it.get("rhs") or ""
        if rhs and rhs != "<lua function>":
            tip.append(f"→ {rhs}")
        src, line = it.get("source") or "", it.get("line")
        if src:
            tip.append(f"{src}:{line}" if line else src)
        tip.append(tr("copy_tip"))
        return "\n".join(tip)

    def haystack(self) -> str:
        it = self.item
        human = " ".join(self.human)
        return " ".join(
            (
                it["display"],
                it["lhs"],
                human,
                human.replace(" + ", "+"),
                self.desc,
                it.get("desc", ""),
                source_label(it["plugin"]),
                it["mode"],
                MODE_LABELS.get(it["mode"], ""),
                it.get("rhs", ""),
            )
        ).lower()


class RecipeRow(Gtk.ListBoxRow):
    """A hand-written cheatsheet entry: keys or an Ex command, plus an example."""

    def __init__(self, item: dict):
        super().__init__()
        self.item = item
        self.is_cmd = item.get("kind") == "cmd"
        self.human = [item["display"]] if self.is_cmd else humanize(item["display"])
        self.desc = item["desc"] or tr("no_desc")

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(10)
        box.set_margin_end(10)

        chips = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        chips.set_size_request(300, -1)
        chips.set_valign(Gtk.Align.CENTER)
        if self.is_cmd:
            chip = Gtk.Label(label=item["display"], xalign=0)
            chip.set_ellipsize(Pango.EllipsizeMode.END)
            chip.set_max_width_chars(34)
            chip.add_css_class("cmdchip")
            chips.append(chip)
        else:
            for idx, part in enumerate(self.human[:6]):
                if idx:
                    sep = Gtk.Label(label="›")
                    sep.add_css_class("dim")
                    chips.append(sep)
                chip = Gtk.Label(label=part)
                chip.add_css_class("keychip")
                chips.append(chip)
        box.append(chips)

        mode = Gtk.Label(label=item["mode"])
        mode.add_css_class("modechip")
        mode.set_tooltip_text(MODE_LABELS.get(item["mode"], item["mode"]))
        box.append(mode)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1, hexpand=True)
        desc = Gtk.Label(label=self.desc, xalign=0)
        desc.set_ellipsize(Pango.EllipsizeMode.END)
        text.append(desc)
        if item.get("example"):
            example = Gtk.Label(label=item["example"], xalign=0)
            example.add_css_class("example")
            example.set_ellipsize(Pango.EllipsizeMode.END)
            text.append(example)
        sub_parts = [item.get("category", "")]
        if item.get("needs"):
            sub_parts.append(tr("needs", plugin=item["needs"]))
        sub = Gtk.Label(label=" · ".join(p for p in sub_parts if p), xalign=0)
        sub.add_css_class("dim")
        sub.set_ellipsize(Pango.EllipsizeMode.END)
        text.append(sub)
        box.append(text)

        self.set_child(box)
        self.set_tooltip_text(self._tooltip())

    def _tooltip(self) -> str:
        it = self.item
        tip = [it["display"] if self.is_cmd else " › ".join(self.human)]
        if not self.is_cmd and len(self.human) > 1:
            tip.append(tr("seq_tip"))
        tip.append(self.desc)
        if it.get("example"):
            tip.append(tr("example_tip", example=it["example"]))
        if it.get("needs"):
            tip.append(tr("needs", plugin=it["needs"]))
        tip.append(tr("copy_tip"))
        return "\n".join(tip)

    def haystack(self) -> str:
        it = self.item
        human = " ".join(self.human)
        return " ".join(
            (
                it["display"],
                human,
                human.replace(" + ", "+"),
                self.desc,
                it.get("example", ""),
                it.get("category", ""),
                it.get("needs", ""),
                source_label(it["plugin"]),
                it["mode"],
                MODE_LABELS.get(it["mode"], ""),
            )
        ).lower()


class Window(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application):
        super().__init__(application=app, title=tr("title"))
        self.set_default_size(1080, 720)

        self.rows: list[KeyRow | RecipeRow] = []
        self.selected_source: str | None = None
        self.mode_filter = "all"
        self.query = ""
        self.stamp = ""
        self.leader = ""
        self.capture = False
        self.captured: list[str] = []
        self.capture_loose = False
        self._syncing = False

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)

        self.header = Adw.HeaderBar()
        self.search = Gtk.SearchEntry(hexpand=True)
        self.search.set_placeholder_text(tr("search"))
        self.search.connect("search-changed", self.on_search)
        self.search.connect("stop-search", lambda *_: self.quit_app())
        self.search.set_size_request(420, -1)

        # the title area swaps between the search entry and the captured chord
        self.capture_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=6, halign=Gtk.Align.CENTER
        )
        self.capture_box.add_css_class("capture")
        self.title_stack = Gtk.Stack()
        self.title_stack.add_named(self.search, "search")
        self.title_stack.add_named(self.capture_box, "capture")
        self.header.set_title_widget(self.title_stack)

        self.mode_drop = Gtk.DropDown.new_from_strings(
            [MODE_LABELS[m] for m in MODE_ORDER]
        )
        self.mode_drop.connect("notify::selected", self.on_mode)
        self.header.pack_end(self.mode_drop)

        self.lang_drop = Gtk.DropDown.new_from_strings(LANG_LABELS)
        self.lang_drop.set_selected(LANGS.index(LANG))
        self.lang_drop.set_tooltip_text(tr("lang_tip"))
        self.lang_drop.connect("notify::selected", self.on_lang)
        self.header.pack_end(self.lang_drop)

        self.refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        self.refresh_btn.set_tooltip_text(tr("refresh"))
        self.refresh_btn.connect("clicked", lambda *_: self.refresh())
        self.header.pack_end(self.refresh_btn)

        self.capture_btn = Gtk.ToggleButton(icon_name="input-keyboard-symbolic")
        self.capture_btn.set_tooltip_text(tr("capture_tip"))
        self.capture_btn.connect("toggled", self.on_capture_toggled)
        self.header.pack_start(self.capture_btn)

        self.help_btn = Gtk.Button(icon_name="help-about-symbolic")
        self.help_btn.set_tooltip_text(tr("help"))
        self.help_btn.connect("clicked", lambda *_: self.show_legend())
        self.header.pack_start(self.help_btn)
        root.append(self.header)

        panes = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, vexpand=True)
        panes.set_position(260)
        root.append(panes)

        self.source_list = Gtk.ListBox()
        self.source_list.add_css_class("navigation-sidebar")
        self.source_list.set_header_func(self.source_header)
        self.source_list.connect("row-selected", self.on_source)
        left = Gtk.ScrolledWindow(child=self.source_list, hexpand=False)
        left.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        panes.set_start_child(left)

        self.key_list = Gtk.ListBox()
        self.key_list.set_filter_func(self.filter_row)
        self.key_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.key_list.connect("row-activated", self.on_activate)
        self.stack = Gtk.Stack()
        self.stack.add_named(Gtk.ScrolledWindow(child=self.key_list, hexpand=True), "list")
        self.empty_page = Adw.StatusPage(
            title=tr("empty_title"),
            description=tr("empty_body"),
            icon_name="edit-find-symbolic",
        )
        self.stack.add_named(self.empty_page, "empty")
        panes.set_end_child(self.stack)

        self.status = Gtk.Label(xalign=0)
        self.status.add_css_class("dim")
        self.status.set_margin_top(4)
        self.status.set_margin_bottom(4)
        self.status.set_margin_start(12)
        root.append(self.status)

        keys = Gtk.EventControllerKey()
        # CAPTURE, otherwise Gtk.SearchEntry eats Escape (it just clears itself)
        # and the window never sees the key
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.on_key)
        self.add_controller(keys)

        self.load()
        GLib.idle_add(self.search.grab_focus)

    # ── data ──────────────────────────────────────────────────────────────
    def load(self):
        keymaps, self.stamp, self.leader = load_keymaps()
        # recipes come from a JSON file, not from the dump: no rebuild needed
        entries = keymaps + load_recipes()

        counts: dict[str, int] = {}
        for it in entries:
            counts[it["plugin"]] = counts.get(it["plugin"], 0) + 1

        keep = self.selected_source
        self.source_list.remove_all()
        self._add_source_row(None, tr("all_sources"), len(entries), SEC_ALL)
        restore = None
        for name in sort_sources(counts):
            row = self._add_source_row(
                name, source_label(name), counts[name], section_of(name)
            )
            if name == keep:
                restore = row
        self.source_list.select_row(restore or self.source_list.get_row_at_index(0))

        self.key_list.remove_all()
        self.rows = []
        for it in sorted(
            entries,
            key=lambda i: (
                source_label(i["plugin"]).lower(),
                # recipes keep the order of the file, keymaps sort by key
                i.get("order", 0),
                i["display"],
                i["mode"],
            ),
        ):
            row = RecipeRow(it) if it["plugin"] == SRC_RECIPES else KeyRow(it)
            self.rows.append(row)
            self.key_list.append(row)

        self.apply_filter()

    def _add_source_row(
        self, key: str | None, label: str, count: int, section: int
    ) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.source_key = key
        row.section = section
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(8)
        box.set_margin_end(8)
        name = Gtk.Label(label=label, xalign=0, hexpand=True)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        name.add_css_class("plugin-name")
        box.append(name)
        num = Gtk.Label(label=str(count))
        num.add_css_class("dim")
        box.append(num)
        row.set_child(box)
        self.source_list.append(row)
        return row

    def source_header(self, row: Gtk.ListBoxRow, before: Gtk.ListBoxRow | None):
        """A caption above the first row of every section."""
        section = getattr(row, "section", SEC_ALL)
        previous = getattr(before, "section", None) if before else None
        if section == SEC_ALL or section == previous:
            row.set_header(None)
            return
        label = Gtk.Label(label=tr(SECTION_LABELS[section]), xalign=0)
        label.add_css_class("srcheader")
        row.set_header(label)

    def refresh(self):
        self.status.set_text(tr("rebuilding"))

        def worker():
            try:
                subprocess.run(
                    [DUMPER, "dump"], check=True, capture_output=True, timeout=300
                )
                err = None
            except Exception as exc:  # noqa: BLE001 — surfaced to the user as text
                err = str(exc)
            GLib.idle_add(done, err)

        def done(err):
            if err:
                self.status.set_text(tr("rebuild_failed", err=err))
            else:
                self.load()
            return False

        threading.Thread(target=worker, daemon=True).start()

    # ── language ──────────────────────────────────────────────────────────
    def on_lang(self, drop: Gtk.DropDown, _param):
        if self._syncing:
            return
        code = LANGS[drop.get_selected()]
        if code == LANG:
            return
        set_language(code)
        save_settings(lang=code)
        self.retranslate()
        self.load()

    def retranslate(self):
        """Re-label everything built once at startup."""
        self._syncing = True
        self.set_title(tr("title"))
        self.search.set_placeholder_text(tr("search"))
        self.mode_drop.set_model(
            Gtk.StringList.new([MODE_LABELS[m] for m in MODE_ORDER])
        )
        self.mode_drop.set_selected(MODE_ORDER.index(self.mode_filter))
        self.lang_drop.set_tooltip_text(tr("lang_tip"))
        self.refresh_btn.set_tooltip_text(tr("refresh"))
        self.capture_btn.set_tooltip_text(tr("capture_tip"))
        self.help_btn.set_tooltip_text(tr("help"))
        self.empty_page.set_title(tr("empty_title"))
        self.empty_page.set_description(tr("empty_body"))
        self._syncing = False
        self.update_capture_box()

    # ── capture mode ──────────────────────────────────────────────────────
    def on_capture_toggled(self, button: Gtk.ToggleButton):
        if self._syncing:
            return
        self.set_capture(button.get_active())

    def set_capture(self, on: bool):
        self.capture = on
        self._syncing = True
        self.capture_btn.set_active(on)
        self._syncing = False
        self.captured = []
        self.title_stack.set_visible_child_name("capture" if on else "search")
        self.update_capture_box()
        if not on:
            GLib.idle_add(self.search.grab_focus)
        self.apply_filter()

    def update_capture_box(self):
        while child := self.capture_box.get_first_child():
            self.capture_box.remove(child)
        if not self.captured:
            hint = Gtk.Label(label=tr("capture_empty"))
            hint.add_css_class("dim")
            self.capture_box.append(hint)
            return
        for idx, token in enumerate(self.captured):
            if idx:
                sep = Gtk.Label(label="›")
                sep.add_css_class("dim")
                self.capture_box.append(sep)
            chip = Gtk.Label(label=humanize_key(token))
            chip.add_css_class("keychip")
            self.capture_box.append(chip)

    def capture_seq(self) -> str:
        return "".join(self.captured)

    def capture_variants(self) -> list[str]:
        """The chord as typed, plus the form that spells the leader out."""
        seq = self.capture_seq().lower()
        variants = {seq}
        leader = (self.leader or "").lower()
        if leader:
            variants.add(seq.replace("<leader>", leader))
            variants.add(seq.replace(leader, "<leader>"))
        return [v for v in variants if v]

    def on_capture_key(self, keyval: int, state: Gdk.ModifierType) -> bool:
        if keyval == Gdk.KEY_Escape:
            self.set_capture(False)
            return True
        if keyval in (Gdk.KEY_BackSpace, Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if keyval == Gdk.KEY_BackSpace and self.captured:
                self.captured.pop()
            elif keyval != Gdk.KEY_BackSpace:
                self.set_capture(False)
                return True
            self.update_capture_box()
            self.apply_filter()
            return True
        token = vim_token(keyval, state, self.leader)
        if token is None:
            return True
        self.captured.append(token)
        self.update_capture_box()
        self.apply_filter()
        return True

    # ── filtering ─────────────────────────────────────────────────────────
    def filter_row(self, row: KeyRow | RecipeRow) -> bool:
        it = row.item
        if self.selected_source and it["plugin"] != self.selected_source:
            return False
        if self.mode_filter != "all" and it["mode"] != self.mode_filter:
            return False
        if self.capture:
            if not self.captured:
                return True
            keys = (it["display"].lower(), it["lhs"].lower())
            variants = self.capture_variants()
            if any(k.startswith(v) for v in variants for k in keys):
                return True
            # nothing is mapped to this chord: fall back to mentions of it,
            # so built-ins described in the recipes still show up
            return self.capture_loose and any(v in row.haystack() for v in variants)
        if self.query:
            hay = row.haystack()
            return all(part in hay for part in self.query.split())
        return True

    def apply_filter(self):
        self.capture_loose = False
        shown = sum(1 for r in self.rows if self.filter_row(r))
        if self.capture and self.captured and not shown:
            self.capture_loose = True
            shown = sum(1 for r in self.rows if self.filter_row(r))
        self.key_list.invalidate_filter()
        self.stack.set_visible_child_name("list" if shown else "empty")
        if self.capture:
            seq = " › ".join(humanize_key(t) for t in self.captured)
            key = "capture_loose" if self.capture_loose else "capture_status"
            self.status.set_text(
                tr("capture_hint")
                if not self.captured
                else tr(key, seq=seq, shown=shown)
            )
            return
        scope = source_label(self.selected_source) if self.selected_source else tr("all_sources")
        self.status.set_text(
            tr("shown", shown=shown, total=len(self.rows), scope=scope, stamp=self.stamp)
        )

    def on_search(self, entry: Gtk.SearchEntry):
        self.query = entry.get_text().strip().lower()
        self.apply_filter()

    def on_mode(self, drop: Gtk.DropDown, _param):
        if self._syncing:
            return
        self.mode_filter = MODE_ORDER[drop.get_selected()]
        self.apply_filter()

    def on_source(self, _list, row):
        if row is None:
            return
        self.selected_source = row.source_key
        self.apply_filter()

    # ── actions ───────────────────────────────────────────────────────────
    def quit_app(self):
        """Close the window and exit: otherwise the process lingers windowless."""
        app = self.get_application()
        self.destroy()
        if app is not None:
            app.quit()

    def show_legend(self):
        dialog = Adw.AlertDialog(
            heading=tr("help_title"),
            body=tr("help_body", leader=self.leader or "<leader>"),
        )
        dialog.add_response("ok", tr("help_ok"))
        dialog.present(self)

    def on_activate(self, _list, row: KeyRow | RecipeRow):
        self.copy(row.item["display"])

    def copy(self, text: str):
        Gdk.Display.get_default().get_clipboard().set(text)
        self.status.set_text(tr("copied", text=text))

    def on_key(self, _ctrl, keyval, _code, state):
        if self.capture:
            return self.on_capture_key(keyval, state)
        ctrl = state & Gdk.ModifierType.CONTROL_MASK
        if keyval == Gdk.KEY_Escape:
            self.quit_app()
            return True
        if keyval == Gdk.KEY_F1:
            self.show_legend()
            return True
        if ctrl and keyval == Gdk.KEY_k:
            self.set_capture(True)
            return True
        if ctrl and keyval in (Gdk.KEY_f, Gdk.KEY_l):
            self.search.grab_focus()
            return True
        if ctrl and keyval == Gdk.KEY_r:
            self.refresh()
            return True
        if ctrl and keyval == Gdk.KEY_c:
            row = self.key_list.get_selected_row()
            if row:
                self.copy(row.item["display"])
                return True
        return False


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        win = self.props.active_window or Window(self)
        win.present()


if __name__ == "__main__":
    sys.exit(App().run([sys.argv[0]]))
