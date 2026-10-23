#!/usr/bin/env bash
# Install share-frame for the current user (no sudo).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
missing=()
for p in python-gobject gtk4 gtk4-layer-shell slurp socat; do pacman -Q "$p" &>/dev/null || missing+=("$p"); done
((${#missing[@]})) && echo "Missing packages, install with: sudo pacman -S ${missing[*]}"
mkdir -p ~/.local/bin ~/.local/share/applications
ln -sf "$HERE/share-frame" ~/.local/bin/share-frame
ln -sf "$HERE/share-frame-picker" ~/.local/bin/share-frame-picker

# xdg-desktop-portal-hyprland picker: only touch xdph.conf if the option is absent
XDPH=~/.config/hypr/xdph.conf
if [[ ! -f $XDPH ]]; then
  mkdir -p ~/.config/hypr
  printf 'screencopy {\n    allow_token_by_default = true\n    custom_picker_binary = %s\n}\n' "$HOME/.local/bin/share-frame-picker" > "$XDPH"
  echo "Wrote $XDPH. Restart the portal: systemctl --user restart xdg-desktop-portal-hyprland"
elif ! grep -q custom_picker_binary "$XDPH"; then
  cp "$XDPH" "$XDPH.bak.$(date +%Y%m%d%H%M%S)"
  if grep -q 'screencopy *{' "$XDPH"; then
    sed -i "/screencopy *{/a\\    custom_picker_binary = $HOME/.local/bin/share-frame-picker" "$XDPH"
  else
    printf '\nscreencopy {\n    custom_picker_binary = %s\n}\n' "$HOME/.local/bin/share-frame-picker" >> "$XDPH"
  fi
  echo "Added share-frame-picker to $XDPH (backup kept). Restart: systemctl --user restart xdg-desktop-portal-hyprland"
elif ! grep -q share-frame-picker "$XDPH"; then
  echo "NOTE: $XDPH already sets another custom_picker_binary; left unchanged."
  echo "      To use share-frame-picker, set: custom_picker_binary = $HOME/.local/bin/share-frame-picker"
  echo "      (it falls back to hyprland-preview-share-picker / hyprland-share-picker for other choices)"
fi
cat > ~/.local/share/applications/share-frame.desktop <<D
[Desktop Entry]
Type=Application
Name=share frame
Comment=Toggle a border around the screen region you share
Exec=$HOME/.local/bin/share-frame toggle
Icon=video-display
Terminal=false
Categories=Utility;
D
echo "Installed. Run 'share-frame pick' to choose a region."
