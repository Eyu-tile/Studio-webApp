"""Learning from feedback (`vs lessons`): lessons per brand, the brief, repeats flagged when notes come in, repeated
feedback offered as a lesson, and lesson checks failing QA before the client sees the same mistake again.

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
VS = ROOT / "plugins" / "video-studio" / "bin" / "vs"
sys.path.insert(0, str(ROOT / "plugins" / "video-studio" / "tools"))
import lessons  # noqa: E402


class LessonsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vs-lessons-"))
        self.ws = self.tmp / "video-studio"
        (self.ws / "style").mkdir(parents=True)
        self.env = {**os.environ, "VS_WORKSPACE": str(self.ws)}
        self.env.pop("VS_BRAND", None)
        os.environ["VS_WORKSPACE"] = str(self.ws)

    def tearDown(self):
        os.environ.pop("VS_WORKSPACE", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def vs(self, *args, ok=True):
        p = subprocess.run([str(VS), *map(str, args)], capture_output=True, text=True, env=self.env, cwd=self.tmp)
        if ok and p.returncode != 0:
            raise AssertionError(f"{args}\n{p.stdout}\n{p.stderr}")
        return p

    def project(self, name, client):
        (self.ws / "history").mkdir(exist_ok=True)
        (self.ws / "history" / f"{name.upper()}.json").write_text(json.dumps({"code": name.upper(),
                                                                                "project": name, "client": client}))
        w = self.ws / "projects" / name / "work"
        w.mkdir(parents=True)
        edl = {"segments": [{"src": "a.mp4", "start": 0, "end": 4}, {"src": "b_oldlogo.mp4", "start": 0, "end": 1.2}],
               "music": {"file": "bed.mp3", "gain_db": -14},
               "texts": [{"text": "Basically the best", "start": 0, "end": 2, "size": 0.04}]}
        (w / "edl.json").write_text(json.dumps(edl))
        return w

    def test_matching_and_categories(self):
        les = {"id": "L1", "rule": "Keep the music bed at -22 dB or lower under speech", "category": "music"}
        self.assertEqual(lessons.category_of("music is too loud over the voice"), "music")
        self.assertIsNotNone(lessons.match("the music is too loud again", [les]))
        self.assertIsNone(lessons.match("typo in the end card", [les]))

    def test_brief_add_and_dedupe_per_brand(self):
        self.vs("lessons", "add", "--brand", "TrueClean", "--rule", "Keep the music bed at -22 dB or lower",
                "--check", "music_gain_max=-22", "--must", "--told")
        self.vs("lessons", "add", "--brand", "Acme", "--rule", "Hook text in the first second", "--when", "reels")
        self.vs("lessons", "add", "--global", "--rule", "Never use wipe transitions",
                "--check", "banned_transitions=wipe")
        out = self.vs("lessons", "add", "--brand", "trueclean", "--rule", "music bed at -22 dB or lower").stdout
        self.assertIn("already a lesson", out)                                   # same rule, any case of the brand
        b = self.vs("lessons", "brief", "--brand", "TrueClean").stdout
        self.assertIn("[L1] Keep the music bed", b)
        self.assertIn("MUST", b)
        self.assertIn("[house:L1] Never use wipe", b)                            # house rules apply to every brand
        self.assertNotIn("Hook text", b)                                         # other brands' lessons stay out
        self.assertTrue((self.ws / "library" / "TrueClean" / "LESSONS.md").exists())
        self.assertIn("Hook text", self.vs("lessons", "brief", "--brand", "Acme", "--kind", "reels").stdout)
        self.assertNotIn("Hook text", self.vs("lessons", "brief", "--brand", "Acme", "--kind", "youtube").stdout)

    def test_repeat_is_flagged_when_notes_come_in(self):
        w = self.project("tc1", "TrueClean")
        self.vs("lessons", "add", "--brand", "TrueClean", "--rule", "Keep the music bed at -22 dB or lower under speech")
        out = self.vs("notes", "add", w / "notes.json", "--edl", w / "edl.json",
                      "--text", "0:02 music way too loud again", "--text", "0:04 typo in title").stdout
        self.assertIn("REPEAT: note #1", out)                                   # brand found from the project's task
        self.assertNotIn("note #2", out.split("REPEAT")[-1])
        book = json.loads((self.ws / "library" / "TrueClean" / "lessons.json").read_text())
        self.assertEqual(book["lessons"][0]["repeats"], 1)
        self.assertEqual(json.loads((w / "notes.json").read_text())["notes"][0]["lesson"], "L1")

    def test_learn_offers_unclassified_notes_and_cross_project_repeats(self):
        for name in ("tc1", "tc2"):
            w = self.project(name, "TrueClean")
            self.vs("notes", "add", w / "notes.json", "--edl", w / "edl.json",
                    "--text", "0:01 captions are too small to read", "--text", "0:03 swap this shot")
        w = self.ws / "projects" / "tc2" / "work"
        self.vs("notes", "done", w / "notes.json", 1, 2, "--how", "bigger captions")
        out = self.vs("lessons", "learn", "--brand", "TrueClean", "--notes", w / "notes.json").stdout
        self.assertIn("#1 [captions] captions are too small", out)
        self.assertIn("2x in tc1, tc2", out)                                    # came back in another project
        self.vs("lessons", "add", "--brand", "TrueClean", "--rule", "Captions at least 7 % of the height",
                "--from", f"{w / 'notes.json'}:1")
        self.vs("lessons", "none", w / "notes.json", 2)
        out = self.vs("lessons", "learn", "--brand", "TrueClean", "--notes", w / "notes.json").stdout
        self.assertIn("(0)", out)

    def test_checks_fail_qa_before_delivery(self):
        w = self.project("tc1", "TrueClean")
        self.vs("lessons", "add", "--brand", "TrueClean", "--rule", "Music at -22 dB or lower",
                "--check", "music_gain_max=-22", "--must")
        self.vs("lessons", "add", "--brand", "TrueClean", "--rule", "Never show the old logo clip",
                "--check", "banned_sources=oldlogo", "--must")
        self.vs("lessons", "add", "--brand", "TrueClean", "--rule", "No filler words on screen",
                "--check", "banned_words=basically,literally")
        self.vs("lessons", "add", "--brand", "TrueClean", "--rule", "Text at least 6 % of the height",
                "--check", "text_size_min=0.06")
        p = self.vs("lessons", "check", w / "edl.json", "--brand", "TrueClean", ok=False)
        self.assertEqual(p.returncode, 1)
        self.assertIn("FAIL lesson L1", p.stdout)
        self.assertIn("music at -14 dB", p.stdout)
        self.assertIn("FAIL lesson L2", p.stdout)
        self.assertIn("WARN lesson L3", p.stdout)                               # not a must: a warning
        self.assertIn("WARN lesson L4", p.stdout)
        edl = json.loads((w / "edl.json").read_text())
        edl["music"]["gain_db"] = -24
        edl["segments"][1]["src"] = "b.mp4"
        edl["texts"][0].update(text="The best", size=0.07)
        (w / "edl.json").write_text(json.dumps(edl))
        p = self.vs("lessons", "check", w / "edl.json", "--project", "tc1")    # brand from the project
        self.assertNotIn("FAIL", p.stdout)
        self.assertNotIn("WARN", p.stdout)
        book = json.loads((self.ws / "library" / "TrueClean" / "lessons.json").read_text())
        self.assertEqual(book["lessons"][0]["caught"], 1)                       # caught before the client saw it

    def test_retire_and_edit(self):
        self.vs("lessons", "add", "--brand", "TrueClean", "--rule", "Warm grade on every video")
        self.vs("lessons", "edit", "--brand", "TrueClean", "L1", "--check", "banned_grades=cool", "--must")
        self.assertIn("checked", self.vs("lessons", "brief", "--brand", "TrueClean").stdout)
        self.vs("lessons", "retire", "--brand", "TrueClean", "L1", "--why", "new brand book")
        self.assertIn("no lessons yet", self.vs("lessons", "brief", "--brand", "TrueClean").stdout)
        self.assertIn("RETIRED", self.vs("lessons", "list", "--brand", "TrueClean", "--all").stdout)


if __name__ == "__main__":
    unittest.main()
