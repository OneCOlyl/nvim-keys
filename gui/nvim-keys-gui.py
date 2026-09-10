#!/usr/bin/env python3
"""nvim-keys — GTK4 window listing every Neovim keymap, grouped by plugin.

Left pane: sources (plugins, Neovim itself, your own config, hand-written recipes).
Right pane: keymaps, human-readable, with the original vim notation below.
Top: search across key, description, plugin and command.
"""

from __future__ import annotations

import json
import locale
import os
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
        "needs": "needs {plugin}",
        "example_tip": "Example: {example}",
        "refresh": "Rebuild the list (Ctrl+R)",
        "help": "How to read the notation (F1)",
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
            "Greyed out under the description is the original notation from your "
            "Neovim config:\n"
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
        "needs": "нужен {plugin}",
        "example_tip": "Пример: {example}",
        "refresh": "Пересобрать список (Ctrl+R)",
        "help": "Как читать обозначения (F1)",
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
            "Серым под описанием — исходная запись из конфига Neovim:\n"
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
            "«Приёмы» в списке источников — это шпаргалка, написанная руками: "
            "прыжки, поиск, отмена и операции с файлами, каждый пункт с примером. "
            "Строки, начинающиеся с «:», — это Ex-команды: набираются в командной "
            "строке и подтверждаются Enter.\n\n"
            "Enter — скопировать сочетание, Ctrl+R — пересобрать, Esc — закрыть."
        ),
        "help_ok": "Понятно",
    },
}


def pick_language() -> str:
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


MODE_LABELS = {
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
MODE_ORDER = ["all", "n", "i", "v", "x", "s", "o", "t", "c"]

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
.plugin-name { font-weight: bold; }
.dim { opacity: 0.6; }
"""

# ── key notation ────────────────────────────────────────────────────────────

MODIFIERS = {"C": "Ctrl", "M": "Alt", "A": "Alt", "S": "Shift", "D": "Super", "T": "Meta"}

NAMED_KEYS = {
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


def recipe_files() -> list[Path]:
    """Shipped recipes plus the user's own additions, in that order."""
    paths: list[Path] = []
    env = os.environ.get("NVIM_KEYS_RECIPES")
    if env:
        paths.append(Path(env).expanduser())
    else:
        checkout = Path(__file__).resolve().parent.parent / "data" / "recipes.json"
        home = os.environ.get("NVIM_KEYS_HOME") or os.path.join(
            os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
            "nvim-keys",
        )
        paths.append(checkout if checkout.exists() else Path(home) / "recipes.json")
    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    paths.append(Path(config_home) / "nvim-keys" / "recipes.json")
    return [p for p in paths if p.exists()]


def pick_text(value) -> str:
    """Recipe texts are {"en": …, "ru": …}; plain strings are allowed too."""
    if isinstance(value, dict):
        return value.get(LANG) or value.get("en") or next(iter(value.values()), "")
    return value or ""


def load_recipes() -> list[dict]:
    """Hand-written cheatsheet entries, shaped like keymap rows."""
    items: list[dict] = []
    for path in recipe_files():
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
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


def sort_sources(counts: dict[str, int]) -> list[str]:
    """Own config, recipes and built-ins on top, plugins by keymap count."""
    priority = {"$config": 0, SRC_RECIPES: 1, "$neovim": 2, "$other": 4}

    def key(name: str):
        return (priority.get(name, 3), -counts[name], source_label(name).lower())

    return sorted(counts, key=key)


class KeyRow(Gtk.ListBoxRow):
    def __init__(self, item: dict):
        super().__init__()
        self.item = item
        self.human = humanize(item["display"])

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
        desc = Gtk.Label(label=item["desc"] or tr("no_desc"), xalign=0)
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
        if it["desc"]:
            tip.append(it["desc"])
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
                it["desc"],
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
        desc = Gtk.Label(label=item["desc"] or tr("no_desc"), xalign=0)
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
        if it["desc"]:
            tip.append(it["desc"])
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
                it["desc"],
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

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)

        header = Adw.HeaderBar()
        self.search = Gtk.SearchEntry(hexpand=True)
        self.search.set_placeholder_text(tr("search"))
        self.search.connect("search-changed", self.on_search)
        self.search.connect("stop-search", lambda *_: self.quit_app())
        self.search.set_size_request(420, -1)
        header.set_title_widget(self.search)

        self.mode_drop = Gtk.DropDown.new_from_strings(
            [MODE_LABELS[m] for m in MODE_ORDER]
        )
        self.mode_drop.connect("notify::selected", self.on_mode)
        header.pack_end(self.mode_drop)

        refresh = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh.set_tooltip_text(tr("refresh"))
        refresh.connect("clicked", lambda *_: self.refresh())
        header.pack_end(refresh)

        help_btn = Gtk.Button(icon_name="help-about-symbolic")
        help_btn.set_tooltip_text(tr("help"))
        help_btn.connect("clicked", lambda *_: self.show_legend())
        header.pack_start(help_btn)
        root.append(header)

        panes = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, vexpand=True)
        panes.set_position(260)
        root.append(panes)

        self.source_list = Gtk.ListBox()
        self.source_list.add_css_class("navigation-sidebar")
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
        self.stack.add_named(
            Adw.StatusPage(
                title=tr("empty_title"),
                description=tr("empty_body"),
                icon_name="edit-find-symbolic",
            ),
            "empty",
        )
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

        self.source_list.remove_all()
        self._add_source_row(None, tr("all_sources"), len(entries))
        for name in sort_sources(counts):
            self._add_source_row(name, source_label(name), counts[name])
        self.source_list.select_row(self.source_list.get_row_at_index(0))

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

    def _add_source_row(self, key: str | None, label: str, count: int):
        row = Gtk.ListBoxRow()
        row.source_key = key
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

    # ── filtering ─────────────────────────────────────────────────────────
    def filter_row(self, row: KeyRow | RecipeRow) -> bool:
        it = row.item
        if self.selected_source and it["plugin"] != self.selected_source:
            return False
        if self.mode_filter != "all" and it["mode"] != self.mode_filter:
            return False
        if self.query:
            hay = row.haystack()
            return all(part in hay for part in self.query.split())
        return True

    def apply_filter(self):
        self.key_list.invalidate_filter()
        shown = sum(1 for r in self.rows if self.filter_row(r))
        self.stack.set_visible_child_name("list" if shown else "empty")
        scope = source_label(self.selected_source) if self.selected_source else tr("all_sources")
        self.status.set_text(
            tr("shown", shown=shown, total=len(self.rows), scope=scope, stamp=self.stamp)
        )

    def on_search(self, entry: Gtk.SearchEntry):
        self.query = entry.get_text().strip().lower()
        self.apply_filter()

    def on_mode(self, drop: Gtk.DropDown, _param):
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
        ctrl = state & Gdk.ModifierType.CONTROL_MASK
        if keyval == Gdk.KEY_Escape:
            self.quit_app()
            return True
        if keyval == Gdk.KEY_F1:
            self.show_legend()
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
