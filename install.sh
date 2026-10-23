#!/usr/bin/env bash
# Install share-frame for the current user (no sudo).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
missing=()
for p in python-gobject gtk4 gtk4-layer-shell slurp socat; do pacman -Q "$p" &>/dev/null || missing+=("$p"); done
((${#missing[@]})) && echo "Missing packages, install with: sudo pacman -S ${missing[*]}"
mkdir -p ~/.local/bin ~/.local/share/applications
ln -sf "$HERE/share-frame" ~/.local/bin/share-frame
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
