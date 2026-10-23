"""share-frame daemon: a click-through bordered layer-shell overlay (GTK4).

The layer surface covers the whole monitor and never moves. The frame is a set of
GTK widgets placed in a Gtk.Fixed; the input region is limited to the frame's
chrome. Because the surface origin is constant (0,0 of the monitor), pointer
coordinates are already monitor coordinates: no async-margin races while dragging.
"""
import os, socket, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sf_core import *  # noqa: F401,F403

if len(sys.argv) > 1 and sys.argv[1] == "--save-pick":
    save_pick(sys.argv[2], *sys.argv[3:7]); sys.exit(0)

import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk, Gdk, GLib, Gtk4LayerShell as LS
import cairo

SOCK, CONF = sys.argv[1], sys.argv[2]
NS = "share-frame"
DEBUG = os.environ.get("SHARE_FRAME_DEBUG")
def dbg(*a):
    if DEBUG: print(*a, file=sys.stderr, flush=True)

CURSORS = {"move": "move", "tl": "nw-resize", "bl": "sw-resize", "br": "se-resize",
           "t": "n-resize", "b": "s-resize", "l": "w-resize", "r": "e-resize"}
PARTS = ("t", "b", "l", "r", "tl", "bl", "br")

class Frame:
    def __init__(self, app):
        self.app, self.editing, self.zone, self.drag = app, False, None, None
        self.win = Gtk.Window(application=app, title=NS, decorated=False)
        LS.init_for_window(self.win)
        LS.set_namespace(self.win, NS)
        LS.set_layer(self.win, LS.Layer.OVERLAY)
        LS.set_exclusive_zone(self.win, -1)
        for e in (LS.Edge.TOP, LS.Edge.LEFT, LS.Edge.RIGHT, LS.Edge.BOTTOM):
            LS.set_anchor(self.win, e, True)        # full monitor, origin = monitor 0,0
        self.css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.css, 800)
        self.fixed = Gtk.Fixed(); self.win.set_child(self.fixed)
        self.tint = Gtk.Box(css_classes=["sf-tint"]); self.fixed.put(self.tint, 0, 0)
        self.parts = {}
        for k in PARTS:
            w = Gtk.Box(css_classes=["sf-part", "sf-grip" if len(k) == 2 else "sf-edge"])
            self.parts[k] = w; self.fixed.put(w, 0, 0)
        self.handle = Gtk.DrawingArea(css_classes=["sf-grip"]); self.handle.set_draw_func(self.draw_icon)
        self.parts["move"] = self.handle; self.fixed.put(self.handle, 0, 0)
        self.label = Gtk.Label(css_classes=["sf-label"]); self.fixed.put(self.label, 0, 0)
        click = Gtk.GestureClick(); click.connect("pressed", self.press)
        click.connect("released", self.release); self.win.add_controller(click)
        mot = Gtk.EventControllerMotion(); mot.connect("motion", self.motion)
        mot.connect("leave", lambda *_: self.hover(None)); self.win.add_controller(mot)
        keys = Gtk.EventControllerKey(); keys.connect("key-pressed", self.key)
        self.win.add_controller(keys)
        self.win.connect("realize", self.on_realize)
        self.win.connect("map", lambda *_: GLib.timeout_add(300, self.dbg_layout))
        self.reload()

    def on_realize(self, *_):
        # GTK may reset the input region on layout; re-apply ours every time
        self.win.get_surface().connect("layout", lambda *_: self.apply_input())
        self.apply_input()

    def dbg_layout(self):
        dbg("layout", self.win.get_surface_transform(), self.win.get_width(), self.win.get_height(),
            "monitor", self.mw, self.mh, "g", self.g)
        return False

    # geometry -----------------------------------------------------------
    def monitors(self):
        ms = Gdk.Display.get_default().get_monitors()
        return {ms.get_item(i).get_connector(): ms.get_item(i) for i in range(ms.get_n_items())}

    def reload(self, reset=False):
        self.c = load(CONF)
        mons = self.monitors()
        name = fallback_monitor(self.c["monitor"], mons) or next(iter(mons), "")
        self.mon = mons.get(name); self.c["monitor"] = name
        geo = self.mon.get_geometry() if self.mon else None
        self.mw, self.mh = (geo.width, geo.height) if geo else (1920, 1080)
        try: g = [int(float(self.c[k])) for k in ("x", "y", "width", "height")]
        except ValueError: g = [-1, -1, 0, 0]
        if reset or offscreen(g, self.mw, self.mh): g = default_geom(self.mw, self.mh)
        self.g = clamp(g, self.mw, self.mh)
        self.b = max(1, min(PAD - 2, int(float(self.c["border"]))))
        rgba = Gdk.RGBA()
        if not rgba.parse(self.c["color"]): rgba.parse(DEFAULTS["color"])
        self.rgba = rgba
        c = rgba.to_string(); a = float(self.c["opacity"])
        self.css.load_from_string(f"""
            window, window > fixed {{ background: transparent; }}
            .sf-edge {{ background: alpha({c}, {a}); }}
            .sf-grip {{ background: alpha({c}, 0.8); }}
            .sf-grip.hot {{ background: {c}; }}
            .sf-tint {{ background: alpha({c}, 0.12); }}
            .sf-label {{ color: white; font-family: monospace; font-size: 12px; }}""")
        LS.set_monitor(self.win, self.mon)
        self.place()
        if [str(v) for v in self.g] != [self.c[k] for k in ("x", "y", "width", "height")] or reset:
            self.persist()

    def place(self):
        """Lay out the widgets for self.g. Called at most once per frame while dragging."""
        x, y, w, h = self.g
        for k, (zx, zy, zw, zh) in zones_abs(self.g, self.b).items():
            wd = self.parts[k]; wd.set_size_request(zw, zh); self.fixed.move(wd, zx, zy)
        self.tint.set_visible(self.editing); self.label.set_visible(self.editing)
        if self.editing:
            self.tint.set_size_request(w, h); self.fixed.move(self.tint, x, y)
            self.label.set_text(f"share-frame edit  {w}x{h}+{x}+{y}  arrows=move  "
                                "shift+arrows=resize  alt=x10  Enter=save  Esc=cancel")
            self.fixed.move(self.label, x + 10, y + 8)
        self.apply_input()

    def draw_icon(self, _a, cr, W, H):
        cx, cy, s = W / 2, H / 2, min(W, H) / 2 - 4   # centered in the handle
        cr.set_source_rgba(0.1, 0.1, 0.12, 1); cr.set_line_width(1.6)
        cr.move_to(cx - s, cy); cr.line_to(cx + s, cy); cr.move_to(cx, cy - s); cr.line_to(cx, cy + s)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            tx, ty = cx + dx * s, cy + dy * s
            cr.move_to(tx - dx * 3 - dy * 3, ty - dy * 3 - dx * 3); cr.line_to(tx, ty)
            cr.line_to(tx - dx * 3 + dy * 3, ty - dy * 3 + dx * 3)
        cr.stroke()

    def apply_input(self):
        surf = self.win.get_surface()
        if surf is None: return
        reg = cairo.Region()
        for x, y, w, h in zones_abs(self.g, self.b).values():
            reg.union(cairo.RectangleInt(int(x) - 3, int(y) - 3, int(w) + 6, int(h) + 6))
        if self.editing:
            reg.union(cairo.RectangleInt(*self.g))
        else:
            reg.subtract(cairo.RectangleInt(*self.g))   # interior always passes clicks
        if self.drag:                                    # keep events during a fast drag
            reg = cairo.Region(cairo.RectangleInt(0, 0, self.mw, self.mh))
        surf.set_input_region(reg)
        dbg("input", reg.get_extents(), reg.num_rectangles(), "drag" if self.drag else "")
        LS.set_keyboard_mode(self.win, LS.KeyboardMode.EXCLUSIVE if self.editing else LS.KeyboardMode.NONE)

    # modes ----------------------------------------------------------------
    def set_editing(self, on, keep=True):
        if on and not self.editing: self.saved = list(self.g)
        if not on and self.editing and not keep: self.g = self.saved
        if not on and self.editing and keep: self.persist()
        self.editing = on; self.win.set_visible(True); self.place()

    def persist(self):
        c = load(CONF); c.update(dict(zip(("x", "y", "width", "height"), map(str, self.g))))
        c["monitor"] = self.c["monitor"]; save(CONF, c); self.c.update(c)

    # pointer: surface == monitor, so event coords are monitor coords ---------
    def hover(self, z):
        if z != self.zone:
            for k in ("tl", "bl", "br", "move"):
                (self.parts[k].add_css_class if k == z else self.parts[k].remove_css_class)("hot")
            self.zone = z
            self.win.set_cursor_from_name(CURSORS.get(z) if z else None)

    def motion(self, _c, x, y):
        if self.drag: self.drag["ptr"] = (x, y)
        else: self.hover(zone_at(self.g, self.b, x, y, self.editing))

    def press(self, _g, _n, x, y):
        mode = zone_at(self.g, self.b, x, y, self.editing)
        dbg("press", x, y, self.g, mode)
        if not mode: return
        self.drag = {"mode": mode, "start": list(self.g), "p0": (x, y), "ptr": (x, y)}
        self.apply_input()
        self.tick_id = self.win.add_tick_callback(self.tick)   # once per frame

    def tick(self, *_):
        if not self.drag: return False
        (x0, y0), (x1, y1) = self.drag["p0"], self.drag["ptr"]
        g = drag_geom(self.drag["start"], self.drag["mode"], round(x1 - x0), round(y1 - y0),
                      self.mw, self.mh)
        if g != self.g: self.g = g; self.place()
        return True

    def release(self, *_):
        if self.drag:
            self.tick(); self.win.remove_tick_callback(self.tick_id)
            self.drag = None; self.apply_input(); self.persist()

    def key(self, _c, kv, _code, st):
        if not self.editing: return False
        step = 10 if st & Gdk.ModifierType.ALT_MASK else 1
        shift = st & Gdk.ModifierType.SHIFT_MASK
        x, y, w, h = self.g
        d = {Gdk.KEY_Left: (-step, 0), Gdk.KEY_Right: (step, 0),
             Gdk.KEY_Up: (0, -step), Gdk.KEY_Down: (0, step)}.get(kv)
        if d:
            g = [x, y, w + d[0], h + d[1]] if shift else [x + d[0], y + d[1], w, h]
            self.g = clamp(g, self.mw, self.mh); self.place(); return True
        if kv in (Gdk.KEY_Return, Gdk.KEY_KP_Enter): self.set_editing(False, True); return True
        if kv == Gdk.KEY_Escape: self.set_editing(False, False); return True
        return False

    # ipc ----------------------------------------------------------------------
    def cmd(self, c):
        v = self.win.get_visible()
        if c == "ping": return "pong"
        if c == "status":
            return ("edit" if self.editing else "locked") + (" shown" if v else " hidden") + \
                f" {self.c['monitor']} {self.g[2]}x{self.g[3]}+{self.g[0]}+{self.g[1]}"
        if c == "toggle": self.win.set_visible(not v); return "shown" if not v else "hidden"
        if c == "show": self.win.set_visible(True); self.apply_input(); return "shown"
        if c == "hide": self.win.set_visible(False); return "hidden"
        if c == "edit": self.set_editing(True); return "edit"
        if c == "lock": self.set_editing(False, True); return "locked"
        if c == "reload": self.reload(); return "reloaded"
        if c == "reset": self.reload(reset=True); self.win.set_visible(True); return "reset"
        if c == "quit": GLib.idle_add(self.app.quit); return "bye"
        return "?"

def main():
    app = Gtk.Application(application_id="dev.ferens.ShareFrame")
    def activate(app):
        f = Frame(app); app.hold()
        srv = socket.socket(socket.AF_UNIX); srv.bind(SOCK); srv.listen(4)
        def on_conn(fd, _cond):
            conn, _ = srv.accept()
            try: conn.sendall(f.cmd(conn.recv(64).decode().strip()).encode())
            finally: conn.close()
            return True
        GLib.io_add_watch(srv.fileno(), GLib.IO_IN, on_conn)
    app.connect("activate", activate)
    try: app.run([])
    finally:
        try: os.unlink(SOCK)
        except OSError: pass

main()
