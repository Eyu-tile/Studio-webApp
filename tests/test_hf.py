"""`vs hf`: Higgsfield accounts per project (team workspaces and separate logins)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "plugins" / "video-studio" / "tools"
WS = "eb85946c-1a48-4b0a-9434-52b7a20e1f9f"


class HiggsfieldAccountsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vs-hf-"))
        self.log = self.tmp / "claude_calls.txt"
        fake = self.tmp / "fake_claude.py"
        fake.write_text(f"import sys\nopen({str(self.log)!r},'a').write(' '.join(sys.argv[1:])+'\\n')\n")
        self.env = {**os.environ, "VS_KEYS_DIR": str(self.tmp / "cfg"),
                    "VS_CLAUDE_CMD": f"{sys.executable} {fake}"}

    def hf(self, *args, ok=True, cwd=None):
        p = subprocess.run([sys.executable, str(TOOLS / "hf.py"), *args], capture_output=True, text=True,
                           env=self.env, cwd=cwd or self.tmp)
        if ok and p.returncode:
            raise AssertionError(f"{args}\n{p.stdout}\n{p.stderr}")
        return p

    def current(self, project):
        return json.loads(self.hf("current", "--project", project, "--json", ok=False).stdout)

    def test_workspace_account_and_switch(self):
        self.hf("add", "acme", "--workspace", WS, "--label", "Acme Inc")
        self.hf("add", "zeta", "--login", "--label", "Zeta")
        self.hf("use", "acme", "--project", "acme-spring")
        self.hf("use", "zeta", "--project", "zeta-launch")
        a = self.current("acme-spring")
        self.assertEqual((a["account"], a["kind"], a["workspace_id"]), ("acme", "workspace", WS))
        self.assertIn("select_workspace", a["how_to_select"])
        z = self.current("zeta-launch")
        self.assertEqual((z["account"], z["kind"], z["server"]), ("zeta", "login", "higgsfield-zeta"))
        self.assertIn("mcp__higgsfield-zeta__", z["how_to_select"])
        # switch a project to another account
        self.hf("use", "zeta", "--project", "acme-spring")
        self.assertEqual(self.current("acme-spring")["account"], "zeta")

    def test_login_registers_named_mcp_server(self):
        self.hf("add", "zeta", "--login")
        call = self.log.read_text().strip()
        self.assertEqual(call, "mcp add --transport http --scope user higgsfield-zeta https://mcp.higgsfield.ai/mcp")

    def test_no_account_and_default(self):
        p = self.hf("current", "--project", "x", ok=False)
        self.assertEqual(p.returncode, 1)
        self.hf("add", "acme", "--workspace", WS)
        self.hf("default", "acme")
        c = self.current("x")
        self.assertEqual((c["account"], c["chosen_by"]), ("acme", "default"))

    def test_list_and_remove(self):
        self.hf("add", "acme", "--workspace", WS, "--label", "Acme Inc")
        self.hf("use", "acme", "--project", "p1")
        out = self.hf("list", "--project", "p1").stdout
        self.assertIn("* acme", out)
        self.assertIn("projects: p1", out)
        self.hf("remove", "acme")
        self.assertEqual(self.hf("current", "--project", "p1", ok=False).returncode, 1)

    def test_project_detected_from_cwd_and_validation(self):
        self.hf("add", "acme", "--workspace", WS)
        d = self.tmp / "video-studio" / "projects" / "acme-spring" / "work"
        d.mkdir(parents=True)
        self.hf("use", "acme", cwd=d)
        self.assertEqual(self.current("acme-spring")["account"], "acme")
        self.assertNotEqual(self.hf("add", "Bad Name", "--login", ok=False).returncode, 0)
        self.assertNotEqual(self.hf("add", "x", "--workspace", "not-a-uuid", ok=False).returncode, 0)
        reg = json.loads((self.tmp / "cfg" / "higgsfield.json").read_text())
        self.assertNotIn("token", json.dumps(reg).lower())


if __name__ == "__main__":
    unittest.main()
