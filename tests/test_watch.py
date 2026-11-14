"""`vs watch` on a local file, a direct link (local HTTP server) and the Instagram embed parser (fixture)."""
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
import watch  # noqa: E402


def sh(*cmd):
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if p.returncode:
        raise AssertionError(f"{cmd}\n{p.stdout}\n{p.stderr[-3000:]}")
    return p


class WatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="vs-watch-"))
        cls.cwd = os.getcwd()
        os.chdir(cls.tmp)
        Path("srv").mkdir()
        sh("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x568:r=25:d=6", "-f", "lavfi", "-i",
           "sine=f=300:d=6", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "srv/clip.mp4")
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(cls.tmp / "srv"))
        handler.log_message = lambda *a: None
        cls.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        os.chdir(cls.cwd)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def check_out(self, out, frames=1):
        md = Path(out, "watch.md").read_text()
        self.assertIn("## How it's cut", md)
        self.assertGreaterEqual(len(list(Path(out).glob("frames_*.png"))), frames)
        self.assertTrue(Path(out, "meta.json").exists())
        return md

    def test_local_file(self):
        sh(sys.executable, TOOLS / "watch.py", "srv/clip.mp4", "-o", "w_local", "--no-transcript")
        md = self.check_out("w_local")
        self.assertIn("No transcript (skipped)", md)

    def test_direct_link(self):
        sh(sys.executable, TOOLS / "watch.py", f"{self.base}/clip.mp4", "-o", "w_link", "--no-transcript")
        self.check_out("w_link")
        self.assertEqual(json.loads(Path("w_link/meta.json").read_text())["source"], "direct link")

    def test_instagram_embed_parser(self):
        # An embed page as Instagram serves it: escaped JSON inside the HTML.
        page = ('<div class="UsernameText">someone</div><div class="Caption">3 tips &amp; tricks '
                '<a>#ad</a></div><script>{\\"video_url\\":\\"' + self.base.replace("/", "\\\\\\/") +
                '\\\\\\/clip.mp4?a=1\\\\u0026b=2\\",\\"x\\":1}</script>')
        Path("srv/embed.html").write_text(page)
        orig = watch.http_get

        def fake(url, dest=None, timeout=60):
            if "/embed/captioned/" in url:
                return page
            return orig(url.replace("?a=1&b=2", ""), dest, timeout)
        watch.http_get = fake
        try:
            f, meta = watch.instagram_embed("https://www.instagram.com/reel/ABC123/", self.tmp)
        finally:
            watch.http_get = orig
        self.assertEqual(meta["uploader"], "someone")
        self.assertEqual(meta["description"], "3 tips & tricks #ad")
        self.assertTrue(f and Path(f).stat().st_size > 1000)


if __name__ == "__main__":
    unittest.main()
