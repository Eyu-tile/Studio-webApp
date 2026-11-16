"""Offline tests for the Internet Archive module (tools/archive.py): licence table, brief parsing, query
building, ranking, two-stage search, file grouping, scene normalising and verified cuts (needs ffmpeg).
Fixtures: archive.org metadata captured by broll-mcp (MIT), see tests/fixtures/archive/README.md.

Run: python3 -m unittest discover -s tests -v
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins" / "video-studio" / "tools"))
import archive as ia  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "archive"


class LicenceTest(unittest.TestCase):
    def test_table(self):
        pd = ia.license_info("http://creativecommons.org/licenses/publicdomain/")
        self.assertEqual((pd["label"], pd["commercial_use"], pd["attribution_required"]),
                         ("Public domain (CC PD dedication)", "allowed", "no"))
        self.assertEqual(ia.license_info("https://creativecommons.org/publicdomain/zero/1.0/")["label"], "CC0 1.0")
        nc = ia.license_info("http://creativecommons.org/licenses/by-nc/3.0/")
        self.assertEqual((nc["label"], nc["commercial_use"]), ("CC BY-NC 3.0", "not_allowed"))
        self.assertEqual(ia.license_info("https://creativecommons.org/licenses/by/4.0")["attribution_required"], "yes")

    def test_nothing_guessed(self):
        odd = ia.license_info("http://example.com/my-licence")
        self.assertEqual((odd["label"], odd["commercial_use"]), ("unrecognized", "unknown"))
        none = ia.license_info(None, "Copyright 1950 Some Studio")
        self.assertEqual((none["label"], none["commercial_use"]), ("unknown (rights statement only)", "unknown"))


class QueryTest(unittest.TestCase):
    def test_brief_terms(self):
        terms, decade, bw = ia.brief_terms("8 seconds of children eating bananas, black and white 1950s cinematic footage")
        self.assertEqual(terms, ["children", "eating", "bananas"])
        self.assertEqual(decade, 1950)
        self.assertTrue(bw)

    def test_query_escapes_licence_slashes(self):
        q = ia.build_query(["bananas"], "movies", True)
        self.assertIn(r"*\/by\/*", q)
        self.assertNotIn("*licenses/by/*", q)  # unescaped: archive.org answers BACKEND_ERROR
        self.assertIn('format:"h.264"', q)
        strict = ia.build_query(["children", "bananas"], "movies", True, decade=1950, color="bw")
        self.assertIn("(title:children OR subject:children OR description:children OR shotlist:children) AND", strict)
        self.assertIn("year:[1950 TO 1959]", strict)
        self.assertIn("color:(black", strict)
        loose = ia.build_query(["children", "bananas"], "audio", False, licence="stated")
        self.assertIn("title:(children OR bananas)", loose)
        self.assertNotIn("format:", loose)

    def test_score(self):
        doc = {"title": "About Bananas", "subject": ["children"], "downloads": 10000, "format": ["h.264"], "color": "B&W"}
        s, why = ia.score(doc, ["bananas", "children", "eating"], 1, True, True)
        # title 3 + subject 2 + description 1 + tier 3 + log10(10000)/2 = 2 + h.264 1 + b&w 2
        self.assertEqual(s, 14)
        self.assertEqual(why[:2], ["title 'bananas'", "subject 'children'"])


class SearchTest(unittest.TestCase):
    def setUp(self):
        ia._last[0] = 0
        ia.time.sleep = lambda s: None  # no politeness pause in tests

    def fake(self, strict_docs, any_docs, tier1=()):
        calls = []

        def http_json(url, params=None):
            q = params["q"]
            calls.append(q)
            if q.startswith("identifier:("):
                return {"response": {"docs": [{"identifier": i} for i in tier1 if f'"{i}"' in q and "prelinger" in q]}}
            docs = any_docs if "title:(" in q else strict_docs  # only the any-term query groups terms as title:(a OR b)
            return {"response": {"numFound": len(docs), "docs": docs}}
        return http_json, calls

    def test_two_stage_and_tiers(self):
        strict = [{"identifier": "a", "title": "bananas", "downloads": 10}]
        loose = [{"identifier": "a", "title": "bananas"}, {"identifier": "b", "title": "bananas boat", "downloads": 9e6},
                 {"identifier": "c", "title": "fruit"}]
        http_json, calls = self.fake(strict, loose, tier1=("c",))
        docs = ia.search("bananas", "movies", 3, http_json)
        self.assertEqual([d["identifier"] for d in docs][0], "a")          # all-terms hits rank first
        self.assertEqual(len(docs), 3)                                     # fewer than n strict -> any-term stage ran
        self.assertEqual(sum(1 for c in calls if not c.startswith("identifier:(")), 2)
        self.assertEqual(next(d for d in docs if d["identifier"] == "c")["_tier"], 1)

    def test_backend_error_is_an_error(self):
        with self.assertRaises(RuntimeError):
            ia.search("bananas", "movies", 3, lambda url, params=None: {"error": "[BACKEND_ERROR]"})

    def test_no_searchable_words(self):
        with self.assertRaises(RuntimeError):
            ia.search("cinematic b-roll footage", "movies", 3, lambda url, params=None: {})


class FilesTest(unittest.TestCase):
    def test_single_film(self):
        files = json.loads((FIX / "AboutBan1935.json").read_text())["files"]
        groups = ia.video_groups(files)
        self.assertEqual(len(groups), 1)
        g = groups[0]
        self.assertEqual(g["best"]["name"], "AboutBan1935.mp4")
        self.assertEqual(g["best"]["format"], "h.264")
        self.assertEqual(g["scan"]["format"], "512Kb MPEG4")             # cheap file for scanning
        self.assertEqual(g["best"]["md5"], "de484b1b573d28be4860f00a593f4416")

    def test_multi_clip_renditions_merge(self):
        files = json.loads((FIX / "ace_200911_03.trimmed.json").read_text())["files"]
        groups = ia.video_groups(files)
        self.assertEqual(len(groups), 6)                                  # 12 h.264 encodes = 6 shots
        self.assertTrue(all(g["best"]["height"] == 360 for g in groups))  # the larger encode wins
        self.assertTrue(ia.thumbs_for("ace_200911_03", files, groups[0]))

    def test_pick_named_file(self):
        files = json.loads((FIX / "AboutBan1935.json").read_text())["files"]
        it = {"identifier": "AboutBan1935", "groups": ia.video_groups(files)}
        self.assertEqual(ia.pick_file(it, "AboutBan1935_512kb.mp4")[1]["format"], "512Kb MPEG4")
        with self.assertRaises(RuntimeError):
            ia.pick_file(it, "nope.mp4")


class ScenesTest(unittest.TestCase):
    def test_normalize(self):
        sc = ia.normalize_scenes([2.0, 2.5, 8.0], 0.0, 40.0)
        # 2.0-2.5 is < 1.5 s: merged; 8.0-40.0 is 32 s: split every 10 s
        self.assertEqual([(s["start"], s["end"]) for s in sc],
                         [(0.0, 2.5), (2.5, 8.0), (8.0, 18.0), (18.0, 28.0), (28.0, 38.0), (38.0, 40.0)])
        self.assertEqual([s["synthetic"] for s in sc], [False, False, True, True, True, True])
        self.assertTrue(all(s["synthetic"] for s in ia.normalize_scenes([], 0.0, 15.0)))
        self.assertEqual(len(ia.normalize_scenes([], 0.0, 5000.0)), ia.MAX_SCENES)


class CutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="vs-ia-"))
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=20", "-f", "lavfi",
                        "-i", "sine=d=20", "-c:v", "libx264", "-g", "250", "-c:a", "aac", "-shortest",
                        str(cls.tmp / "src.mp4")], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_frame_accurate_and_verified(self):
        # keyframes every 10 s: a stream copy from 3 s would snap; the re-encode must be 8.0 s
        out = self.tmp / "c.mp4"
        r = ia.cut(str(self.tmp / "src.mp4"), 3.0, 8.0, out, "test", source_length=20.0)
        self.assertAlmostEqual(r["duration"], 8.0, delta=ia.TOLERANCE)
        self.assertEqual(r["decode_errors"], 0)
        self.assertTrue(r["has_audio"])
        self.assertFalse(list(self.tmp.glob("*.part*")))

    def test_clamped_to_source_end(self):
        r = ia.cut(str(self.tmp / "src.mp4"), 16.0, 8.0, self.tmp / "end.mp4", "test", audio=False, source_length=20.0)
        self.assertAlmostEqual(r["asked"], 4.0)
        self.assertFalse(r["has_audio"])

    def test_provenance(self):
        out = self.tmp / "p.mp4"
        r = ia.cut(str(self.tmp / "src.mp4"), 1.0, 2.0, out, "test", source_length=20.0)
        it = {"identifier": "AboutBan1935", "title": "About Bananas", "date": "1935", "creator": "Castle Films",
              "collections": ["prelinger"], "tier": 1, "server": "dn1", "page_url": "https://archive.org/details/AboutBan1935",
              "license": ia.license_info("http://creativecommons.org/licenses/publicdomain/")}
        f = {"name": "AboutBan1935.mp4", "md5": "de48", "format": "h.264"}
        p = ia.provenance(it, f, 1.0, 2.0, out, "test", r)
        self.assertEqual(p["attribution_text"], "\"About Bananas\" (1935), Prelinger Archives via Internet Archive, "
                         "https://archive.org/details/AboutBan1935. License: Public domain (CC PD dedication).")
        self.assertEqual(p["segment"]["start_s"], 1.0)
        self.assertEqual(len(p["clip_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
