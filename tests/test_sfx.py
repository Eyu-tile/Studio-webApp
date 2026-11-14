"""Tests for `vs sfx`: sounds are measured, their hit lands on the frame, levels are normalised, tails and
build-ups are capped, risers fit the room before a reveal, speech lowers cues (needs ffmpeg + numpy).

Run: python3 -m unittest discover -s tests -v
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "video-studio"
TOOLS = PLUGIN / "tools"
sys.path.insert(0, str(TOOLS))
import numpy as np  # noqa: E402
from vs_common import sfx_chain  # noqa: E402

SR = 48000


def sh(*cmd, ok=True, env=None):
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, env=env)
    if ok and p.returncode != 0:
        raise AssertionError(f"{' '.join(map(str, cmd))}\n{p.stdout}\n{p.stderr[-3000:]}")
    return p


def write_wav(path, x):
    """Mono float -> 16-bit WAV through ffmpeg."""
    raw = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", "-", str(path)],
                   input=raw, check=True)


def read_mono(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, "<i2").astype(float) / 32768


def burst(dur, at, length, amp, rise=0.0):
    """Noise that is silent until `at`, optionally ramps up over `rise` s, holds `length` s, then stops."""
    t = np.arange(int(dur * SR)) / SR
    env = np.where((t >= at) & (t < at + length), 1.0, 0.0)
    if rise:  # quadratic build: -20 dB at about 30 % of the way in, full level at `at`
        env = np.maximum(env, np.where((t >= at - rise) & (t < at), ((t - (at - rise)) / rise) ** 2, 0.0))
    rng = np.random.default_rng(1)
    return rng.uniform(-1, 1, len(t)) * env * amp


class SfxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="vs-sfx-"))
        cls.cwd = os.getcwd()
        os.chdir(cls.tmp)
        lib = Path("lib")
        lib.mkdir()
        # impact: 0.2 s of silence, then a loud 0.3 s hit. pop: quiet (-30 dB) click at 0.1 s.
        write_wav(lib / "impact_test.wav", burst(1.5, 0.2, 0.3, 0.9))
        write_wav(lib / "pop_test.wav", burst(0.6, 0.1, 0.05, 0.03))
        # whoosh: quadratic build over 1.5 s to full level at 1.6 s, holds 0.4 s, file is 3 s long. Its loud part
        # (within 3 dB of the loudest) arrives at 1.6 - 1.5 * (1 - sqrt(0.708)) = 1.36 s.
        write_wav(lib / "whoosh_test.wav", burst(3.0, 1.6, 0.4, 0.5, rise=1.5))
        # riser: builds 0..3 s, crest at 3 s, then 5 s of silence (like the bundled riser).
        write_wav(lib / "riser_test.wav", burst(8.0, 3.0, 0.3, 0.6, rise=3.0))
        for name, src in (("a", "testsrc2"), ("b", "smptebars")):
            sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"{src}=s=320x180:r=25:d=6", "-f", "lavfi",
               "-i", "sine=f=220:d=6", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", f"{name}.mp4")
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=red:s=100x50:d=1", "-frames:v", "1", "logo.png")
        cls.edl = {"segments": [{"src": str(cls.tmp / "a.mp4"), "start": 0, "end": 4},
                                {"src": str(cls.tmp / "b.mp4"), "start": 0, "end": 4,
                                 "transition_in": {"type": "whip-left", "duration": 0.3}}],
                   "texts": [{"text": "BIG", "start": 1.2, "end": 2, "pos": "center"},
                             {"text": "small", "start": 5.0, "end": 6}],
                   "overlays": [{"file": str(cls.tmp / "logo.png"), "start": 7.3, "end": 7.6}]}
        Path("edl.json").write_text(json.dumps(cls.edl))
        Path("words.json").write_text(json.dumps({"words": [{"w": "hi", "s": 4.9, "e": 5.3}]}))
        cls.env = dict(os.environ, VS_WORKSPACE=str(cls.tmp / "ws"), XDG_CACHE_HOME=str(cls.tmp / "cache"))

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.cwd)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def vs(self, *args):
        return sh(PLUGIN / "bin" / "vs", *args, env=self.env)

    def plan(self, *extra, name="plan.json"):
        self.vs("sfx", "plan", "--edl", "edl.json", "--library", "lib", "-o", name, *extra)
        return json.loads(Path(name).read_text())["plan"]

    def by_cue(self, plan, cue):
        return [p for p in plan if p["cue"] == cue]

    # ---------------------------------------------------------------------------------------
    def test_analyse_measures_onset_and_arrival(self):
        out = self.vs("sfx", "analyse", "lib").stdout
        rows = {line.split()[0]: line.split() for line in out.splitlines()[1:]}
        self.assertAlmostEqual(float(rows["impact_test.wav"][3]), 0.2, delta=0.03)   # onset
        self.assertAlmostEqual(float(rows["whoosh_test.wav"][4]), 1.36, delta=0.06)  # loud part arrives (hit)
        self.assertAlmostEqual(float(rows["whoosh_test.wav"][5]), 1.8, delta=0.25)   # loudest (crest), in the hold
        self.assertAlmostEqual(float(rows["riser_test.wav"][5]), 3.1, delta=0.2)     # crest, not file end

    def test_hits_land_on_frame(self):
        plan = self.plan()
        big = self.by_cue(plan, "text-big")[0]
        self.assertTrue(big["file"].endswith("impact_test.wav"))
        self.assertAlmostEqual(big["at"], 1.2 - 0.2, delta=0.03)     # silence pad absorbed: the hit is on 1.2 s
        whip = self.by_cue(plan, "transition-fast")[0]
        self.assertTrue(whip["file"].endswith("whoosh_test.wav"))
        # crest on the frame; build-up capped at --max-head 0.8 s before it, faded in
        crest = float(next(ln.split()[5] for ln in self.vs("sfx", "analyse", "lib/whoosh_test.wav").stdout.splitlines()[1:]))
        self.assertAlmostEqual(whip["in"], crest - 0.8, delta=0.02)
        self.assertAlmostEqual(whip["at"] + (crest - whip["in"]), whip["frame_t"], delta=0.02)
        self.assertIn("fade_in", whip)
        self.assertEqual(whip["pan"], -0.4)                          # whip-left sounds on the left

    def test_levels_are_normalised(self):
        plan = self.plan()
        pop, big = self.by_cue(plan, "text")[0], self.by_cue(plan, "text-big")[0]
        # the quiet pop is lifted, the loud impact lowered; each ends near REF -12 dB + its level
        self.assertGreater(pop["norm_db"], 10)
        self.assertLess(big["norm_db"], 0)
        self.assertEqual(pop["level_db"], -12)

    def test_tail_fades_before_next_hit(self):
        plan = self.plan("--min-gap", "0.1")
        hits = sorted((p for p in plan if p["file"] and p["cue"] != "riser"), key=lambda p: p["frame_t"])
        for cur, nxt in zip(hits, hits[1:]):
            length = len(read_mono(cur["file"])) / SR - cur.get("in", 0)
            end = cur["at"] + (cur.get("dur") or length)
            self.assertLessEqual(end, nxt["frame_t"] + 0.06, f"{cur['cue']} rings into {nxt['cue']}")

    def test_riser_crests_on_reveal(self):
        plan = self.plan("--style", "launch")
        r = [p for p in plan if p["cue"] == "riser" and abs(p["frame_t"] - 7.3) < 0.01]
        self.assertEqual(len(r), 1, plan)
        r = r[0]
        build = r["frame_t"] - r["at"]
        self.assertGreaterEqual(build, 1.0)
        self.assertAlmostEqual(r["in"] + build, 3.1, delta=0.2)      # file crest (~3.1 s) lands on 7.3 s
        self.assertLess(r["dur"], build + 0.3)                       # silent 5 s tail cut off

    def test_speech_lowers_or_drops_cues(self):
        plan = self.plan("--words", "words.json")
        small = self.by_cue(plan, "text")[0]
        self.assertTrue(small.get("over_speech"))
        self.assertEqual(small["level_db"], -12 - 6)
        th = self.plan("--style", "talking-head", "--words", "words.json", name="th.json")
        self.assertLessEqual(len(th), 3)                             # sparse: one cue per ~5 s

    def test_apply_and_render_place_the_sound(self):
        plan = self.plan(name="p.json")
        self.vs("render", "edl.json", "-o", "draft.mp4")
        self.vs("sfx", "apply", "draft.mp4", "--plan", "p.json", "-o", "draft_sfx.mp4", "--stem", "stem.wav")
        x = read_mono("stem.wav")
        big = self.by_cue(plan, "text-big")[0]
        # loudest sample within the first 0.5 s after the title frame, and silence just before it
        i = int(big["frame_t"] * SR)
        self.assertGreater(np.abs(x[i:i + SR // 4]).max(), 0.05)
        self.assertLess(np.abs(x[i - SR // 10:i - SR // 50]).max(), 0.02)
        self.vs("sfx", "merge", "edl.json", "--plan", "p.json", "-o", "edl.sfx.json")
        merged = json.loads(Path("edl.sfx.json").read_text())["sfx"]
        self.assertTrue(any("in" in s for s in merged) and any("dur" in s for s in merged))
        self.vs("render", "edl.sfx.json", "-o", "rendered.mp4")

    def test_sfx_chain(self):
        c = sfx_chain({"file": "x", "at": 1.5, "in": 0.4, "dur": 1.0, "fade_in": 0.1, "fade_out": 0.2,
                       "pan": -0.5, "gain_db": -9})
        self.assertIn("atrim=start=0.400:duration=1.000", c)
        self.assertIn("afade=t=out:st=0.800:d=0.200", c)
        self.assertIn("c0=1.000*c0|c1=0.500*c1", c)
        self.assertTrue(c.endswith("volume=-9.0dB,adelay=1500:all=1"))
        self.assertEqual(sfx_chain({"at": 0, "gain_db": -6}),
                         "aresample=48000,aformat=channel_layouts=stereo,volume=-6.0dB,adelay=0:all=1")


if __name__ == "__main__":
    unittest.main()
