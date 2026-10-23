# share-frame

A click-through colored border that marks the screen region you're sharing
(Teams, Meet, Zoom, OBS…) on Hyprland. Built for Omarchy, works on any Hyprland.

The border sits just **outside** the shared rectangle, so it never shows up in the share.

Design details: [docs/SPEC.md](docs/SPEC.md).

## Dependencies

```sh
sudo pacman -S --needed python-gobject gtk4 gtk4-layer-shell slurp socat
```

All of these ship with Omarchy except possibly `gtk4-layer-shell`/`socat`; `install.sh` tells you what's missing.

## Install

```sh
git clone <this repo> ~/Projects/share-frame
cd ~/Projects/share-frame && ./install.sh
```

This symlinks `~/.local/bin/share-frame` and adds a **share frame** entry to the
launcher (`Super + Space`). Restart walker if it doesn't appear: `omarchy-restart-walker`.

## Usage

| Command | What it does |
|---|---|
| `share-frame` | Toggle the frame on/off (same as the launcher entry) |
| `share-frame pick` | Draw the region with `slurp`, save it, show the frame |
| `share-frame edit` | Make the frame interactive: drag to move, drag edges/corners to resize |
| `share-frame lock` | Save and go back to click-through |
| `share-frame show` / `hide` | Explicit show / hide |
| `share-frame status` | `locked shown`, `edit hidden`, `stopped`… |
| `share-frame quit` | Stop the daemon |
| `share-frame watch` | Auto-show while a screencast is active (opt-in, see below) |

In edit mode: arrows move, `Shift`+arrows resize, hold `Alt` for 10px steps,
`Enter` saves and locks, `Esc` cancels.

Typical flow: `share-frame pick` → in Teams, share the same region → done.

## Config

`~/.config/share-frame/config` (written by `pick`/`edit`, safe to hand-edit, then `share-frame reload`):

```ini
monitor = DP-1      # Hyprland output name; empty = compositor's choice
x = 200             # shared rectangle, monitor-local logical pixels
y = 300
width = 1920
height = 1080
color = #89b4fa     # any CSS color
border = 4          # px, drawn outside the rectangle
opacity = 1.0
```

## Hyprland config examples

Add to `~/.config/hypr/hyprland.conf` (or `bindings.conf` on Omarchy):

```ini
# no blur/shadow/animation on the overlay
layerrule = noanim, share-frame
layerrule = blur off, share-frame   # older Hyprland: just omit, blur is off for layers by default

# keybinds
bind = SUPER SHIFT, F, exec, share-frame
bind = SUPER SHIFT ALT, F, exec, share-frame pick
bind = SUPER CTRL, F, exec, share-frame edit
```

It's a layer-shell surface, so it's on every workspace already (no `pin` needed).

## Auto-show while sharing

```ini
exec-once = share-frame watch
```

Listens on Hyprland's event socket and shows the frame on `screencast>>1`,
hides it on `screencast>>0`. Note: Hyprland fires these for any screencast
(including screen recording), not per region.

## Uninstall

```sh
./uninstall.sh   # removes the symlink and launcher entry, keeps your config
```

## License

MIT
