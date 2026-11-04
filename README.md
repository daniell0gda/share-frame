# share-frame

**A share-area frame for [Omarchy](https://omarchy.org).** It draws a click-through
colored border around the screen region you share in Teams, Meet, Zoom or OBS. It
also makes the share portal send exactly that region, so the call shows only
what is inside the frame.

The border sits just **outside** the shared rectangle, so it never shows up in the share.
It is useful most on ultrawide monitors, where sharing the whole screen is too much.

Design details: [docs/SPEC.md](docs/SPEC.md).

## Install (Omarchy plugin)

Install the dependencies first. Omarchy ships most of them.

```sh
omarchy-pkg-add python-gobject gtk4 gtk4-layer-shell slurp socat
```

Add the plugin:

```sh
omarchy plugin add https://github.com/daniell0gda/share-frame --enable
```

A frame icon appears in the bar. On first load the plugin:

- links `share-frame` into `~/.local/bin`
- registers the share picker in `~/.config/hypr/xdph.conf` (your file is backed up first)
- restarts `xdg-desktop-portal-hyprland`
- adds a **share frame** entry to the app launcher

If a package is missing, the bar icon tells you which one. Click it to install.

Update:

```sh
omarchy plugin update io.github.daniell0gda.share-frame
```

Remove (run the uninstaller first, so the portal setting is cleaned up):

```sh
~/.config/omarchy/plugins/io.github.daniell0gda.share-frame/uninstall.sh
omarchy plugin remove io.github.daniell0gda.share-frame
```

Even if you skip the uninstaller, screen sharing keeps working. The installed picker
launcher falls back to the normal picker when share-frame is gone.

Requirements: Omarchy with plugin support (tested on 4.0), Hyprland and
`xdg-desktop-portal-hyprland`.

### Install without the plugin system

Any Hyprland setup works for the frame itself:

```sh
git clone https://github.com/daniell0gda/share-frame ~/.local/share/share-frame
~/.local/share/share-frame/install.sh
```

## Use

1. Draw the area: right click the bar icon, or run `share-frame pick`.
2. In Teams, start a screen share.
3. In the dialog, choose **share-frame area** (`Enter` or `1`).

The call now shows exactly the inside of the frame.

| Bar icon | Action |
|---|---|
| Left click | Show or hide the frame |
| Right click | Draw a new region |
| Middle click | Edit: move and resize the frame |

### Share dialog

When an app asks to share, a small dialog appears:

- **share-frame area** (`Enter` or `1`): shares exactly the inside of the frame
  (shows the frame if it is hidden).
- **Screen / window / region…** (`2`): opens your normal picker
  (`hyprland-preview-share-picker`, else `hyprland-share-picker`; override with
  `SHARE_FRAME_FALLBACK_PICKER`).

Chromium (and so Teams in the browser) asks the portal twice for each share: once
for the preview in its own dialog and once when you click **Share**. To avoid a
second question, the picker answers **share-frame area** by itself for 90 seconds
after you chose it. Set `SHARE_FRAME_REMEMBER_SECONDS=0` to turn this off.

## Command line

| Command | What it does |
|---|---|
| `share-frame` | Toggle the frame on/off (same as the launcher entry) |
| `share-frame pick` | Draw the region with `slurp`, save it, show the frame |
| `share-frame edit` | Make the frame interactive: drag to move, drag edges/corners to resize |
| `share-frame lock` | Save and go back to click-through |
| `share-frame reset` | Recenter on the monitor at 1280×720 (use if it is lost) |
| `share-frame show` / `hide` | Explicit show / hide |
| `share-frame status` | `locked shown`, `edit hidden`, `stopped`… |
| `share-frame quit` | Stop the daemon |
| `share-frame watch` | Auto-show while a screencast is active (opt-in, see below) |

In edit mode: arrows move, `Shift`+arrows resize, hold `Alt` for 10px steps,
`Enter` saves and locks, `Esc` cancels.

### Handle and grips (locked mode)

Even when locked, the frame has a few live spots, all **outside** the shared area:

- **Move handle** (four-way arrow, flush outside the top-right corner): drag to move.
- **Corner grips** (other three corners): hover shows a resize cursor, drag to resize.
- **Border strips**: drag to resize that edge.

Everything else, including the whole interior, passes clicks through. The frame
always stays on the monitor. It is saved to the config when you let go. If a saved
position is off-screen, it is recentered on startup.

> The frame cannot be focused with Hyprland window shortcuts (it is a layer-shell
> overlay, not a window). Why: see [docs/SPEC.md](docs/SPEC.md#focus).

## Keybindings (optional)

Omarchy 4 (Lua config), in `~/.config/hypr/bindings.lua`:

```lua
o.bind("SUPER + SHIFT + F", "Share frame", "share-frame")
o.bind("SUPER + SHIFT + ALT + F", "Share frame pick", "share-frame pick")
o.bind("SUPER + CTRL + F", "Share frame edit", "share-frame edit")
```

Older Omarchy (`hyprland.conf` syntax):

```ini
bind = SUPER SHIFT, F, exec, share-frame
bind = SUPER SHIFT ALT, F, exec, share-frame pick
bind = SUPER CTRL, F, exec, share-frame edit
```

The frame is a layer-shell surface, so it is on every workspace already.

## Auto-show while sharing (optional)

Start `share-frame watch` with your session (Omarchy 4: `o.launch_on_start("share-frame watch")`
in `~/.config/hypr/autostart.lua`; older: `exec-once = share-frame watch`).

It listens on Hyprland's event socket. It shows the frame on `screencast>>1` and
hides it on `screencast>>0`. Hyprland fires these for any screencast, including
screen recording, not per region.

## Config

`~/.config/share-frame/config` (written by `pick`/`edit`, safe to edit by hand, then run `share-frame reload`):

```ini
monitor = DP-1      # Hyprland output name; empty/unknown = focused monitor
x = 200             # shared rectangle, monitor-local logical pixels
y = 300
width = 1920
height = 1080
color = #89b4fa     # any CSS color
border = 4          # px, drawn outside the rectangle
opacity = 1.0
```

## Troubleshooting

- **The share never starts after you choose the frame.** Restart the portal:
  `systemctl --user restart xdg-desktop-portal-hyprland`. Make sure you run version 1.0.0 or newer.
- **Teams or Chromium never accepts the share and asks again.** Chromium may fail to
  import the portal's DMA-BUF frames (`EGL_BAD_MATCH` in its log). Make the portal send
  plain memory buffers: add `force_shm = true` inside `screencopy { … }` in
  `~/.config/hypr/xdph.conf`, then run `systemctl --user restart xdg-desktop-portal-hyprland`.
  This uses a little more CPU.
- **The dialog does not appear.** Check that `~/.config/hypr/xdph.conf` has
  `custom_picker_binary = ~/.local/bin/share-frame-picker`. Run `~/.config/omarchy/plugins/io.github.daniell0gda.share-frame/install.sh` to repair it.
- **The frame is lost.** Run `share-frame reset`.

## Development

```sh
python3 tests/test_geometry.py
omarchy plugin validate .
```

## License

MIT
