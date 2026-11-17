"""Frame accuracy of the renderer, measured with a source whose every frame encodes its own number, and the
speed-path equivalences (needs ffmpeg + numpy).

Before 2026-11, shots cut at in-points between two source frames showed the previous source frame on 1 in 6
output frames (82.5 % exact). Seeking a little early and trimming to the in-point fixed it (97.3 %); the shared
decoder for jump cuts (one decoder per run of shots) must give pixel-identical output.

Run: python3 -m unittest discover -s tests -v
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
VS = ROOT / "plugins" / "video-studio" / "bin" / "vs"
FPS = 30
# a jump-cut pattern taken from a real 2:35 talking-head edit (in/out points between frames)
CUTS = [(4.72, 8.98), (9.38, 13.2), (13.56, 15.2), (16.08, 17.74), (18.08, 19.54), (20.24, 21.72), (22.14, 23.68),
        (24.26, 25.38)]


def sh(*cmd, env=None, ok=True, cwd=None):
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, env=env, cwd=cwd)
    if ok and p.returncode != 0:
        raise AssertionError(f"{' '.join(map(str, cmd))}\n{p.stdout}\n{p.stderr[-2500:]}")
    return p


class AccuracyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="vs-acc-"))
        # every frame's brightness = (frame number mod 50) * 5; long GOP like screen/web recordings
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
           f"color=c=black:s=320x180:r={FPS}:d=30,format=gray,geq=lum='mod(N\\,50)*5'", "-f", "lavfi", "-i",
           "sine=d=30", "-shortest", "-c:v", "libx264", "-preset", "veryfast", "-crf", "1", "-g", "250",
           "-pix_fmt", "yuv420p", "-c:a", "aac", cls.tmp / "num.mp4")
        cls.edl = {"segments": [{"src": str(cls.tmp / "num.mp4"), "start": a, "end": b} for a, b in CUTS]}
        (cls.tmp / "edl.json").write_text(json.dumps(cls.edl))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def render(self, name, env=None):
        sh(VS, "render", self.tmp / "edl.json", "-o", self.tmp / name, env={**os.environ, **(env or {})})
        return self.tmp / name

    def exactness(self, video):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", "scale=16:16,format=gray", "-f",
                              "rawvideo", "-"], capture_output=True).stdout
        got = np.round(np.frombuffer(raw, np.uint8).reshape(-1, 256).mean(axis=1) / 5).astype(int) % 50
        starts, t = [], 0.0
        for a, b in CUTS:
            starts.append(t)
            t += b - a
        errs = []
        for i, g in enumerate(got):
            tc = (i + 0.5) / FPS
            k = max(j for j, o in enumerate(starts) if o <= tc + 1e-9)
            ideal = int(np.floor((CUTS[k][0] + tc - starts[k]) * FPS + 1e-6)) % 50
            errs.append((g - ideal + 25) % 50 - 25)
        return np.mean(np.array(errs) == 0)

    def test_frame_accuracy(self):
        self.assertGreaterEqual(self.exactness(self.render("shared.mp4")), 0.95)

    def test_shared_decoder_is_pixel_identical(self):
        a, b = self.render("s.mp4"), self.render("p.mp4", {"VS_NO_SHARE": "1"})
        p = sh("ffmpeg", "-hide_banner", "-i", a, "-i", b, "-lavfi", "[0:v][1:v]psnr", "-f", "null", "-")
        self.assertEqual(re.findall(r"average:(\S+)", p.stderr)[-1], "inf")

    def test_empty_sound_plan_is_not_an_error(self):
        p = sh(VS, "sfx", "plan", "--edl", self.tmp / "edl.json", "--style", "talking-head", "-o",
               self.tmp / "sfx.json", "--library-only", "--library", self.tmp)
        self.assertIn("0 cues", p.stdout)
        self.assertEqual(json.loads((self.tmp / "sfx.json").read_text())["plan"], [])


if __name__ == "__main__":
    unittest.main()
