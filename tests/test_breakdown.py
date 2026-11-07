"""`vs breakdown` recovers cuts, camera moves, dips and tempo from a reference made with `vs render`."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "plugins" / "video-studio" / "tools"


def sh(*cmd):
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if p.returncode:
        raise AssertionError(f"{cmd}\n{p.stderr[-3000:]}")
    return p


class BreakdownTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="vs-bd-"))
        cls.cwd = os.getcwd()
        os.chdir(cls.tmp)
        Path("raw").mkdir()
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "mandelbrot=s=1280x720", "-frames:v", "1", "raw/m.png")
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1280x720", "-frames:v", "1",
           "-vf", "format=rgb24", "raw/c.png")
        # 120 BPM click track.
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
           "aevalsrc='0.8*sin(2*PI*1500*t)*exp(-60*mod(t,0.5))':s=48000:d=12", "raw/click.wav")
        edl = {"segments": [
            {"src": "raw/m.png", "end": 2.5, "ken_burns": False},
            {"src": "raw/c.png", "end": 2.5, "kf": {"zoom": [[0, 1.0, "linear"], [2.5, 1.4, "linear"]]}},
            {"src": "raw/m.png", "end": 2.5, "zoom": 1.5, "kf": {"x": [[0, 0.0, "linear"], [2.5, 1.0, "linear"]]}},
            {"src": "raw/c.png", "end": 2.5, "ken_burns": False, "transition_in": {"type": "dip-black", "dur": 0.6}}],
            "audio_track": {"src": "raw/click.wav"}}
        Path("edl.json").write_text(json.dumps(edl))
        sh(sys.executable, TOOLS / "render.py", "edl.json", "-o", "ref.mp4", "--no-loudnorm", "--fps", "25")
        sh(sys.executable, TOOLS / "breakdown.py", "ref.mp4", "-o", "bd")
        cls.keep = cls.tmp
        cls.bd = json.loads(Path("bd/breakdown.json").read_text())

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.cwd)
        if not os.environ.get("VS_KEEP"):
            shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_shots_and_moves(self):
        shots = self.bd["shots"]
        self.assertEqual(len(shots), 4, [(s["start"], s["camera"]["move"]) for s in shots])
        moves = [s["camera"]["move"] for s in shots]
        self.assertIn(moves[0], ("static", "frozen / still"))
        self.assertTrue(moves[1].startswith("push in"), moves)
        self.assertTrue(moves[2].startswith("pan right"), moves)
        self.assertEqual(shots[3]["transition_in"], "dip-black")

    def test_tempo_and_outputs(self):
        self.assertAlmostEqual(self.bd["sound"]["bpm"], 120, delta=3)
        for f in ("report.md", "sheet.png", "remake_edl.json"):
            self.assertTrue(Path("bd", f).exists(), f)
        remake = json.loads(Path("bd/remake_edl.json").read_text())
        self.assertEqual(len(remake["segments"]), 4)
        self.assertIn("zoom", remake["segments"][1]["kf"])
        self.assertIn("x", remake["segments"][2]["kf"])


if __name__ == "__main__":
    unittest.main()
