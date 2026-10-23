"""share-frame daemon: a click-through bordered layer-shell overlay (GTK4)."""
import os, socket, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sf_core import *  # noqa: F401,F403
import sf_core

if len(sys.argv) > 1 and sys.argv[1] == "--save-pick":
    save_pick(sys.argv[2], *sys.argv[3:7]); sys.exit(0)

import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk, Gdk, GLib, Gtk4LayerShell as LS
import cairo

SOCK, CONF = sys.argv[1], sys.argv[2]
NS = "share-frame"
CURSORS = {"move": "move", "tl": "nw-resize", "bl": "sw-resize", "br": "se-resize",
           "t": "n-resize", "b": "s-resize", "l": "w-resize", "r": "e-resize"}

class Frame:
    def __init__(self, app):
        self.app, self.editing, self.zone, self.drag = app, False, None, None
        self.win = Gtk.Window(application=app, title=NS, decorated=False)
        LS.init_for_window(self.win)
        LS.set_namespace(self.win, NS)
        LS.set_layer(self.win, LS.Layer.OVERLAY)
        LS.set_exclusive_zone(self.win, -1)
        for e in (LS.Edge.TOP, LS.Edge.LEFT): LS.set_anchor(self.win, e, True)
        css = Gtk.CssProvider()
        css.load_from_string("window, window * { background: transparent; }")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, 800)
        self.area = Gtk.DrawingArea(); self.area.set_draw_func(self.draw)
        self.win.set_child(self.area)
        click = Gtk.GestureClick(); click.connect("pressed", self.press)
        click.connect("released", self.release); self.area.add_controller(click)
        mot = Gtk.EventControllerMotion(); mot.connect("motion", self.motion)
        mot.connect("leave", lambda *_: self.hover(None)); self.area.add_controller(mot)
        keys = Gtk.EventControllerKey(); keys.connect("key-pressed", self.key)
        self.win.add_controller(keys)
        self.win.connect("realize", lambda *_: self.apply_input())
        self.reload()

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
        LS.set_monitor(self.win, self.mon)
        self.place()
        if [str(v) for v in self.g] != [self.c[k] for k in ("x", "y", "width", "height")] or reset:
            self.persist()

    def place(self):
        x, y, w, h = self.g
        LS.set_margin(self.win, LS.Edge.LEFT, x - PAD)
        LS.set_margin(self.win, LS.Edge.TOP, y - PAD)
        W, H = w + 2 * PAD, h + 2 * PAD
        self.win.set_default_size(W, H); self.area.set_size_request(W, H)
        self.win.set_size_request(W, H)
        self.apply_input()

    def rects(self): return zones(self.g[2], self.g[3], self.b)

    def zone_at(self, px, py):
        for k, (x, y, w, h) in self.rects().items():
            s = 3 if len(k) == 1 else 0     # widen thin border strips a bit
            if x - s <= px < x + w + s and y - s <= py < y + h + s: return k
        return "move" if self.editing else None

    def draw(self, _a, cr, W, H):
        cr.set_operator(cairo.OPERATOR_SOURCE); cr.set_source_rgba(0, 0, 0, 0); cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        r = self.rgba; a = float(self.c["opacity"]); _, _, w, h = self.g; P, b = PAD, self.b
        if self.editing:
            cr.set_source_rgba(r.red, r.green, r.blue, 0.12); cr.rectangle(P, P, w, h); cr.fill()
        cr.set_source_rgba(r.red, r.green, r.blue, a)
        cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        cr.rectangle(P - b, P - b, w + 2 * b, h + 2 * b); cr.rectangle(P, P, w, h); cr.fill()
        cr.set_fill_rule(cairo.FILL_RULE_WINDING)
        z = self.rects()
        for k in ("tl", "bl", "br"):
            x, y, gw, gh = z[k]
            cr.set_source_rgba(r.red, r.green, r.blue, 1.0 if self.zone == k else 0.75)
            cr.rectangle(x, y, gw, gh); cr.fill()
        x, y, hw, hh = z["move"]
        cr.set_source_rgba(r.red, r.green, r.blue, 1.0 if self.zone == "move" else 0.85)
        cr.rectangle(x, y, hw, hh); cr.fill()
        cx, cy, s = x + hw / 2, y + hh / 2, hw / 2 - 4   # icon centered in its hit area
        cr.set_source_rgba(0.1, 0.1, 0.12, 1); cr.set_line_width(1.6)
        cr.move_to(cx - s, cy); cr.line_to(cx + s, cy); cr.move_to(cx, cy - s); cr.line_to(cx, cy + s)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            tx, ty = cx + dx * s, cy + dy * s
            cr.move_to(tx - dx * 3 - dy * 3, ty - dy * 3 - dx * 3); cr.line_to(tx, ty)
            cr.line_to(tx - dx * 3 + dy * 3, ty - dy * 3 + dx * 3)
        cr.stroke()
        if self.editing:
            cr.set_source_rgba(1, 1, 1, 0.9); cr.select_font_face("monospace"); cr.set_font_size(14)
            X, Y, w, h = self.g
            cr.move_to(P + 10, P + 22)
            cr.show_text(f"share-frame edit  {w}x{h}+{X}+{Y}  arrows=move  shift+arrows=resize  "
                         "alt=x10  Enter=save  Esc=cancel")

    def apply_input(self):
        surf = self.win.get_surface()
        if surf is None: return
        if self.editing:
            surf.set_input_region(None)
            LS.set_keyboard_mode(self.win, LS.KeyboardMode.EXCLUSIVE)
        else:
            reg = cairo.Region()           # only handle, grips and border strips
            for x, y, w, h in self.rects().values():
                reg.union(cairo.RectangleInt(int(x) - 3, int(y) - 3, int(w) + 6, int(h) + 6))
            reg.subtract(cairo.RectangleInt(PAD, PAD, self.g[2], self.g[3]))
            surf.set_input_region(reg)
            LS.set_keyboard_mode(self.win, LS.KeyboardMode.NONE)
        self.area.queue_draw()

    # modes ----------------------------------------------------------------
    def set_editing(self, on, keep=True):
        if on and not self.editing: self.saved = list(self.g)
        if not on and self.editing and not keep: self.g = self.saved; self.place()
        if not on and self.editing and keep: self.persist()
        self.editing = on; self.win.set_visible(True); self.apply_input()

    def persist(self):
        c = load(CONF); c.update(dict(zip(("x", "y", "width", "height"), map(str, self.g))))
        c["monitor"] = self.c["monitor"]; save(CONF, c); self.c.update(c)

    # pointer: absolute-coordinate drag (no feedback loop) --------------------
    def hover(self, z):
        if z != self.zone:
            self.zone = z
            self.area.set_cursor_from_name(CURSORS.get(z) if z else None)
            self.area.queue_draw()

    def motion(self, _c, x, y):
        if not self.drag: self.hover(self.zone_at(x, y))

    def press(self, _g, _n, sx, sy):
        mode = self.zone_at(sx, sy)
        if not mode: return
        try: p0 = cursor_pos()
        except Exception: return
        self.drag = (mode, list(self.g), p0)
        GLib.timeout_add(16, self.tick)      # ~60 Hz

    def tick(self):
        if not self.drag: return False
        mode, start, (x0, y0) = self.drag
        try: x1, y1 = cursor_pos()
        except Exception: return True
        g = drag_geom(start, mode, int(x1 - x0), int(y1 - y0), self.mw, self.mh)
        if g != self.g: self.g = g; self.place()
        return True

    def release(self, *_):
        if self.drag:
            self.tick(); self.drag = None; self.persist()

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
