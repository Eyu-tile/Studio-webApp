"""`vs translate` (export, check, subs, dub) and `vs thumbs` ranking."""
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


def sh(*cmd, ok=True):
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if ok and p.returncode:
        raise AssertionError(f"{cmd}\n{p.stdout}\n{p.stderr[-3000:]}")
    return p


def tr(*args, ok=True):
    return sh(sys.executable, TOOLS / "translate.py", *args, ok=ok)


def rms(path, start, dur):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(dur), "-i", str(path), "-ac", "1",
                          "-ar", "48000", "-f", "f32le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.float32)
    return float(np.sqrt((x ** 2).mean())) if len(x) else 0.0


class TranslateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="vs-tr-"))
        cls.cwd = os.getcwd()
        os.chdir(cls.tmp)
        for d in ("raw", "work/tts"):
            Path(d).mkdir(parents=True)
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=8", "-f", "lavfi", "-i",
           "sine=f=300:d=8", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "raw/a.mp4")
        words = [("Hello", 1.0, 1.4), ("there", 1.45, 1.8), ("friends.", 1.85, 2.4),
                 ("This", 3.0, 3.3), ("is", 3.35, 3.5), ("the", 3.55, 3.7), ("plan.", 3.75, 4.5),
                 ("Cut", 6.0, 6.3), ("this.", 6.35, 6.8)]
        Path("work/t.json").write_text(json.dumps({"source": "raw/a.mp4",
                                                   "words": [{"w": w, "s": s, "e": e} for w, s, e in words]}))
        # The edit drops the first second.
        Path("work/edl.json").write_text(json.dumps({"source": "raw/a.mp4", "segments": [{"start": 1.0, "end": 5.0}]}))

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.cwd)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_export_subs_dub(self):
        tr("export", "work/t.json", "work/edl.json", "-o", "work/es.json", "--lang", "es")
        doc = json.loads(Path("work/es.json").read_text())
        self.assertEqual([ln["source"] for ln in doc["lines"]], ["Hello there friends.", "This is the plan."])
        self.assertAlmostEqual(doc["lines"][0]["start"], 0.0, places=2)    # on the EDITED timeline
        self.assertAlmostEqual(doc["lines"][1]["start"], 2.0, places=2)
        self.assertEqual(tr("check", "work/es.json", ok=False).returncode, 1)
        doc["lines"][0]["text"] = "Hola, amigos."
        doc["lines"][1]["text"] = "Este es el plan que tenemos para todos ustedes hoy mismo, de verdad."
        Path("work/es.json").write_text(json.dumps(doc))
        chk = tr("check", "work/es.json")
        self.assertIn("line 2", chk.stdout)                                # too long: warned
        tr("subs", "work/es.json", "-o", "work/cap_es", "--aspect", "9:16")
        srt = Path("work/cap_es.srt").read_text()
        self.assertIn("00:00:00,000 --> ", srt)
        self.assertIn("Hola, amigos.", srt)
        self.assertIn("Dialogue:", Path("work/cap_es.ass").read_text())
        sh(sys.executable, TOOLS / "render.py", "work/edl.json", "-o", "sub.mp4", "--captions", "work/cap_es.ass",
           "--no-loudnorm")
        # Voice clips: line 1 fits, line 2 is far too long.
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=600:d=1.0", "work/tts/1.wav")
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=900:d=4.0", "work/tts/2.wav")
        r = tr("dub", "work/es.json", "--clips", "work/tts", "-o", "work/dub.wav", "--length", "4")
        self.assertIn("line 2", r.stdout)
        self.assertIn("too long", r.stdout)
        self.assertGreater(rms("work/dub.wav", 0.2, 0.5), 0.05)           # line 1 at 0.0-1.0
        self.assertLess(rms("work/dub.wav", 1.2, 0.5), 0.01)              # pause
        self.assertGreater(rms("work/dub.wav", 2.3, 0.5), 0.05)           # line 2 from 2.0
        Path("work/dubbed.json").write_text(json.dumps({"source": "raw/a.mp4", "segments": [{"start": 1.0, "end": 5.0}],
                                                        "audio_track": {"src": "work/dub.wav"}}))
        sh(sys.executable, TOOLS / "render.py", "work/dubbed.json", "-o", "dubbed.mp4", "--no-loudnorm")

    def test_thumbs_rank(self):
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=320x180:r=25:d=4", "-f", "lavfi", "-i",
           "testsrc2=s=320x180:r=25:d=4", "-filter_complex", "[0][1]concat=n=2:v=1:a=0", "-c:v", "libx264",
           "-pix_fmt", "yuv420p", "raw/th.mp4")
        sh(sys.executable, TOOLS / "thumbs.py", "raw/th.mp4", "-o", "work/th", "--n", "4")
        ranked = json.loads(Path("work/th/ranked.json").read_text())
        self.assertGreaterEqual(ranked[0]["t"], 4.0)                       # best is in the picture half
        self.assertTrue(all(r["reject"] for r in ranked if r["t"] < 4.0))  # black frames rejected


if __name__ == "__main__":
    unittest.main()
