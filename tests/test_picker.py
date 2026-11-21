import os, shutil, subprocess, tempfile, unittest

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FRAME_REGION = "[SELECTION]/region:DP-1@10,20,800,600"


class PickerTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.runtime = self.make_dir("run")
        self.bin = self.make_dir("bin")
        self.make_dir("cfg/share-frame")
        shutil.copy(os.path.join(REPO, "share-frame-picker"), self.dir)
        self.write("cfg/share-frame/config", "monitor = DP-1\nx = 10\ny = 20\nwidth = 800\nheight = 600\n")
        self.write("dialog-choice", "frame")
        self.write("picker_dialog.py",
                   f"open({self.path('dialogs')!r}, 'a').write('x')\n"
                   f"print(open({self.path('dialog-choice')!r}).read())\n")
        self.write_executable("share-frame", '[[ $1 == status ]] && echo "locked shown DP-1 800x600+10+20"\nexit 0\n')
        self.write("busctl-exit", "0")
        self.write_executable("bin/busctl", f'cat {self.path("portal-objects")}\nexit "$(cat {self.path("busctl-exit")})"\n')
        self.write_executable("bin/fallback-picker", "exit 1\n")
        self.waiting_requests()

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

    def waiting_requests(self, *apps):
        paths = ["/org/freedesktop/portal/desktop/session/1_7/gtk1"]
        paths += [f"/org/freedesktop/portal/desktop/request/{app}/webrtc{i}" for i, app in enumerate(apps)]
        self.write("portal-objects", "\n".join(paths) + "\n")

    def request_share(self, *apps):
        self.waiting_requests(*apps)
        env = dict(os.environ, XDG_RUNTIME_DIR=self.runtime, XDG_CONFIG_HOME=self.path("cfg"),
                   PATH=f"{self.bin}:{os.environ['PATH']}", SHARE_FRAME_FALLBACK_PICKER="fallback-picker")
        env.pop("SHARE_FRAME_PICK", None)
        result = subprocess.run([self.path("share-frame-picker")], env=env, capture_output=True, text=True)
        return result.stdout.strip()

    def dialogs_shown(self):
        if not os.path.exists(self.path("dialogs")):
            return 0
        with open(self.path("dialogs")) as f:
            return len(f.read())

    def test_same_app_asking_again_gets_the_frame_without_a_dialog(self):
        self.assertEqual(self.request_share("1_42"), FRAME_REGION)
        self.assertEqual(self.request_share("1_42"), FRAME_REGION)
        self.assertEqual(self.dialogs_shown(), 1)

    def test_another_app_asking_after_a_frame_choice_sees_the_dialog(self):
        self.request_share("1_42")
        self.request_share("1_99")
        self.assertEqual(self.dialogs_shown(), 2)

    def test_two_apps_waiting_at_once_always_see_the_dialog(self):
        self.request_share("1_42")
        self.request_share("1_42", "1_99")
        self.assertEqual(self.dialogs_shown(), 2)

    def test_choice_is_not_remembered_when_the_asking_app_is_unknown(self):
        self.request_share("1_42", "1_99")
        self.request_share("1_42")
        self.assertEqual(self.dialogs_shown(), 2)

    def test_failed_portal_lookup_with_partial_output_shows_the_dialog(self):
        self.request_share("1_42")
        self.write("busctl-exit", "1")
        self.request_share("1_42")
        self.assertEqual(self.dialogs_shown(), 2)

    def test_choosing_another_source_forgets_the_frame_choice(self):
        self.request_share("1_42")
        self.write("dialog-choice", "other")
        self.request_share("1_99")
        self.request_share("1_42")
        self.assertEqual(self.dialogs_shown(), 3)

    def test_choice_from_an_older_version_is_ignored(self):
        self.write("run/share-frame-last-pick", "9999999999\n")
        self.request_share("1_42")
        self.assertEqual(self.dialogs_shown(), 1)


if __name__ == "__main__":
    unittest.main()
