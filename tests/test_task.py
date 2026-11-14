"""`vs task`: client task history by code, deliveries with snapshots, feedback, resume, restore, hook listing."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "plugins" / "video-studio"
TOOLS = ROOT / "tools"


class TaskHistoryTest(unittest.TestCase):
    def setUp(self):
        self.ws = Path(tempfile.mkdtemp(prefix="vs-task-"))
        self.env = {**os.environ, "VS_WORKSPACE": str(self.ws)}
        self.p = self.ws / "projects" / "acme-ad"
        (self.p / "work").mkdir(parents=True)
        (self.p / "out" / "final").mkdir(parents=True)
        (self.p / "project.md").write_text("# Project: acme-ad\n")
        (self.p / "work" / "shots.json").write_text('{"H": [["Hook", "clip1", 0]]}')
        (self.p / "out" / "final" / "ad.mp4").write_bytes(b"\x00" * 2048)

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def task(self, *args, ok=True):
        r = subprocess.run([sys.executable, str(TOOLS / "task.py"), *args], capture_output=True, text=True,
                           env=self.env, cwd=self.ws)
        if ok and r.returncode:
            raise AssertionError(f"{args}\n{r.stdout}\n{r.stderr}")
        return r

    def data(self):
        return json.loads((self.ws / "history" / "TC0001.json").read_text())

    def test_full_cycle(self):
        self.task("new", "tc0001", "--project", "acme-ad", "--client", "Acme", "--title", "Spring ad",
                  "--brief", "9x16, 1 hook")
        self.assertIn("TC0001", (self.p / "project.md").read_text())
        self.task("deliver", "TC0001", "--file", "out/final/ad.mp4", "--link", "https://example.com/v1",
                  "--note", "first cut")
        snap = self.ws / "history" / "TC0001" / "v1"
        self.assertTrue((snap / "work" / "shots.json").exists())
        self.assertTrue((snap / "project.md").exists())
        self.task("feedback", "TC0001", "hook faster\n0:12 swap the shot", "--split", "--who", "Naomi")
        d = self.data()
        self.assertEqual(d["status"], "revising")
        self.assertEqual([f["on"] for f in d["feedback"]], ["v1", "v1"])
        out = self.task("resume", "TC0001").stdout
        self.assertIn("Open client feedback (2)", out)
        self.assertIn("#2 on v1", out)
        self.assertIn("first cut", out)
        self.task("done", "TC0001", "1", "--how", "two cuts in the hook")
        self.task("done", "TC0001", "2", "--skip", "client agreed to keep it")
        (self.p / "work" / "shots.json").write_text('{"H": [["Hook", "clip2", 0]]}')
        self.task("deliver", "TC0001", "--file", "out/final/ad.mp4", "--note", "faster hook")
        d = self.data()
        self.assertEqual([v["version"] for v in d["versions"]], ["v1", "v2"])
        self.assertIn("clip1", (self.ws / "history" / "TC0001" / "v1" / "work" / "shots.json").read_text())
        self.assertIn("clip2", (self.ws / "history" / "TC0001" / "v2" / "work" / "shots.json").read_text())
        md = (self.ws / "history" / "TC0001.md").read_text()
        self.assertIn("[x] #1", md)
        self.assertIn("[-] #2", md)
        self.assertIn("Open client feedback: none", self.task("resume", "TC0001").stdout)

    def test_restore_on_fresh_machine(self):
        self.task("new", "TC0001", "--project", "acme-ad")
        self.task("deliver", "TC0001", "--file", "out/final/ad.mp4")
        shutil.rmtree(self.p)
        self.assertIn("vs task restore TC0001", self.task("resume", "TC0001").stdout)
        self.task("restore", "TC0001")
        self.assertTrue((self.p / "work" / "shots.json").exists())

    def test_list_unknown_and_close(self):
        self.task("new", "TC0001", "--project", "acme-ad", "--client", "Acme")
        self.task("new", "TC0002", "--client", "Zeta")
        self.assertIn("TC0002", self.task("list", "--client", "zeta").stdout)
        self.task("close", "TC0002")
        self.assertNotIn("TC0002", self.task("list", "--open").stdout)
        r = self.task("resume", "TC9999", ok=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("TC0001", r.stderr)
        self.assertNotEqual(self.task("new", "bad code!", ok=False).returncode, 0)

    def test_session_start_lists_open_tasks(self):
        self.task("new", "TC0001", "--project", "acme-ad", "--client", "Acme", "--title", "Spring ad")
        self.task("feedback", "TC0001", "hook faster")
        envf = self.ws / "env.sh"
        r = subprocess.run(["bash", str(ROOT / "hooks" / "session-start.sh")], capture_output=True, text=True,
                           env={**self.env, "CLAUDE_ENV_FILE": str(envf), "CLAUDE_PLUGIN_ROOT": str(ROOT)})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("TC0001 (Acme: Spring ad) revising", r.stdout)
        self.assertIn("1 open feedback", r.stdout)
        self.assertIn("export PATH", envf.read_text())


if __name__ == "__main__":
    unittest.main()
