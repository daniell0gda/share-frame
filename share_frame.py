"""share-frame daemon: a click-through bordered layer-shell overlay (GTK4)."""
import json, os, socket, subprocess, sys

DEFAULTS = {"monitor": "", "x": "100", "y": "100", "width": "1280", "height": "720",
            "color": "#89b4fa", "border": "4", "opacity": "1.0"}

def load(path):
    c = dict(DEFAULTS)
    try:
        for line in open(path):
            line = line.split("#", 1)[0].strip()
            if "=" in line:
                k, v = (s.strip() for s in line.split("=", 1))
                if k in c: c[k] = v
    except FileNotFoundError:
        pass
    return c

def save(path, c):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("# share-frame config — geometry is the SHARED rectangle, in monitor-local pixels.\n"
                "# The border is drawn just outside it.\n")
        for k in DEFAULTS: f.write(f"{k} = {c[k]}\n")

def save_pick(path, x, y, w, h):
    x, y, w, h = map(int, (x, y, w, h))
    c = load(path)
    mons = json.loads(subprocess.check_output(["hyprctl", "monitors", "-j"]))
    for m in mons:
        mw, mh = (m["width"], m["height"]) if m["transform"] % 2 == 0 else (m["height"], m["width"])
        mw, mh = int(mw / m["scale"]), int(mh / m["scale"])
        if m["x"] <= x < m["x"] + mw and m["y"] <= y < m["y"] + mh:
            c.update(monitor=m["name"], x=x - m["x"], y=y - m["y"])
            break
    c.update(width=w, height=h)
    save(path, c)

if len(sys.argv) > 1 and sys.argv[1] == "--save-pick":
    save_pick(sys.argv[2], *sys.argv[3:7]); sys.exit(0)

import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk, Gdk, GLib, Gtk4LayerShell as LS
import cairo

SOCK, CONF = sys.argv[1], sys.argv[2]
NS = "share-frame"
PAD = 30        # surface extends this far outside the shared rectangle
GRIP = 14       # corner grip square (outside the rectangle)
HW, HH = 30, 22 # move handle, above the top edge, right-aligned

CURSORS = {"move": "move", "tl": "nw-resize", "tr": "ne-resize", "bl": "sw-resize",
           "br": "se-resize", "t": "n-resize", "b": "s-resize", "l": "w-resize", "r": "e-resize"}

