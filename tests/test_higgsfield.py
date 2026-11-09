"""`vs higgsfield` account connections (needs the `claude` CLI; skipped without it) and gen's account record."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "plugins" / "video-studio" / "tools"
sys.path.insert(0, str(TOOLS))
from higgsfield import server  # noqa: E402


def hf(*args, env=None):
    return subprocess.run([sys.executable, str(TOOLS / "higgsfield.py"), *args], capture_output=True, text=True,
                          env=env, timeout=300)


class HiggsfieldTest(unittest.TestCase):
    def test_names(self):
        self.assertEqual(server("Brand A"), "higgsfield-brand-a")
        self.assertEqual(server("default"), "higgsfield")
        self.assertEqual(server("client_b!"), "higgsfield-client-b")

    @unittest.skipUnless(shutil.which("claude"), "needs the claude CLI")
    def test_accounts_and_gen(self):
        home, ws = tempfile.mkdtemp(), tempfile.mkdtemp()
        env = {**os.environ, "HOME": home, "VS_WORKSPACE": ws}
        try:
            self.assertIn("added higgsfield-brand-a", hf("add", "brand-a", env=env).stdout)
            self.assertIn("Needs authentication", hf("list", env=env).stdout)
            hf("use", "brand-a", env=env)
            cur = json.loads(hf("current", env=env).stdout)
            self.assertEqual(cur["tool_prefix"], "mcp__higgsfield-brand-a__")
            script = Path(ws) / "v1.script.json"
            script.write_text(json.dumps({"presenter": {"look": "x", "consent": "fictional"},
                                          "lines": [{"say": "Hello there friends.", "show": "talking"}]}))
            r = subprocess.run([sys.executable, str(TOOLS / "gen.py"), "plan", str(script)], capture_output=True,
                               text=True, env=env)
            self.assertIn("mcp__higgsfield-brand-a__", r.stdout)
            self.assertEqual(json.loads((Path(ws) / "v1.jobs.json").read_text())["account"], "higgsfield-brand-a")
            hf("remove", "brand-a", env=env)
            self.assertNotIn("higgsfield-brand-a ", hf("list", env=env).stdout.split("active:")[0])
        finally:
            shutil.rmtree(home, ignore_errors=True)
            shutil.rmtree(ws, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
