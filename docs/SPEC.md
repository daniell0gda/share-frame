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
- **Surface** — anchored to all four edges, so it covers the whole monitor and
  its origin is the monitor's 0,0. It never moves or resizes. The frame is GTK
  widgets in a `Gtk.Fixed` (border strips, grips, handle, edit tint/label), styled
  with CSS and rendered by GSK; moving the frame = `Fixed.move` of a few widgets.
- **Chrome layout** — `PAD = 22` px around the shared rectangle holds the border
  ring (`b` px), 14×14 corner grips flush outside the top-left, bottom-left and
  bottom-right corners, and a 22×22 move handle flush outside the top-right corner
  (its bottom-left point is the corner), icon centered in its hit area.
- **Click-through** — input region = border strips + grips + handle (each widened
  3 px) minus the shared rectangle; in edit mode the rectangle is added. Everything
  else on the monitor passes input through. GTK can reset the region on layout, so
  it's re-applied on every `GdkSurface::layout`. During a drag the region is the
  whole monitor so a fast pointer can't escape (the button is held, so nothing
  underneath would get the click anyway).
- **Pointer / drag** — because the surface origin is fixed, event coordinates
  *are* monitor coordinates. History: v0.2 used surface-local offsets while moving
  the surface via layer-shell margins (feedback loop, runaway); v0.3 polled
  `hyprctl cursorpos` (lag); v0.4 used `origin + local`, which jumped at grab and
  randomly mid-drag because margin changes are applied asynchronously by the
  compositor, so some events were still in the old surface coordinates. v0.5
  removes the moving surface entirely. Motion stores the latest pointer; a
  frame-clock tick computes `drag_geom(start, mode, ptr - p0)` once per frame;
  config is written on release.
- **Code layout** — `sf_core.py`: config + pure geometry (`clamp`, `drag_geom`,
  `zones`, `zones_abs`, `zone_at`, `offscreen`, `default_geom`), unit-tested in
  `tests/test_geometry.py`; `share_frame.py`: GTK daemon. `SHARE_FRAME_DEBUG=1`
  logs press/input-region/layout to `$XDG_RUNTIME_DIR/share-frame.log`.
- **Clamping** — the shared rect is kept `PAD` px inside the monitor on all sides,
  so the border, grips and handle are always on-screen; minimum size 120×80.
- **Monitor** — `monitor` is matched against `GdkMonitor.connector`; if empty or
  unknown, the focused Hyprland monitor is used and written back. If the saved
  geometry is off-screen or invalid on startup, it's reset to 1280×720 centered.

## Modes

| Mode | Input region | Keyboard | Look |
|---|---|---|---|
| locked | border + grips + handle | none | border, grips, handle |
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

`share-frame [toggle|pick|edit|lock|reset|show|hide|reload|status|quit|watch]`
(`reset` recenters at the default size and saves),
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

## Focus

Evaluated: switching to (or adding) a floating xdg-toplevel window so it joins
Hyprland's focus cycle, with a focused-state color. Rejected for now:

- A toplevel can't position itself on Wayland; placement would depend on
  `windowrule`s plus `hyprctl dispatch movewindowpixel/resizewindowpixel`
  round-trips, and drag would need `xdg_toplevel.move`/`resize` with geometry read
  back from `hyprctl clients`.
- Hyprland draws its own border, shadow, rounding and dim around focused windows;
  these need `noborder`, `noshadow`, `rounding 0`, `nodim`, `noblur` rules, and if
  any rule doesn't match (title/class change, Hyprland rule syntax changes) the
  white focus border sits right on the shared edge and can leak into the share.
- Being in the focus cycle means `Alt+Tab`/`Super+arrows` land on the frame,
  which is the opposite of what you want mid-meeting; it can also be tiled/
  stacked below a fullscreen app, while the overlay layer always stays on top.
- Hyprland does honor `wl_surface` input regions for windows, so click-through
  itself would work; the cost is the positioning and border risks above.

Consequence: the layer-shell frame has no keyboard focus while locked.
Keyboard control is `share-frame edit` (exclusive keyboard until Enter/Esc) or
binds to the CLI. A toplevel mode remains a future idea.

## Portal picker

`share-frame-picker` is an xdph `screencopy:custom_picker_binary`. xdph (1.4.1)
runs it with `WAYLAND_DISPLAY`, `HYPRLAND_INSTANCE_SIGNATURE`,
`XDPH_WINDOW_SHARING_LIST` and optionally `--allow-token`, and parses stdout for
`[SELECTION]<flags>/<target>` where flags may contain `r` (allow restore token)
and target is `screen:<output>`, `window:<handle>` or
`region:<output>@<x>,<y>,<w>,<h>` — monitor-local logical pixels (the reference
picker subtracts the screen's Qt geometry origin). For the frame it prints
`[SELECTION]/region:<monitor>@x,y,w,h` from the live daemon (`status`) or the
config, without `r` (the frame may move, so no restore token). Any other choice
`exec`s the fallback picker with the same arguments. `SHARE_FRAME_PICK=frame|other`
skips the dialog (testing/automation). No output / non-zero exit = cancel.

## Limitations

- The surface is monitor-sized (transparent). Composited cheaply by Hyprland, but
  it is one full-monitor buffer while shown.

- Region coordinates are not read from the share picker — you pick the same
  rectangle twice (once in share-frame, once in Teams/xdg-desktop-portal).
- `screencast` events don't say which region/output is shared, nor do they fire for
  every client identically; watch is a heuristic.
- If the region touches the monitor edge, that side of the border is off-screen.
- One frame at a time; Hyprland-only for `pick` (other wlroots compositors work for the overlay itself).
- Fractional scaling: geometry is in logical px; may be off by a pixel.

## Future ideas

- Optional `mode = toplevel` with focus-colored border (see Focus).

- Read region from `hyprland-share-picker` / portal restore token to avoid double picking.
- Dim everything outside the region instead of (or in addition to) a border.
- Multiple named frames / presets (`share-frame pick meeting`).
- Size presets (1920×1080, 1280×720) and snapping to windows (`hyprctl clients`).
- Pulse/red color while actually live, theme color from the current Omarchy theme.
- Package for AUR.