class Frame:
    def __init__(self, app):
        self.app, self.editing, self.zone = app, False, None
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
        drag = Gtk.GestureDrag(); drag.connect("drag-begin", self.drag_begin)
        drag.connect("drag-update", self.drag_update); drag.connect("drag-end", self.drag_end)
        self.area.add_controller(drag)
        mot = Gtk.EventControllerMotion(); mot.connect("motion", self.motion)
        mot.connect("leave", lambda *_: self.hover(None)); self.area.add_controller(mot)
        keys = Gtk.EventControllerKey(); keys.connect("key-pressed", self.key)
        self.win.add_controller(keys)
        self.win.connect("realize", lambda *_: self.apply_input())
        self.reload()

    # geometry -----------------------------------------------------------
    def reload(self):
        self.c = load(CONF)
        self.g = [int(float(self.c[k])) for k in ("x", "y", "width", "height")]
        self.b = max(1, min(PAD - 2, int(float(self.c["border"]))))
        rgba = Gdk.RGBA(); rgba.parse(self.c["color"]); self.rgba = rgba
        mon = None
        mons = Gdk.Display.get_default().get_monitors()
        for i in range(mons.get_n_items()):
            if mons.get_item(i).get_connector() == self.c["monitor"]: mon = mons.get_item(i)
        LS.set_monitor(self.win, mon)
        self.place()

    def place(self):
        x, y, w, h = self.g
        LS.set_margin(self.win, LS.Edge.LEFT, x - PAD)
        LS.set_margin(self.win, LS.Edge.TOP, y - PAD)
        W, H = w + 2 * PAD, h + 2 * PAD
        self.win.set_default_size(W, H); self.area.set_size_request(W, H)
        self.win.set_size_request(W, H)
        self.apply_input()

    def rects(self):
        """Interactive zones in surface coords; all lie outside the shared rect."""
        _, _, w, h = self.g; P, b, G = PAD, self.b, GRIP
        L, T, R, B = P, P, P + w, P + h            # shared rectangle edges
        z = {"tl": (L - G, T - G, G, G), "tr": (R, T - G, G, G),
             "bl": (L - G, B, G, G), "br": (R, B, G, G),
             "t": (L, T - b, w, b), "b": (L, B, w, b),
             "l": (L - b, T, b, h), "r": (R, T, b, h),
             "move": (R - HW - 4, T - b - HH - 2, HW, HH)}
        return z

    def zone_at(self, px, py):
        for k in ("move", "tl", "tr", "bl", "br", "t", "b", "l", "r"):
            x, y, w, h = self.rects()[k]
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
        z = self.rects()
        for k in ("tl", "tr", "bl", "br"):
            x, y, gw, gh = z[k]
            cr.set_source_rgba(r.red, r.green, r.blue, 1.0 if self.zone == k else 0.75)
            cr.rectangle(x, y, gw, gh); cr.fill()
        x, y, hw, hh = z["move"]
        cr.set_source_rgba(r.red, r.green, r.blue, 1.0 if self.zone == "move" else 0.85)
        cr.new_sub_path(); rad = 5
        cr.arc(x + hw - rad, y + rad, rad, -1.5708, 0); cr.arc(x + hw - rad, y + hh - rad, rad, 0, 1.5708)
        cr.arc(x + rad, y + hh - rad, rad, 1.5708, 3.1416); cr.arc(x + rad, y + rad, rad, 3.1416, 4.7124)
        cr.close_path(); cr.fill()
        # four-way arrow icon
        cx, cy, s = x + hw / 2, y + hh / 2, 7
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
        c = load(CONF); c.update(dict(zip(("x", "y", "width", "height"), self.g)))
        c["monitor"] = self.c["monitor"] or c["monitor"]; save(CONF, c); self.c = c

    # pointer ----------------------------------------------------------------
    def hover(self, z):
        if z != self.zone:
            self.zone = z
            self.area.set_cursor_from_name(CURSORS.get(z) if z else None)
            self.area.queue_draw()

    def motion(self, _c, x, y):
        if not getattr(self, "dragging", False): self.hover(self.zone_at(x, y))

    def drag_begin(self, _g, sx, sy):
        self.start, self.mode, self.dragging = list(self.g), self.zone_at(sx, sy), True

    def drag_update(self, _g, dx, dy):
        m = self.mode
        if not m: return
        # offsets are surface-local; add how far the surface origin already moved
        if m == "move" or "l" in m: dx += self.g[0] - self.start[0]
        if m == "move" or "t" in m: dy += self.g[1] - self.start[1]
        x, y, w, h = self.start; dx, dy = int(dx), int(dy)
        if m == "move": x, y = x + dx, y + dy
        else:
            if "l" in m: dx = min(dx, w - 50); x, w = x + dx, w - dx
            if "r" in m: w = w + dx
            if "t" in m: dy = min(dy, h - 50); y, h = y + dy, h - dy
            if "b" in m: h = h + dy
        self.g = [x, y, max(50, w), max(50, h)]; self.place()

    def drag_end(self, *_):
        self.dragging = False
        if self.mode and not self.editing: self.persist()

    def key(self, _c, kv, _code, st):
        if not self.editing: return False
        step = 10 if st & Gdk.ModifierType.ALT_MASK else 1
        shift = st & Gdk.ModifierType.SHIFT_MASK
        x, y, w, h = self.g
        d = {Gdk.KEY_Left: (-step, 0), Gdk.KEY_Right: (step, 0),
             Gdk.KEY_Up: (0, -step), Gdk.KEY_Down: (0, step)}.get(kv)
        if d:
            if shift: w, h = max(50, w + d[0]), max(50, h + d[1])
            else: x, y = x + d[0], y + d[1]
            self.g = [x, y, w, h]; self.place(); return True
        if kv in (Gdk.KEY_Return, Gdk.KEY_KP_Enter): self.set_editing(False, True); return True
        if kv == Gdk.KEY_Escape: self.set_editing(False, False); return True
        return False

    # ipc ----------------------------------------------------------------------
    def cmd(self, c):
        v = self.win.get_visible()
        if c == "ping": return "pong"
        if c == "status": return ("edit" if self.editing else "locked") + (" shown" if v else " hidden") + f" hover={self.zone}"
        if c == "toggle": self.win.set_visible(not v); return "shown" if not v else "hidden"
        if c == "show": self.win.set_visible(True); self.apply_input(); return "shown"
        if c == "hide": self.win.set_visible(False); return "hidden"
        if c == "edit": self.set_editing(True); return "edit"
        if c == "lock": self.set_editing(False, True); return "locked"
        if c == "reload": self.reload(); return "reloaded"
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
