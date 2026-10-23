# share-frame — design spec

## Goal

When sharing a *region* of a large monitor (e.g. 5120×1440) in Teams on Hyprland,
nothing on screen shows what's being shared. share-frame draws a persistent
colored border around that region that is always on top, never intercepts input,
and never appears inside the share itself.

## Architecture

- **Daemon** `share_frame.py` — Python + GTK4 + `gtk4-layer-shell` (loaded with
  `LD_PRELOAD=/usr/lib/libgtk4-layer-shell.so`, required for GTK4 layer shell from Python).
- **CLI** `share-frame` — bash; starts the daemon on demand and talks to it over a
  Unix socket at `$XDG_RUNTIME_DIR/share-frame.sock` (one plain-text command per connection,
  one-word reply).
- **Surface** — one `zwlr_layer_surface_v1`, namespace `share-frame`, layer
  `OVERLAY`, anchored top+left, exclusive zone `-1` (ignores bar reservations so
  coordinates are true monitor coordinates). Position is set via margins.
- **Geometry** — config stores the shared rectangle `(x, y, w, h)` in
  monitor-local logical px. The surface is `(x-b, y-b, w+2b, h+2b)`; the border
  is painted only in that outer `b`-px ring (even-odd fill), interior fully
  transparent (`OPERATOR_SOURCE`, alpha 0). Hence the border lies *outside* the
  shared pixels.
- **Click-through** — in locked mode the surface input region is set to an empty
  `cairo.Region()` and keyboard interactivity is `NONE`; all pointer events go
  to whatever is underneath.

## Modes

| Mode | Input region | Keyboard | Look |
|---|---|---|---|
| locked | empty | none | border only |
| edit | full surface | exclusive | border + 12% tint + help text |

Transitions:

- `edit`: locked → edit (current geometry remembered for cancel).
- `lock` / `Enter`: edit → locked, geometry written to config.
- `Esc`: edit → locked, geometry restored, nothing written.
- `pick`: slurp selection → config → `reload` → `show` (stays/turns locked).
- `show`/`hide`/`toggle` change visibility only (unmapping the surface); mode is kept.
- `quit` exits the daemon; socket removed.

Edit-mode pointer: drag within 24 px of an edge/corner resizes that edge/corner;
elsewhere moves. Because drag offsets are surface-local and the surface itself
moves, the origin shift is added back each update. Minimum size 50×50.

## Config format

`~/.config/share-frame/config`, `key = value`, `#` comments. Keys:
`monitor` (Hyprland output name, matched against `GdkMonitor.connector`),
`x`, `y`, `width`, `height`, `color` (CSS color via `Gdk.RGBA.parse`),
`border` (px), `opacity` (0–1). Unknown keys ignored, missing keys default.
`pick` converts slurp's global layout coords to monitor-local using `hyprctl monitors -j`
(scale and transform aware).

## CLI

`share-frame [toggle|pick|edit|lock|show|hide|reload|status|quit|watch]`,
default `toggle`. Any command except `quit`/`status` auto-starts the daemon.

## Hyprland integration

- Layer rules: `layerrule = noanim, share-frame` (optionally `blur off`; no shadow on layers).
- No `pin` needed: layer surfaces are workspace-independent.
- Keybinds: see README. The live `hyprland.conf` is never modified by install.

## Launcher

`install.sh` writes `~/.local/share/applications/share-frame.desktop`
(`Name=share frame`, `Exec=~/.local/bin/share-frame toggle`), picked up by walker
(`Super + Space`).

## Screencast watch (opt-in)

`share-frame watch` reads `$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket2.sock`
via `socat` and maps `screencast>>1,*` → `show`, `screencast>>0,*` → `hide`.
Intended for `exec-once`.

## Limitations

- Region coordinates are not read from the share picker — you pick the same
  rectangle twice (once in share-frame, once in Teams/xdg-desktop-portal).
- `screencast` events don't say which region/output is shared, nor do they fire for
  every client identically; watch is a heuristic.
- If the region touches the monitor edge, that side of the border is off-screen.
- One frame at a time; Hyprland-only for `pick` (other wlroots compositors work for the overlay itself).
- Fractional scaling: geometry is in logical px; may be off by a pixel.

## Future ideas

- Read region from `hyprland-share-picker` / portal restore token to avoid double picking.
- Dim everything outside the region instead of (or in addition to) a border.
- Multiple named frames / presets (`share-frame pick meeting`).
- Size presets (1920×1080, 1280×720) and snapping to windows (`hyprctl clients`).
- Pulse/red color while actually live, theme color from the current Omarchy theme.
- Package for AUR.
