"""Tiny GTK4 chooser for share-frame-picker. Prints 'frame', 'other' or nothing."""
import sys, gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk

app = Gtk.Application(application_id="dev.ferens.ShareFramePicker")
result = []

def activate(app):
    win = Gtk.Window(application=app, title="share-frame picker", resizable=False)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                  margin_top=16, margin_bottom=16, margin_start=16, margin_end=16)
    box.append(Gtk.Label(label="What do you want to share?"))
    def pick(v):
        result.append(v); win.close()
    b1 = Gtk.Button(label="share-frame area"); b1.connect("clicked", lambda *_: pick("frame"))
    b2 = Gtk.Button(label="Screen / window / region…"); b2.connect("clicked", lambda *_: pick("other"))
    box.append(b1); box.append(b2)
    box.append(Gtk.Label(label="Enter = frame · 2 = other · Esc = cancel", css_classes=["dim-label"]))
    win.set_child(box)
    keys = Gtk.EventControllerKey()
    def key(_c, kv, *_):
        if kv == Gdk.KEY_Escape: win.close(); return True
        if kv in (Gdk.KEY_1,): pick("frame"); return True
        if kv in (Gdk.KEY_2,): pick("other"); return True
        return False
    keys.connect("key-pressed", key); win.add_controller(keys)
    win.set_default_widget(b1); b1.grab_focus(); win.present()

app.connect("activate", activate)
app.run([])
if result: print(result[0])
