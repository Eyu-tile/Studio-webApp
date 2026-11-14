"""`vs learn`: sources, scan, network sampling into contact sheets, tag, atlas, find, fetch, usage."""
import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "plugins" / "video-studio" / "tools"
sys.path.insert(0, str(TOOLS))
import learn  # noqa: E402


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    """Static files with HTTP Range support, like CDNs and Drive, so ffmpeg can seek without downloading."""

    def send_head(self):
        path = self.translate_path(self.path)
        rng = self.headers.get("Range")
        if not rng or not os.path.isfile(path):
            return super().send_head()
        size = os.path.getsize(path)
        a, b = rng.replace("bytes=", "").split("-")
        start, end = int(a or 0), int(b) if b else size - 1
        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        return f

    def log_message(self, *a):
        pass


def make_clip(path, color, dur=4, size="360x640"):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={color}:s={size}:d={dur}:r=25",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}", "-shortest", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(path)], check=True)


class LearnTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="vs-learn-"))
        cls.media = cls.tmp / "media"
        (cls.media / "sub").mkdir(parents=True)
        make_clip(cls.media / "red.mp4", "red")
        make_clip(cls.media / "sub" / "blue.mp4", "blue", size="640x360")
        shutil.copy(cls.media / "red.mp4", cls.media / "sub" / "red.mp4")  # duplicate (same name and size)
        (cls.media / "notes.txt").write_text("not media")
        handler = functools.partial(RangeHandler, directory=str(cls.media))
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        cls.env = {k: v for k, v in os.environ.items() if k.lower() not in ("http_proxy", "https_proxy")}
        cls.env.update(VS_WORKSPACE=str(cls.tmp / "ws"), VS_LEARN_CACHE=str(cls.tmp / "cache"),
                       VS_KEYS_DIR=str(cls.tmp / "keys"))

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def vs(self, *args, ok=True):
        r = subprocess.run([sys.executable, str(TOOLS / "learn.py"), *args], capture_output=True, text=True,
                           env=self.env, timeout=300)
        if ok and r.returncode:
            raise AssertionError(f"{args}\n{r.stdout}\n{r.stderr}")
        return r

    def res(self, lib):
        return self.tmp / "ws" / "library" / lib / "resources"

    def test_local_folder_full_cycle(self):
        self.vs("source", "Local", str(self.media))
        out = self.vs("scan", "Local").stdout
        self.assertIn("4 files", out)
        inv = json.loads((self.res("Local") / "inventory.json").read_text())
        self.assertEqual(sum(1 for x in inv if x.get("duplicate_of")), 1)
        self.vs("sample", "Local", "--jobs", "2", "--frames", "3")
        sheets = list((self.res("Local") / "sheets").glob("sheet_*.jpg"))
        self.assertEqual(len(sheets), 1)
        nxt = self.vs("next", "Local").stdout
        self.assertIn("blue.mp4", nxt)
        inv = {x["name"] + x.get("folder", ""): x for x in json.loads((self.res("Local") / "inventory.json").read_text())}
        blue = inv["blue.mp4sub"]
        self.assertEqual((blue["res"], blue["orient"], blue["has_audio"]), ("640x360", "horizontal", True))
        tags = self.tmp / "tags.json"
        tags.write_text(json.dumps([{"id": blue["id"], "kind": "test color", "beats": "0-4: solid blue frame",
                                     "best": "0-4", "status": "OK", "use": "blue background"}]))
        self.vs("tag", "Local", str(tags))
        self.vs("atlas", "Local")
        self.assertIn("solid blue frame", (self.res("Local") / "ATLAS.md").read_text())
        self.assertIn(blue["id"], self.vs("find", "Local", "blue background", "--status", "OK", "--unused").stdout)
        self.vs("use", "Local", blue["id"], "--project", "TC0001")
        self.assertIn("no matches", self.vs("find", "Local", "blue", "--unused").stdout)
        got = self.vs("fetch", "Local", blue["id"], "-o", str(self.tmp / "got"), "--section", "1-3").stdout.strip()
        self.assertTrue(Path(got).exists())

    def test_http_links_sampled_without_download(self):
        lst = self.tmp / "links.txt"
        lst.write_text(f"{self.base}/red.mp4\n{self.base}/sub/blue.mp4\n")
        self.vs("source", "Net", str(lst), "--provider", "direct")
        self.assertIn("2 files", self.vs("scan", "Net").stdout)
        self.vs("sample", "Net", "--jobs", "2", "--frames", "4")
        inv = json.loads((self.res("Net") / "inventory.json").read_text())
        self.assertTrue(all(x.get("sampled") and x.get("duration") for x in inv), inv)
        self.assertEqual(len(list((self.tmp / "cache" / "Net" / "frames").glob("*/*.jpg"))), 8)

    def test_detect_and_parsers(self):
        self.assertEqual(learn.detect("https://drive.google.com/drive/folders/abc123"), "gdrive")
        self.assertEqual(learn.detect("https://next.frame.io/share/x/y"), "frameio")
        self.assertEqual(learn.detect("https://f.io/AbCd"), "frameio")
        self.assertEqual(learn.detect("https://www.dropbox.com/scl/fo/x/y?dl=0"), "dropbox")
        self.assertEqual(learn.detect("https://1drv.ms/f/s!abc"), "onedrive")
        self.assertEqual(learn.detect("https://cdn.example.com/a/clip.mov?sig=1"), "direct")
        self.assertEqual(learn.detect("https://some-dam.example.com/share/123"), "web")
        page = ('<div class="flip-entry" id="entry-F1"><a href="https://drive.google.com/drive/folders/F1">'
                '<div class="flip-entry-title">Shoot day 1</div></a></div>'
                '<div class="flip-entry" id="entry-V9"><a href="https://drive.google.com/file/d/V9/view">'
                '<div class="flip-entry-title">clip &amp; b-roll.mp4</div></a></div>')
        self.assertEqual(learn.parse_gdrive_embedded(page),
                         [("F1", "Shoot day 1", True), ("V9", "clip & b-roll.mp4", False)])
        self.assertEqual(learn.od_token("https://1drv.ms/f/s!abc"), "u!aHR0cHM6Ly8xZHJ2Lm1zL2YvcyFhYmM")
        self.assertIn("confirm=t", learn.resolve_gdrive({"pid": "V9"}, "NoKeyLib"))


if __name__ == "__main__":
    unittest.main()
