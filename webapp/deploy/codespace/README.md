# Studio in a GitHub Codespace (free, no card)

The whole stack (web, API, both workers, Postgres, Redis, the media bucket) in a GitHub Codespace, reachable over
HTTPS by your team with a shared password. Free on a **personal** GitHub account: 120 core-hours a month (about
**60 hours** on the 2-core machine) and 15 GB of storage, no card needed. The only possible cost is Claude itself
(your Anthropic key).

It runs while the codespace runs: it stops after 30 minutes without activity in the codespace (raise it to 4 hours in
github.com → Settings → Codespaces → Default idle timeout) and starts again, with all its data, when you open it.
Good for testing sessions with the team; for always-on, use a VM (`../free/README.md`).

## Start it (one click, then 20–40 minutes of building the first time)

1. Open this link while signed in to GitHub, and press **Create codespace** (branch, configuration and machine are
   already filled in):
   **https://codespaces.new/Eyu-tile/Studio-webApp/tree/internal-webapp?devcontainer_path=.devcontainer/studio/devcontainer.json&machine=basicLinux32gb**
2. (The same by hand: on the repository, branch `internal-webapp`, **Code → Codespaces → ⋯ → New with options**,
   configuration **Studio**, machine **2-core**.)
3. The codespace opens in a couple of minutes, and Studio builds **in the background** (20–40 minutes the first
   time). A terminal shows where it stands and follows the build; when it's done it shows the address and the
   team password. Run `bash webapp/deploy/codespace/status.sh` any time to see it again.
4. If the end message asks for it: **Ports** tab (bottom panel), right-click **8080** → Port Visibility → **Public**,
   and the same for **8333** (media uploads and playback). Once per codespace; the start script tries it first.
5. Open the printed address (`https://<codespace>-8080.app.github.dev`), enter user `studio` and the password, then
   sign in with your email: the first person becomes admin. Share the address and password with the team.

Later: open the codespace again (github.com → Codespaces) and Studio starts by itself in about a minute.

## Good to know

- **Sign-in is the test mode behind one shared password**: anyone with it can sign in as any email. Fine for a trial;
  before real client data, set up Google or Microsoft sign-in (`docs/DEPLOY.md` §2).
- **The Claude tab**: put an Anthropic API key in `webapp/deploy/free/.env` (`ANTHROPIC_API_KEY=`), set a spend limit
  for it in the Anthropic console, then run `bash webapp/deploy/codespace/start.sh` in the codespace terminal.
- **Claude's sandbox** needs user namespaces inside Docker. If a Claude message fails with "Claude Code's sandbox
  can't run on this worker", the codespace's kernel doesn't allow them; tell the engineering side before turning the
  sandbox off (`AGENT_SANDBOX=false` removes the network allowlist for Claude's commands).
- **Storage**: the images and data take about 10–12 GB of the free 15 GB-month; delete other codespaces you don't use.
  Deleting this codespace deletes Studio's data in it.
- **Updating**: in the codespace terminal, `git pull` then `bash webapp/deploy/codespace/start.sh`.
