#!/usr/bin/env bash
# Undo install.sh. Run it before `omarchy plugin remove`. Your config is kept.
set -euo pipefail
BIN=~/.local/bin
XDPH=~/.config/hypr/xdph.conf

"$BIN/share-frame" quit 2>/dev/null || true
[[ -f $XDPH ]] && sed -i '\|custom_picker_binary *=.*share-frame-picker|d' "$XDPH"
rm -f "$BIN/share-frame" "$BIN/share-frame-picker" ~/.local/share/applications/share-frame.desktop
systemctl --user restart xdg-desktop-portal-hyprland 2>/dev/null || true
echo "Removed. Config kept at ~/.config/share-frame (delete it by hand if you want)."
