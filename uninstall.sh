#!/usr/bin/env bash
set -euo pipefail
share-frame quit 2>/dev/null || true
rm -f ~/.local/bin/share-frame ~/.local/share/applications/share-frame.desktop
echo "Removed. Config kept at ~/.config/share-frame (delete it by hand if you want)."
