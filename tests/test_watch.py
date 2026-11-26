import os, shutil, subprocess, tempfile, time, unittest

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
STREAM_DUMP = '[{"info": {"props": {"media.name": "xdph-streaming"}}}]'
OTHER_DUMP = '[{"info": {"props": {"media.name": "Integrated_Webcam_HD"}}}]'


class WatchTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.runtime = self.make_dir("run")
        self.bin = self.make_dir("bin")
        shutil.copy(os.path.join(REPO, "share-frame-watch"), self.dir)
        self.write("dump", OTHER_DUMP)
        self.write("pw-dump-exit", "0")
        self.write_executable("bin/pw-dump", f'cat {self.path("dump")}\nexit "$(cat {self.path("pw-dump-exit")})"\n')
        self.write_executable("share-frame", f'echo "$1" >> {self.path("calls")}\n')
        self.marker = os.path.join(self.runtime, "share-frame-sharing")
        self.process = None
        self.addCleanup(self.stop_watching)

    def make_dir(self, name):
        os.makedirs(self.path(name))
        return self.path(name)

    def path(self, name):
        return os.path.join(self.dir, name)

    def write(self, name, text):
        with open(self.path(name), "w") as f:
            f.write(text)

    def write_executable(self, name, body):
        self.write(name, "#!/usr/bin/env bash\n" + body)
        os.chmod(self.path(name), 0o755)

    def start_watching(self, hide_delay="0"):
        env = dict(os.environ, XDG_RUNTIME_DIR=self.runtime, PATH=f"{self.bin}:{os.environ['PATH']}",
                   SHARE_FRAME_HIDE_DELAY=hide_delay, SHARE_FRAME_POLL_SECONDS="0.05")
        self.process = subprocess.Popen([self.path("share-frame-watch")], env=env)

    def stop_watching(self):
        if self.process:
            self.process.kill()
            self.process.wait()

    def mark_sharing(self):
        open(self.marker, "w").close()

    def settle(self, seconds=0.5):
        time.sleep(seconds)

    def hide_calls(self):
        if not os.path.exists(self.path("calls")):
            return 0
        with open(self.path("calls")) as f:
            return f.read().split().count("hide")

    def test_frame_stays_while_the_screencast_stream_exists(self):
        self.mark_sharing()
        self.write("dump", STREAM_DUMP)
        self.start_watching()
        self.settle()
        self.assertEqual(self.hide_calls(), 0)
        self.assertTrue(os.path.exists(self.marker))

    def test_frame_hides_when_the_screencast_stream_is_gone(self):
        self.mark_sharing()
        self.write("dump", STREAM_DUMP)
        self.start_watching()
        self.settle()
        self.write("dump", OTHER_DUMP)
        self.settle()
        self.assertEqual(self.hide_calls(), 1)
        self.assertFalse(os.path.exists(self.marker))

    def test_frame_stays_before_the_stream_has_started(self):
        self.mark_sharing()
        self.start_watching()
        self.settle()
        self.assertEqual(self.hide_calls(), 0)
        self.assertTrue(os.path.exists(self.marker))

    def test_frame_stays_when_the_stream_returns_within_the_hide_delay(self):
        self.mark_sharing()
        self.write("dump", STREAM_DUMP)
        self.start_watching(hide_delay="2")
        self.settle()
        self.write("dump", OTHER_DUMP)
        self.settle(0.5)
        self.write("dump", STREAM_DUMP)
        self.settle(2.5)
        self.assertEqual(self.hide_calls(), 0)

    def test_frame_stays_when_pipewire_cannot_be_queried(self):
        self.mark_sharing()
        self.write("dump", STREAM_DUMP)
        self.start_watching()
        self.settle()
        self.write("pw-dump-exit", "1")
        self.write("dump", "")
        self.settle()
        self.assertEqual(self.hide_calls(), 0)

    def test_frame_shown_by_hand_is_left_alone_when_a_stream_ends(self):
        self.write("dump", STREAM_DUMP)
        self.start_watching()
        self.settle()
        self.write("dump", OTHER_DUMP)
        self.settle()
        self.assertEqual(self.hide_calls(), 0)


if __name__ == "__main__":
    unittest.main()
