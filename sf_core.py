"""share-frame: config + pure geometry (no GTK), shared by daemon and tests."""
import json, os, re, subprocess

DEFAULTS = {"monitor": "", "x": "100", "y": "100", "width": "1280", "height": "720",
            "color": "#89b4fa", "border": "4", "opacity": "1.0"}

def load(path):
    c = dict(DEFAULTS)
    try:
        for line in open(path):
            line = line.strip()
            if line.startswith("#"): continue
            if "=" in line:
                k, v = (s.strip() for s in line.split("=", 1))
                v = re.split(r"\s+#", v, maxsplit=1)[0].strip()
                if k in c and (v or k == "monitor"): c[k] = v
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



# ---- pure geometry (unit-tested in tests/test_geometry.py) ------------------
PAD = 22        # surface extends this far outside the shared rectangle
GRIP = 14       # corner grip square, flush outside the corner
HS = 22         # move handle square, flush outside the top-right corner
MIN_W, MIN_H = 120, 80

def clamp(g, mw, mh, pad=PAD):
    """Keep the shared rect plus all chrome (pad px around it) on a mw x mh monitor."""
    x, y, w, h = g
    w = max(MIN_W, min(w, mw - 2 * pad)); h = max(MIN_H, min(h, mh - 2 * pad))
    x = max(pad, min(x, mw - pad - w)); y = max(pad, min(y, mh - pad - h))
    return [x, y, w, h]

def drag_geom(start, mode, dx, dy, mw, mh):
    """start geometry + absolute pointer delta -> new geometry (clamped)."""
    x, y, w, h = start
    if mode == "move":
        return clamp([x + dx, y + dy, w, h], mw, mh)
    R, B = x + w, y + h
    if "l" in mode: x = min(x + dx, R - MIN_W)
    if "r" in mode: R = max(R + dx, x + MIN_W)
    if "t" in mode: y = min(y + dy, B - MIN_H)
    if "b" in mode: B = max(B + dy, y + MIN_H)
    x, y = max(PAD, x), max(PAD, y); R, B = min(R, mw - PAD), min(B, mh - PAD)
    return [x, y, R - x, B - y]

def offscreen(g, mw, mh):
    x, y, w, h = g
    return x < 0 or y < 0 or x + w > mw or y + h > mh or w < MIN_W or h < MIN_H

def fallback_monitor(saved, available):
    return saved if saved in available else focused_monitor()

def default_geom(mw, mh):
    w, h = min(1280, mw - 2 * PAD), min(720, mh - 2 * PAD)
    return [(mw - w) // 2, (mh - h) // 2, w, h]

def zones(w, h, b):
    """Interactive zones in surface coords (shared rect at PAD,PAD); all outside it."""
    P, G = PAD, GRIP; L, T, R, B = P, P, P + w, P + h
    return {"move": (R, T - HS, HS, HS),
            "tl": (L - G, T - G, G, G), "bl": (L - G, B, G, G), "br": (R, B, G, G),
            "t": (L, T - b, w, b), "b": (L, B, w, b), "l": (L - b, T, b, h), "r": (R, T, b, h)}

def abs_from_local(g, lx, ly):
    """Pointer in monitor coords = surface origin (rect - PAD) + surface-local event pos."""
    return g[0] - PAD + lx, g[1] - PAD + ly

def zones_abs(g, b):
    """Zones in monitor coords (the surface covers the whole monitor)."""
    ox, oy = g[0] - PAD, g[1] - PAD
    return {k: (x + ox, y + oy, w, h) for k, (x, y, w, h) in zones(g[2], g[3], b).items()}

def zone_at(g, b, px, py, editing=False):
    for k, (x, y, w, h) in zones_abs(g, b).items():
        s = 3 if len(k) == 1 else 0     # widen thin border strips a bit
        if x - s <= px < x + w + s and y - s <= py < y + h + s: return k
    if editing and g[0] <= px < g[0] + g[2] and g[1] <= py < g[1] + g[3]: return "move"
    return None

def focused_monitor():
    try:
        for m in json.loads(subprocess.check_output(["hyprctl", "monitors", "-j"])):
            if m.get("focused"): return m["name"]
    except Exception: pass
    return ""

def cursor_pos():
    p = json.loads(subprocess.check_output(["hyprctl", "cursorpos", "-j"]))
    return p["x"], p["y"]
