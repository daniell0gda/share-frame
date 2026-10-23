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
EDGE = 24  # px grab zone for resizing in edit mode

class Frame:
    def __init__(self, app):
        self.app, self.editing = app, False
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
        drag.connect("drag-update", self.drag_update); self.area.add_controller(drag)
        keys = Gtk.EventControllerKey(); keys.connect("key-pressed", self.key)
        self.win.add_controller(keys)
        self.win.connect("realize", lambda *_: self.apply_input())
        self.reload()

    # geometry -----------------------------------------------------------
    def reload(self):
        self.c = load(CONF)
        self.g = [int(float(self.c[k])) for k in ("x", "y", "width", "height")]
        self.b = max(1, int(float(self.c["border"])))
        rgba = Gdk.RGBA(); rgba.parse(self.c["color"]); self.rgba = rgba
        mon = None
        mons = Gdk.Display.get_default().get_monitors()
        for i in range(mons.get_n_items()):
            if mons.get_item(i).get_connector() == self.c["monitor"]: mon = mons.get_item(i)
        LS.set_monitor(self.win, mon)
        self.place()

    def place(self):
        x, y, w, h = self.g; b = self.b
        LS.set_margin(self.win, LS.Edge.LEFT, x - b)
        LS.set_margin(self.win, LS.Edge.TOP, y - b)
        self.win.set_default_size(w + 2 * b, h + 2 * b)
        self.area.set_size_request(w + 2 * b, h + 2 * b)
        self.win.set_size_request(w + 2 * b, h + 2 * b)
        self.area.queue_draw()

    def draw(self, _a, cr, W, H):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        if self.editing:
            cr.set_source_rgba(self.rgba.red, self.rgba.green, self.rgba.blue, 0.12); cr.paint()
        else:
            cr.set_source_rgba(0, 0, 0, 0); cr.paint()
        r = self.rgba; a = float(self.c["opacity"])
        cr.set_source_rgba(r.red, r.green, r.blue, a)
        b = self.b
        cr.rectangle(0, 0, W, H); cr.rectangle(b, b, W - 2 * b, H - 2 * b)
        cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD); cr.fill()
        if self.editing:
            cr.set_source_rgba(1, 1, 1, 0.9); cr.select_font_face("monospace"); cr.set_font_size(14)
            x, y, w, h = self.g
            cr.move_to(b + 10, b + 22)
            cr.show_text(f"share-frame edit  {w}x{h}+{x}+{y}  drag=move  edges=resize  "
                         "arrows=move  shift+arrows=resize  alt=x10  Enter=save  Esc=cancel")

    def apply_input(self):
        surf = self.win.get_surface()
        if surf is None: return
        if self.editing:
            surf.set_input_region(None)
            LS.set_keyboard_mode(self.win, LS.KeyboardMode.EXCLUSIVE)
        else:
            surf.set_input_region(cairo.Region())  # empty: clicks pass through
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

    # input ------------------------------------------------------------------
    def drag_begin(self, _g, sx, sy):
        x, y, w, h = self.g; W, H = w + 2 * self.b, h + 2 * self.b
        self.start = list(self.g)
        self.mode = (("l" if sx < EDGE else "r" if sx > W - EDGE else "") +
                     ("t" if sy < EDGE else "b" if sy > H - EDGE else "")) or "move"

    def drag_update(self, _g, dx, dy):
        if not self.editing: return
        # offsets are surface-local; add how far the surface origin already moved
        sx0, sy0 = self.start[0], self.start[1]
        if self.mode == "move" or "l" in self.mode: dx += self.g[0] - sx0
        if self.mode == "move" or "t" in self.mode: dy += self.g[1] - sy0
        x, y, w, h = self.start; dx, dy = int(dx), int(dy)
        if self.mode == "move": x, y = x + dx, y + dy
        else:
            if "l" in self.mode: dx = min(dx, w - 50); x, w = x + dx, w - dx
            if "r" in self.mode: w = w + dx
            if "t" in self.mode: dy = min(dy, h - 50); y, h = y + dy, h - dy
            if "b" in self.mode: h = h + dy
        self.g = [x, y, max(50, w), max(50, h)]; self.place()

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
        if c == "status": return ("edit" if self.editing else "locked") + (" shown" if v else " hidden")
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
