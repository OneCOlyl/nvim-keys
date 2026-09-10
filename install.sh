#!/usr/bin/env bash
# Install nvim-keys into ~/.local (or $PREFIX).
#
#   ./install.sh            copy files
#   ./install.sh --link     symlink to this checkout (handy for development)
#   ./install.sh --uninstall
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${PREFIX:-$HOME/.local}/bin"
SHARE_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/nvim-keys"

mode="copy"
case "${1:-}" in
--link) mode="link" ;;
--uninstall) mode="uninstall" ;;
"") ;;
*)
    echo "usage: install.sh [--link|--uninstall]" >&2
    exit 2
    ;;
esac

if [[ "$mode" == "uninstall" ]]; then
    rm -f "$BIN_DIR/nvim-keys"
    rm -rf "$SHARE_DIR"
    echo "nvim-keys removed. Waybar and Hyprland config were left untouched."
    exit 0
fi

mkdir -p "$BIN_DIR" "$SHARE_DIR"

install_file() {
    local src="$1" dst="$2"
    rm -f "$dst"
    if [[ "$mode" == "link" ]]; then
        ln -s "$src" "$dst"
    else
        cp "$src" "$dst"
    fi
}

install_file "$ROOT/bin/nvim-keys" "$BIN_DIR/nvim-keys"
install_file "$ROOT/lua/prelude.lua" "$SHARE_DIR/prelude.lua"
install_file "$ROOT/lua/dump.lua" "$SHARE_DIR/dump.lua"
install_file "$ROOT/gui/nvim-keys-gui.py" "$SHARE_DIR/gui.py"
install_file "$ROOT/data/recipes.json" "$SHARE_DIR/recipes.json"
chmod +x "$BIN_DIR/nvim-keys"

echo "Installed:"
echo "  $BIN_DIR/nvim-keys"
echo "  $SHARE_DIR/{prelude.lua,dump.lua,gui.py,recipes.json}"

missing=()
for dep in nvim python3 jq; do
    command -v "$dep" >/dev/null || missing+=("$dep")
done
python3 -c 'import gi; gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1")' \
    2>/dev/null || missing+=("python-gobject with GTK4 + libadwaita")

if ((${#missing[@]})); then
    echo
    echo "Missing dependencies: ${missing[*]}"
fi

case ":$PATH:" in
*":$BIN_DIR:"*) ;;
*) echo && echo "Note: $BIN_DIR is not in your PATH" ;;
esac

echo
echo "Next: run 'nvim-keys dump', then see examples/ for the Waybar module."
