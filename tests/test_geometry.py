import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sf_core import *

MW, MH = 5120, 1440
class T(unittest.TestCase):
    def test_move_is_absolute_no_accumulation(self):
        s = [100, 100, 1280, 720]
        # repeated updates with the same absolute delta give the same result
        for _ in range(50): g = drag_geom(s, "move", 300, 50, MW, MH)
        self.assertEqual(g, [400, 150, 1280, 720])
    def test_move_clamped_on_screen(self):
        g = drag_geom([100, 100, 1280, 720], "move", -5000, 5000, MW, MH)
        self.assertEqual(g, [PAD, MH - PAD - 720, 1280, 720])
        g = drag_geom([100, 100, 1280, 720], "move", 99999, -999, MW, MH)
        self.assertEqual(g[0] + g[2] + PAD, MW); self.assertEqual(g[1], PAD)
    def test_handle_on_screen(self):
        g = drag_geom([100, 100, 1280, 720], "move", 99999, -999, MW, MH)
        hx, hy, hw, hh = zones(g[2], g[3], 4)["move"]
        sx, sy = g[0] - PAD + hx, g[1] - PAD + hy
        self.assertTrue(0 <= sx and sx + hw <= MW and 0 <= sy and sy + hh <= MH)
    def test_resize_corners_and_min(self):
        s = [100, 100, 1280, 720]
        self.assertEqual(drag_geom(s, "br", 100, 50, MW, MH), [100, 100, 1380, 770])
        self.assertEqual(drag_geom(s, "tl", 50, 20, MW, MH), [150, 120, 1230, 700])
        g = drag_geom(s, "br", -5000, -5000, MW, MH)
        self.assertEqual(g[2:], [MIN_W, MIN_H])
        g = drag_geom(s, "tl", 5000, 5000, MW, MH)
        self.assertEqual(g, [100 + 1280 - MIN_W, 100 + 720 - MIN_H, MIN_W, MIN_H])
        g = drag_geom(s, "l", -5000, 0, MW, MH); self.assertEqual(g[0], PAD)
    def test_offscreen_reset(self):
        self.assertTrue(offscreen([-1669, 1020, 1280, 720], MW, MH))
        self.assertFalse(offscreen([100, 100, 1280, 720], MW, MH))
        self.assertEqual(default_geom(MW, MH), [1920, 360, 1280, 720])
    def test_handle_flush_at_top_right_corner(self):
        x, y, w, h = zones(1280, 720, 4)["move"]
        self.assertEqual((x, y + h), (PAD + 1280, PAD))  # bottom-left of handle = corner
    def test_zones_outside_shared_rect(self):
        for k, (x, y, w, h) in zones(1280, 720, 4).items():
            inside = x < PAD + 1280 and x + w > PAD and y < PAD + 720 and y + h > PAD
            self.assertFalse(inside, k)
    def test_color_survives_comment_parsing(self):
        import tempfile
        p = tempfile.mktemp(); save(p, dict(DEFAULTS)); self.assertEqual(load(p)["color"], "#89b4fa"); os.unlink(p)
    def test_origin_plus_local_is_stable(self):
        # pointer fixed on screen at (500, 300); surface moves, local coords shift oppositely
        for g in ([100, 100, 1280, 720], [400, 150, 1280, 720], [PAD, PAD, 640, 480]):
            lx, ly = 500 - (g[0] - PAD), 300 - (g[1] - PAD)
            self.assertEqual(abs_from_local(g, lx, ly), (500, 300))
    def test_simulated_drag_no_runaway(self):
        g = [100, 100, 1280, 720]; start = list(g); p0 = abs_from_local(g, PAD + 1290, 10)
        for step in range(1, 101):          # mouse moves +3,+1 px per event
            ax, ay = p0[0] + 3 * step, p0[1] + step
            lx, ly = ax - (g[0] - PAD), ay - (g[1] - PAD)     # what GTK reports locally
            p = abs_from_local(g, lx, ly)
            g = drag_geom(start, "move", p[0] - p0[0], p[1] - p0[1], MW, MH)
        self.assertEqual(g, [400, 200, 1280, 720])
    def test_zone_hit_abs(self):
        g = [100, 100, 1280, 720]
        self.assertEqual(zone_at(g, 4, 100 + 1280 + 11, 100 - 11), "move")   # handle center
        self.assertEqual(zone_at(g, 4, 100 - 7, 100 + 720 + 7), "bl")
        self.assertEqual(zone_at(g, 4, 700, 400), None)                      # interior passes
        self.assertEqual(zone_at(g, 4, 700, 400, editing=True), "move")
        self.assertEqual(zone_at(g, 4, 100 + 1281, 400), "r")
    def test_fixed_surface_drag_press_offset_preserved(self):
        # surface never moves: pointer delta == box delta, grab offset preserved
        g = [100, 100, 1280, 720]; p0 = (1391, 89)
        g2 = drag_geom(g, "move", 1500 - p0[0], 300 - p0[1], MW, MH)
        hx, hy, _, _ = zones_abs(g, 4)["move"]; hx2, hy2, _, _ = zones_abs(g2, 4)["move"]
        self.assertEqual((p0[0] - hx, p0[1] - hy), (1500 - hx2, 300 - hy2))
unittest.main()
