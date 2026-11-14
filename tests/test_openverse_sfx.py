"""Openverse sound search: no broken category filter for sfx, and --cc0 asks for CC0/public domain only."""
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "plugins" / "video-studio" / "tools"
SEEN = []


class FakeOpenverse(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        SEEN.append(q)
        res = [{"id": "a1", "title": "Door slam cc0", "license": "cc0", "license_version": "1.0", "duration": 1200,
                "url": "http://x/a1.wav", "creator": "u1", "foreign_landing_url": "http://x/a1"},
               {"id": "b2", "title": "Door slam by", "license": "by", "license_version": "4.0", "duration": 900,
                "url": "http://x/b2.wav", "creator": "u2", "foreign_landing_url": "http://x/b2"}]
        if q.get("license") == ["cc0,pdm"]:
            res = res[:1]
        body = json.dumps({"result_count": len(res), "results": res}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class OpenverseSfxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenverse)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.tmp = Path(tempfile.mkdtemp(prefix="vs-ov-"))
        cls.env = {k: v for k, v in os.environ.items() if k.lower() not in ("http_proxy", "https_proxy")}
        cls.env.update(VS_WORKSPACE=str(cls.tmp / "ws"), VS_OPENVERSE_BASE=f"http://127.0.0.1:{cls.srv.server_address[1]}",
                       NO_PROXY="127.0.0.1", no_proxy="127.0.0.1")

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def search(self, *extra):
        SEEN.clear()
        out = self.tmp / "r"
        p = subprocess.run([sys.executable, str(TOOLS / "assets.py"), "search", "door slam", "--type", "sfx",
                            "--provider", "openverse", "--library", "-o", str(out), *extra],
                           capture_output=True, text=True, env=self.env, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        d = json.loads(out.with_suffix(".json").read_text())
        return SEEN[-1], d.get("results", d)

    def test_sfx_has_no_category_filter(self):
        q, res = self.search()
        self.assertNotIn("category", q)  # category=sound_effect matches nothing on Openverse now
        self.assertEqual(q.get("length"), ["short"])
        self.assertEqual(q.get("license_type"), ["commercial,modification"])
        self.assertEqual(len(res), 2)

    def test_cc0_only(self):
        q, res = self.search("--cc0")
        self.assertEqual(q.get("license"), ["cc0,pdm"])
        self.assertNotIn("license_type", q)
        self.assertEqual([r["license"] for r in res], ["CC0 / public domain"])


if __name__ == "__main__":
    unittest.main()
