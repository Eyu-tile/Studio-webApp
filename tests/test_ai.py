"""`vs ai` commands on their built-in fallbacks (VS_NO_AI-independent: forced with --fallback where needed)."""
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
import numpy as np  # noqa: E402
from vs_common import probe  # noqa: E402


def sh(*cmd):
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if p.returncode:
        raise AssertionError(f"{cmd}\n{p.stdout}\n{p.stderr[-3000:]}")
    return p


def ai(*args):
    return sh(sys.executable, TOOLS / "ai.py", *args)


def pcm(path, start=0.5, dur=1.0):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(dur), "-i", str(path), "-ac", "1",
                          "-ar", "48000", "-f", "f32le", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.float32)


def band(x, f):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    fr = np.fft.rfftfreq(len(x), 1 / 48000)
    return spec[(fr > f - 20) & (fr < f + 20)].sum()


class AiFallbackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="vs-ai-"))
        cls.cwd = os.getcwd()
        os.chdir(cls.tmp)
        os.environ["VS_NO_AI"] = "1"
        Path("raw").mkdir()
        Path("work").mkdir()
        # A skin-coloured disc moving left -> right on a blue 16:9 background.
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x203080:s=640x360:r=25:d=4", "-vf",
           "geq=r='if(lt(hypot(X-(80+120*T),Y-180),45),225,32)':g='if(lt(hypot(X-(80+120*T),Y-180),45),170,48)'"
           ":b='if(lt(hypot(X-(80+120*T),Y-180),45),140,128)'", "-c:v", "libx264", "-pix_fmt", "yuv420p", "raw/walk.mp4")
        # Stereo: 440 Hz in the centre ("voice"), 880 Hz in opposite phase ("wide music").
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
           "aevalsrc='0.3*sin(2*PI*440*t)+0.3*sin(2*PI*880*t)|0.3*sin(2*PI*440*t)-0.3*sin(2*PI*880*t)':s=48000:d=3",
           "raw/mix.wav")
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=2", "-c:v", "libx264",
           "-pix_fmt", "yuv420p", "raw/clip.mp4")
        sh("ffmpeg", "-y", "-v", "error", "-i", "raw/clip.mp4", "-vf", "colorbalance=rs=0.3:bs=-0.3,eq=brightness=0.08",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "raw/warm.mp4")
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x00C000:s=320x240", "-vf",
           "drawbox=x=110:y=70:w=100:h=100:color=red:t=fill", "-frames:v", "1", "raw/prod.png")

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.cwd)
        os.environ.pop("VS_NO_AI", None)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_track_reframes_edl(self):
        Path("work/e.json").write_text(json.dumps({"source": "raw/walk.mp4", "segments": [{"start": 0, "end": 4}]}))
        r = ai("track", "work/e.json", "--aspect", "9:16")
        self.assertIn("skin+motion", r.stderr)
        kx = json.loads(Path("work/e.json").read_text())["segments"][0]["kf"]["x"]
        self.assertLess(kx[0][1], 0.3)
        self.assertGreater(kx[-1][1], kx[0][1] + 0.3)   # the crop follows the subject to the right
        sh(sys.executable, TOOLS / "render.py", "work/e.json", "-o", "out.mp4", "--aspect", "9:16", "--no-loudnorm")

    def test_match_lut(self):
        import re
        r = ai("match", "raw/clip.mp4", "raw/warm.mp4", "-o", "work/fix.cube")
        before, after = (float(x) for x in re.search(r"distance ([0-9]*\.[0-9]+) -> ([0-9]*\.[0-9]+)", r.stdout).groups())
        self.assertLess(after, before * 0.3)
        self.assertIn("LUT_3D_SIZE 33", Path("work/fix.cube").read_text()[:200])
        Path("work/m.json").write_text(json.dumps({"segments": [{"src": "raw/warm.mp4", "end": 2, "lut": "work/fix.cube"}]}))
        sh(sys.executable, TOOLS / "render.py", "work/m.json", "-o", "m.mp4", "--no-loudnorm")

    def test_stems_fallback(self):
        ai("stems", "raw/mix.wav", "-o", "work/stems", "--fallback")
        v, m = pcm("work/stems/vocals.wav"), pcm("work/stems/music.wav")
        self.assertGreater(band(v, 440), 10 * band(v, 880))
        self.assertGreater(band(m, 880), 10 * band(m, 440))

    def test_cutout_fallback(self):
        r = ai("cutout", "raw/prod.png", "-o", "work/prod.png", "--fallback")
        self.assertIn("flat-colour key", r.stderr)
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", "work/prod.png", "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
                             capture_output=True).stdout
        img = np.frombuffer(raw, np.uint8).reshape(240, 320, 4)
        self.assertLess(img[10, 10, 3], 20)      # background transparent
        self.assertGreater(img[120, 160, 3], 200)  # product kept

    def test_upscale_and_interpolate_fallbacks(self):
        ai("upscale", "raw/clip.mp4", "-o", "work/up.mp4", "--scale", "2", "--fallback")
        self.assertEqual((probe.__wrapped__("work/up.mp4")["width"]), 640)
        ai("interpolate", "raw/clip.mp4", "-o", "work/i50.mp4", "--fps", "50", "--fallback")
        self.assertAlmostEqual(probe.__wrapped__("work/i50.mp4")["fps"], 50, delta=0.5)
        ai("interpolate", "raw/clip.mp4", "-o", "work/slow.mp4", "--slowmo", "2", "--fallback")
        self.assertAlmostEqual(probe.__wrapped__("work/slow.mp4")["duration"], 4.0, delta=0.15)

    def test_status(self):
        self.assertIn("fallback in use", ai("status").stdout)


if __name__ == "__main__":
    unittest.main()
