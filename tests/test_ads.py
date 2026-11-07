"""`vs ads` (brief, plan, qa, sheet), `vs review --brief`, and platform safe zones in captions/texts."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "plugins" / "video-studio" / "tools"


def sh(*cmd, ok=True):
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if ok and p.returncode:
        raise AssertionError(f"{cmd}\n{p.stdout}\n{p.stderr[-3000:]}")
    return p


def vs(tool, *args, ok=True):
    return sh(sys.executable, TOOLS / f"{tool}.py", *args, ok=ok)


GOOD_BRIEF = {
    "client": "Acme", "product": "KneeEase", "offer": "30% off today", "cta": "Shop now 30% off",
    "format": "ugc", "platform": "reels", "length": [6, 12],
    "audience": {"who": "women 55-70 with knee pain who garden", "age": "55+", "gender": "female"},
    "emotion": "pain relief", "awareness": "problem", "angles": ["gardening pain", "stairs", "doctor said"],
    "variants": 3,
    "claims": [{"claim": "Warms in 60 seconds", "evidence": "lab test 2026-03", "source": "client/tests.pdf"}],
    "creator": {"name": "Jo", "paid": True, "disclosure": "Paid partnership label"},
    "policy": {"category": "health", "before_after": False}, "brand": {"accent": "#FF6A2B"}}


class AdsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="vs-ads-"))
        cls.cwd = os.getcwd()
        os.chdir(cls.tmp)
        for d in ("raw", "work", "out/ads"):
            Path(d).mkdir(parents=True)
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=25:d=12", "-f", "lavfi",
           "-i", "sine=f=300:d=12", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "raw/a.mp4")
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=200:d=12", "raw/bed.wav")
        Path("work/brief.json").write_text(json.dumps(GOOD_BRIEF))
        words = [{"w": w, "s": 0.05 + 0.4 * i, "e": 0.4 + 0.4 * i} for i, w in enumerate(
            "My knees hurt every time I garden until I found this.".split())]
        Path("work/t.json").write_text(json.dumps({"source": "raw/a.mp4", "words": words}))

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.cwd)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def edl(self, name, **over):
        e = {"source": "raw/a.mp4",
             "segments": [{"start": 0, "end": 2.5, "zoom": 1.1}, {"start": 3, "end": 5.5}, {"start": 6, "end": 9}],
             "texts": [{"text": "KNEES HURT?", "start": 0.1, "end": 2.0, "pos": "top"},
                       {"text": "Shop now - 30% off", "start": 5.0, "end": 8.0, "pos": "bottom"}],
             "music": {"file": "raw/bed.wav", "gain_db": -18, "duck": True}}
        e.update(over)
        Path(f"work/{name}.json").write_text(json.dumps(e))
        return f"work/{name}.json"

    def test_brief_checks(self):
        r = vs("ads", "brief", "work/new.json")
        self.assertIn("template", r.stdout)
        self.assertEqual(vs("ads", "brief", "work/new.json", ok=False).returncode, 1)   # empty template fails
        self.assertEqual(vs("ads", "brief", "work/brief.json").returncode, 0)
        bad = dict(GOOD_BRIEF, policy={"category": "weight_loss", "before_after": True},
                   creator={"name": "Jo", "paid": True, "disclosure": ""},
                   claims=[{"claim": "Lose 10 lbs", "evidence": ""}])
        Path("work/bad.json").write_text(json.dumps(bad))
        out = vs("ads", "brief", "work/bad.json", ok=False).stdout
        self.assertIn("before/after", out)
        self.assertIn("disclosure", out)
        self.assertIn("without evidence", out)

    def test_plan(self):
        vs("ads", "plan", "work/brief.json", "-o", "work/ads", "--length", "10")
        plan = json.loads(Path("work/ads/plan.json").read_text())
        self.assertEqual(len(plan["variants"]), 3)
        v = plan["variants"][0]
        self.assertEqual(v["beats"][0]["beat"], "hook")
        self.assertLessEqual(v["beats"][0]["end"], 3.0)
        self.assertAlmostEqual(v["beats"][-1]["end"], 10, delta=0.2)
        self.assertEqual(plan["hook"]["type"], "call out the problem")
        self.assertIn("--preset", plan["captions_args"])
        self.assertEqual(plan["safe_zone"]["bottom"], 0.35)
        self.assertIn("gardening pain", Path("work/ads/plan.md").read_text())

    def test_qa_good_and_bad(self):
        e = self.edl("good")
        vs("captions", "work/t.json", e, "-o", "work/good_cap", "--style", "bold-pop", "--preset", "reels")
        ass = Path("work/good_cap.ass").read_text()
        style = next(line for line in ass.splitlines() if line.startswith("Style:")).split(",")
        self.assertGreaterEqual(int(style[21]) / 1920, 0.35)                     # captions above the Reels UI
        vs("render", e, "-o", "out/ads/good.mp4", "--preset", "reels", "--captions", "work/good_cap.ass")
        r = vs("ads", "qa", "out/ads/good.mp4", "--edl", e, "--brief", "work/brief.json", "--captions",
               "work/good_cap.ass", "-o", "out/ads/good.qa.json", ok=False)
        self.assertEqual(r.returncode, 0, r.stdout)
        for check in ("words-on-screen", "safe-zone", "cta", "stimulus", "true-peak", "compliance"):
            self.assertRegex(r.stdout, rf"PASS\s+{check}")
        # Bad: late first text, a 5 s static shot, no CTA.
        b = self.edl("bad", segments=[{"start": 0, "end": 1.5}, {"start": 2, "end": 7.5}],
                     texts=[{"text": "hello", "start": 1.2, "end": 2.0}])
        vs("render", b, "-o", "out/ads/bad.mp4", "--preset", "reels")
        r = vs("ads", "qa", "out/ads/bad.mp4", "--edl", b, "--brief", "work/brief.json", "-o", "out/ads/bad.qa.json",
               ok=False)
        self.assertEqual(r.returncode, 1)
        for check in ("words-on-screen", "stimulus", "cta"):
            self.assertRegex(r.stdout, rf"FAIL\s+{check}")
        vs("ads", "sheet", "out/ads", "-o", "out/ads/review.html", "--brief", "work/brief.json")
        page = Path("out/ads/review.html").read_text()
        self.assertEqual(page.count("<video"), 2)
        self.assertIn("FAIL", page)
        # Through the review loop.
        r = vs("review", b, "--brief", "work/brief.json", "--preset", "reels", "--dir", "work/rv", ok=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("ad cta", Path("work/rv/r01/review.md").read_text())

    def test_texts_respect_safe_zone(self):
        e = self.edl("zone", texts=[{"text": "LOW", "start": 0, "end": 2, "pos": "bottom"}])
        vs("render", e, "-o", "out/zone.mp4", "--preset", "reels", "--preview")
        ass = Path("out/zone.texts.ass").read_text()
        style = next(line for line in ass.splitlines() if line.startswith("Style: T0")).split(",")
        play_h = int(next(line for line in ass.splitlines() if line.startswith("PlayResY")).split(":")[1])
        self.assertGreaterEqual(int(style[21]) / play_h, 0.36)


if __name__ == "__main__":
    unittest.main()
