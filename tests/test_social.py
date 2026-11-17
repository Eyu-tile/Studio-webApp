"""Tests for `vs social`: upload files per platform, limit checks (length, aspect, caption, hashtags, X link length,
YouTube title, Instagram public URL, confirmed account), the approval plan, logging a post on the task, and the
preference (needs ffmpeg). Posting itself runs through Composio and is not exercised here.

Run: python3 -m unittest discover -s tests -v
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VS = ROOT / "plugins" / "video-studio" / "bin" / "vs"


def sh(*cmd, env=None, ok=True, cwd=None):
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, env=env, cwd=cwd)
    if ok and p.returncode != 0:
        raise AssertionError(f"{' '.join(map(str, cmd))}\n{p.stdout}\n{p.stderr[-2000:]}")
    return p


class SocialTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="vs-social-"))
        cls.ws = cls.tmp / "video-studio"
        cls.env = {**os.environ, "VS_WORKSPACE": str(cls.ws)}
        sh(VS, "new", "demo", env=cls.env, cwd=cls.tmp)
        out = cls.ws / "projects" / "demo" / "out"
        out.mkdir(parents=True, exist_ok=True)
        cls.wide = out / "final.mov"          # 16:9, 12 s, needs re-encoding (not an mp4)
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=12", "-f", "lavfi",
           "-i", "sine=d=12", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", cls.wide)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def vs(self, *args, ok=True):
        return sh(VS, *args, env=self.env, ok=ok, cwd=self.tmp)

    def post(self):
        return self.ws / "projects" / "demo" / "out" / "social" / "v1" / "post.json"

    def test_prep_check_and_log(self):
        self.vs("social", "prep", self.wide, "--project", "demo", "--platforms", "tiktok,reels,x,youtube",
                "--title", "Launch reel")
        f = self.post()
        data = json.loads(f.read_text())
        self.assertEqual(list(data["posts"]), ["tiktok", "reels", "x", "youtube"])
        up = Path(data["posts"]["x"]["file"])
        self.assertEqual(up.suffix, ".mp4")                                       # .mov re-encoded for upload
        self.assertTrue((f.parent / "cover.jpg").exists() and (f.parent / "post_plan.md").exists())
        self.assertTrue(any("aspect" in p for p in data["posts"]["tiktok"]["file_problems"]))   # 16:9 on TikTok
        self.assertEqual(data["posts"]["x"]["file_problems"], [])
        self.assertEqual(data["posts"]["youtube"]["privacy"], "private")          # safe default
        self.assertEqual(data["posts"]["tiktok"]["privacy"], "SELF_ONLY")
        self.assertNotEqual(self.vs("social", "check", f, ok=False).returncode, 0)  # captions/accounts missing

        # fill in: X caption over 280 once links count 23; 31 hashtags on Reels; long YouTube title; no public URL
        data["posts"]["x"].update(caption="a" * 250 + " https://example.com/a/very/long/link/that/counts/as/23",
                                  account="@brand")
        data["posts"]["reels"].update(caption="Launch " + " ".join(f"#t{i}" for i in range(31)), account="brand")
        data["posts"]["youtube"].update(caption="Description", title="T" * 101, account="Brand channel")
        data["posts"]["tiktok"].update(caption="Launch day", account="@brand")
        f.write_text(json.dumps(data))
        out = self.vs("social", "check", f, ok=False).stdout
        self.assertIn("X: ready", out)                                            # 250 + 1 + 23 = 274 <= 280
        self.assertIn("31 hashtags > 30", out)
        self.assertIn("public direct URL", out)
        self.assertIn("title 101 characters > 100", out)
        data = json.loads(f.read_text())
        data["posts"]["x"]["caption"] = "b" * 260 + " https://example.com/x"
        data["posts"]["reels"].update(caption="Launch #new", public_url="https://cdn.example.com/launch.mp4",
                                      accept_aspect=True)                     # the person accepts letterboxing
        data["posts"]["youtube"]["title"] = "Launch reel"
        data["posts"].pop("tiktok")                                               # 16:9 file: not for TikTok
        f.write_text(json.dumps(data))
        out = self.vs("social", "check", f, ok=False)
        self.assertIn("caption 284 characters > 280", out.stdout)
        data = json.loads(f.read_text())
        data["posts"]["x"]["caption"] = "Launch day https://example.com/x"
        f.write_text(json.dumps(data))
        self.assertEqual(self.vs("social", "check", f).returncode, 0)            # all ready
        plan = (f.parent / "post_plan.md").read_text()
        self.assertIn("| X | @brand |", plan)
        self.assertIn("Nothing is posted until the person approves this table", plan)

        # re-running prep keeps the written captions and accounts
        self.vs("social", "prep", self.wide, "--project", "demo", "--platforms", "x,youtube")
        kept = json.loads(f.read_text())["posts"]
        self.assertEqual((kept["x"]["account"], kept["youtube"]["title"]), ("@brand", "Launch reel"))

    def test_log_on_task_and_pref(self):
        self.vs("task", "new", "TC0002", "--project", "demo", "--client", "Acme")
        out = self.vs("task", "deliver", "TC0002", "--file", self.wide).stdout
        self.assertIn("posting to social media", out)
        self.vs("social", "prep", self.wide, "--project", "demo", "--platforms", "x", "--task", "TC0002",
                "-o", self.tmp / "s2")
        self.vs("social", "log", self.tmp / "s2" / "post.json", "x", "--url", "https://x.com/brand/status/1")
        t = json.loads((self.ws / "history" / "TC0002.json").read_text())
        self.assertEqual(t["versions"][-1]["posts"][0]["url"], "https://x.com/brand/status/1")
        self.assertEqual(self.vs("social", "pref").stdout.strip(), "ask")
        self.vs("social", "pref", "never")
        out = self.vs("task", "deliver", "TC0002", "--file", self.wide, "--version", "v2").stdout
        self.assertNotIn("posting to social media", out)
        self.vs("social", "pref", "ask")
        self.assertNotEqual(self.vs("social", "prep", self.wide, "--platforms", "myspace", ok=False).returncode, 0)


if __name__ == "__main__":
    unittest.main()
