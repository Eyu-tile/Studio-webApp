"""The agentic loop: `vs edl` operations with history and ripple, `vs notes`, `vs review`."""
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
from notes import parse_line  # noqa: E402
from vs_common import timeline  # noqa: E402


def sh(*cmd, ok=True):
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if ok and p.returncode:
        raise AssertionError(f"{cmd}\n{p.stdout}\n{p.stderr[-3000:]}")
    return p


def vs(tool, *args, ok=True):
    return sh(sys.executable, TOOLS / f"{tool}.py", *args, ok=ok)


class LoopTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="vs-loop-"))
        cls.cwd = os.getcwd()
        os.chdir(cls.tmp)
        Path("raw").mkdir()
        Path("work").mkdir()
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=20", "-f", "lavfi",
           "-i", "sine=f=440:d=20", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "raw/a.mp4")
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=900:d=0.2", "raw/hit.wav")

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.cwd)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def fresh(self, name):
        edl = {"source": "raw/a.mp4", "segments": [{"start": 0, "end": 2}, {"start": 4, "end": 6}, {"start": 8, "end": 10},
                                                   {"start": 12, "end": 14}],
               "texts": [{"text": "A", "start": 0.5, "end": 1.5}, {"text": "C", "start": 4.5, "end": 5.5},
                         {"text": "D", "start": 6.5, "end": 7.5}],
               "sfx": [{"file": "raw/hit.wav", "at": 4.0}, {"file": "raw/hit.wav", "at": 6.0}]}
        p = Path("work") / f"{name}.json"
        p.write_text(json.dumps(edl))
        hist = Path("work/.history") / name
        shutil.rmtree(hist, ignore_errors=True)
        return p

    def load(self, p):
        return json.loads(Path(p).read_text())

    def test_trim_ripples_and_undo(self):
        p = self.fresh("trim")
        vs("edl", "trim", p, "2", "--end", "-0.5")          # shot 2 now 4-5.5: everything after 4.0 moves 0.5 earlier
        e = self.load(p)
        self.assertEqual(e["segments"][1]["end"], 5.5)
        self.assertEqual([t["start"] for t in e["texts"]], [0.5, 4.0, 6.0])
        self.assertEqual([f["at"] for f in e["sfx"]], [3.5, 5.5])
        vs("edl", "undo", p)
        self.assertEqual(self.load(p)["segments"][1]["end"], 6)
        vs("edl", "redo", p)
        self.assertEqual(self.load(p)["segments"][1]["end"], 5.5)
        hist = vs("edl", "history", p).stdout
        self.assertIn("initial", hist)
        self.assertIn("trim shot 2", hist)

    def test_cut_split_delete_move_insert(self):
        p = self.fresh("ops")
        vs("edl", "cut", p, "3.0", "5.0")                   # removes the end of shot 2 and the start of shot 3
        e = self.load(p)
        self.assertAlmostEqual(timeline(e)[-1]["out_end"], 6.0, places=3)
        # C (4.5-5.5) overlapped the cut [3, 5): its last 0.5 s survives as 3.0-3.5. D (6.5-7.5) moved 2 s earlier.
        self.assertEqual([(t["text"], t["start"], t["end"]) for t in e["texts"]],
                         [("A", 0.5, 1.5), ("C", 3.0, 3.5), ("D", 4.5, 5.5)])
        self.assertEqual([f["at"] for f in e["sfx"]], [4.0])  # the hit at 4.0 was inside the cut
        out = vs("edl", "at", p, "3.5").stdout
        self.assertIn("@ 9.50s", out)
        vs("edl", "split", p, "1", "--at", "1.0")
        self.assertEqual(len(self.load(p)["segments"]), 5)
        vs("edl", "delete", p, "2")
        vs("edl", "move", p, "4", "--to", "1")
        self.assertEqual(self.load(p)["segments"][0]["start"], 12)
        vs("edl", "insert", p, "--before", "1", "--src", "raw/a.mp4", "--start", "16", "--end", "17", "--set", "mute=true")
        e = self.load(p)
        self.assertEqual(e["segments"][0], {"src": "raw/a.mp4", "start": 16.0, "end": 17.0, "mute": True})
        vs("edl", "set", p, "all", "grade=warm")
        vs("edl", "set", p, "--edl", "reframe=0.4")
        e = self.load(p)
        self.assertTrue(all(s["grade"] == "warm" for s in e["segments"]))
        self.assertEqual(e["reframe"], 0.4)
        self.assertIn("total 00:06.000", vs("edl", "show", p).stdout)

    def test_hand_edit_is_recorded_and_lint(self):
        p = self.fresh("hand")
        vs("edl", "trim", p, "1", "--start", "0.2")
        e = self.load(p)
        e["segments"][0]["end"] = 99
        Path(p).write_text(json.dumps(e))
        r = vs("edl", "lint", p, ok=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("ends at 99.00s", r.stdout)
        vs("edl", "undo", p)                                 # records the hand edit, then steps back from it
        self.assertEqual(self.load(p)["segments"][0]["end"], 2)
        self.assertIn("hand edit", vs("edl", "history", p).stdout)

    def test_notes(self):
        self.assertEqual(parse_line("0:12 cut is too early", 30)[0], [(12.0, None)])
        self.assertEqual(parse_line("1:02.5 - 1:04 remove this", 30), ([(62.5, 64.0)], "remove this"))
        self.assertEqual(parse_line("@00:00:31:15 logo too big", 30)[0], [(31.5, None)])
        self.assertEqual(parse_line("[0:45] music too loud", 30), ([(45.0, None)], "music too loud"))
        self.assertEqual(parse_line("0:30–0:35, 0:50 same issue", 30)[0], [(30.0, 35.0), (50.0, None)])
        self.assertEqual(parse_line("12.4s typo", 30)[0], [(12.4, None)])
        self.assertEqual(parse_line("make it punchier overall", 30), ([], "make it punchier overall"))
        p = self.fresh("noted")
        Path("n.txt").write_text("0:05 too long\nmore energy please\n")
        vs("notes", "add", "work/notes.json", "--edl", p, "n.txt", "--by", "client")
        Path("n.csv").write_text("Comment,Timecode,Name\nlogo late,00:00:07:00,Ana\n")
        vs("notes", "add", "work/notes.json", "--edl", p, "n.csv")
        book = json.loads(Path("work/notes.json").read_text())
        self.assertEqual(len(book["notes"]), 3)
        self.assertEqual(book["notes"][0]["where"][0]["shot"], 3)   # output 5.0 -> shot 3 (8-10) at 9.0
        self.assertEqual(book["notes"][0]["where"][0]["src_t"], 9.0)
        self.assertEqual(book["notes"][2]["at"][0][0], 7.0)
        vs("notes", "done", "work/notes.json", "1", "--how", "trimmed")
        self.assertIn("2 open, 1 done", vs("notes", "list", "work/notes.json").stdout)

    def test_review_round(self):
        p = self.fresh("rev")
        r = vs("review", p, "--dir", "work/rv", ok=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        md = Path("work/rv/r01/review.md").read_text()
        self.assertIn("PASS", md)
        for img in ("cuts.png", "overview.png", "texts.png"):
            self.assertTrue(Path("work/rv/r01", img).exists(), img)
        vs("edl", "set", p, "2", "end=50")                  # past the source: lint FAIL, no render
        r = vs("review", p, "--dir", "work/rv", ok=False)
        self.assertEqual(r.returncode, 1)
        md = Path("work/rv/r02/review.md").read_text()
        self.assertIn("ends at 50.00s", md)
        self.assertIn("Changed since round 1", md)


if __name__ == "__main__":
    unittest.main()
