"""`vs keys`: per-project API keys, pop-up entry, lookup order, exec, and that values are never printed."""
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "plugins" / "video-studio" / "tools"
SECRET_A = "sk_projectA_0000aaaa"
SECRET_B = "sk_projectB_1111bbbb"
SECRET_G = "sk_global_2222gggg"


class KeysTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vs-keys-"))
        self.env = {k: v for k, v in os.environ.items() if not k.endswith(("_API_KEY", "_CLIENT_ID", "_ACCESS_KEY"))}
        self.env.update(VS_KEYS_DIR=str(self.tmp / "cfg"))
        for k in ("DISPLAY", "WAYLAND_DISPLAY", "VS_KEYS_FILE", "VS_KEYS_DIALOG_CMD"):
            self.env.pop(k, None)

    def keys(self, *args, ok=True, env=None, stdin=None, cwd=None):
        p = subprocess.run([sys.executable, str(TOOLS / "keys.py"), *args], capture_output=True, text=True,
                           env={**self.env, **(env or {})}, input=stdin, cwd=cwd or self.tmp)
        if ok and p.returncode:
            raise AssertionError(f"{args}\n{p.stdout}\n{p.stderr}")
        for s in (SECRET_A, SECRET_B, SECRET_G):
            self.assertNotIn(s, p.stdout + p.stderr, "a key value was printed")
        return p

    def test_project_overrides_machine_wide(self):
        self.keys("set", "elevenlabs", stdin=SECRET_G + "\n")
        self.keys("set", "elevenlabs", "--project", "acme", stdin=SECRET_A + "\n")
        self.keys("set", "elevenlabs", "--project", "zeta", stdin=SECRET_B + "\n")
        self.assertIn("project acme", self.keys("check", "elevenlabs", "--project", "acme").stdout)
        self.assertIn("aaaa", self.keys("check", "elevenlabs", "--project", "acme").stdout)
        self.assertIn("bbbb", self.keys("check", "elevenlabs", "--project", "zeta").stdout)
        self.assertIn("machine-wide", self.keys("check", "elevenlabs", "--project", "other").stdout)
        # files are private
        f = self.tmp / "cfg" / "projects" / "acme.env"
        self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600)

    def test_exec_injects_the_projects_key(self):
        self.keys("set", "elevenlabs", "--project", "acme", stdin=SECRET_A + "\n")
        probe = [sys.executable, "-c", "import os;print(os.environ['ELEVENLABS_API_KEY']=='%s')" % SECRET_A]
        p = self.keys("exec", "--project", "acme", "--", *probe)
        self.assertEqual(p.stdout.strip(), "True")

    def test_project_detected_from_cwd(self):
        d = self.tmp / "video-studio" / "projects" / "acme" / "work"
        d.mkdir(parents=True)
        self.keys("set", "heygen", stdin=SECRET_A + "\n", cwd=d)
        self.assertTrue((self.tmp / "cfg" / "projects" / "acme.env").exists())

    def test_missing_key_exit_code(self):
        p = self.keys("check", "openai", "--project", "acme", ok=False)
        self.assertEqual(p.returncode, 1)
        self.assertIn("vs keys ask openai --project acme", p.stdout)

    def test_ask_uses_popup_and_saves(self):
        helper = self.tmp / "fake_dialog.py"
        helper.write_text(f"print('{SECRET_A}')\n")
        p = self.keys("ask", "elevenlabs", "--project", "acme",
                      env={"VS_KEYS_DIALOG_CMD": f"{sys.executable} {helper}"})
        self.assertIn("saved for project acme", p.stdout)
        self.assertIn("aaaa", self.keys("check", "elevenlabs", "--project", "acme").stdout)
        # already set: no second pop-up unless --force
        self.assertIn("already set", self.keys("ask", "elevenlabs", "--project", "acme").stdout)

    def test_ask_cancelled(self):
        p = self.keys("ask", "elevenlabs", "--project", "acme", ok=False, env={"VS_KEYS_DIALOG_CMD": "false"})
        self.assertEqual(p.returncode, 2)

    def test_ask_without_desktop_explains_alternatives(self):
        p = self.keys("ask", "elevenlabs", "--project", "acme", ok=False)
        if p.returncode == 0:  # a real desktop dialog ran (developer machine); nothing to assert
            return
        self.assertEqual(p.returncode, 3)
        self.assertIn("vs keys set elevenlabs --project acme", p.stderr)

    def test_list_masks_values(self):
        self.keys("set", "elevenlabs", "--project", "acme", stdin=SECRET_A + "\n")
        out = self.keys("list", "--project", "acme").stdout
        self.assertIn("…aaaa", out)


if __name__ == "__main__":
    unittest.main()
