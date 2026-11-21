# Studio on a free VM (for testing)

The whole stack (web, API, both worker pools, Postgres, Redis, the media bucket) on one **Oracle Cloud Always Free**
VM, with HTTPS and a shared team password in front. $0 a month; the only possible cost is Claude itself (your
Anthropic key, with the per-brand budgets in Studio and a spend limit you set in the Anthropic console).

Why this host: Studio needs a background worker that runs ffmpeg, Whisper and Claude Code with its sandbox (user
namespaces). Render, Koyeb and Railway's free plans have no background workers (or sleep, or delete the database
after 30 days); Oracle's free VM is a real Linux machine that runs everything. Since mid-2026 the free allowance is
**2 Arm cores and 12 GB RAM** (plus 200 GB disk), which is enough for a test team.

## 1. Create the VM (about 10 minutes)

1. Sign up at cloud.oracle.com (Free Tier). It asks for a card to verify you; Always Free resources are never
   charged. Pick a **home region** close to you: free Arm capacity is per region and can't be moved later.
2. Compute → Instances → **Create instance**
   - Image: **Canonical Ubuntu 24.04** (or 22.04)
   - Shape: **Ampere → VM.Standard.A1.Flex**, **2 OCPUs, 12 GB** (the "Always Free-eligible" label shows)
   - Networking: create a new VCN with a **public subnet**, and **assign a public IPv4 address**
   - Boot volume: 100–200 GB (200 GB total is free)
   - Add your SSH public key, then Create
   - "Out of host capacity"? Try another availability domain, or again in an hour; it frees up.
3. Open the web ports: Instance → Subnet → **Security List** → Add Ingress Rules: source `0.0.0.0/0`, TCP,
   destination ports **80** and **443** (two rules).
4. Optional but wise: Networking → reserve the public IP, so the address (and Studio's URL) survives a VM rebuild.

## 2. Install Studio (one command, then 20–40 minutes of building)

```bash
ssh ubuntu@<public-ip>
git clone https://github.com/Eyu-tile/Studio-webApp.git studio && cd studio && git checkout internal-webapp
sudo webapp/deploy/free/setup.sh
```
The repository is private: `git clone` asks for your GitHub username and a **personal access token**
(github.com → Settings → Developer settings → Fine-grained tokens, read-only access to this one repository).

`setup.sh` installs Docker, opens ports 80/443 in the VM's firewall, allows user namespaces for Claude's sandbox,
adds swap, writes `webapp/deploy/free/.env` with fresh random secrets, builds and starts everything, and prints:

```
Studio:    https://<ip-with-dashes>.sslip.io
Password:  user "studio", password "…"
```
The address is free and needs no domain: sslip.io maps the name to your IP, and Caddy gets a Let's Encrypt
certificate for it. To use your own domain later, point it at the VM and change `APP_HOST` / `S3_HOST` in `.env`.

## 3. Use it

1. Open the address, enter the team password (once per browser), sign in with your email: the first person to sign
   in becomes admin.
2. Share the address and the password with the team; they sign in with their own emails.
3. For the Claude tab: put an Anthropic API key in `.env` (`ANTHROPIC_API_KEY=`), set a monthly spend limit for it in
   the Anthropic console, and run `sudo webapp/deploy/free/setup.sh` again.
4. Higgsfield sign-in works here (it needs a public HTTPS address): Brand → Connections → Higgsfield.

## Good to know

- **Sign-in is the dev mode behind a password**: anyone with the team password can sign in as any email. Fine for a
  trial team; before real client data, switch to Google or Microsoft sign-in (`AUTH_MODE=oidc` and the `OIDC_*`
  values, see `docs/DEPLOY.md` §2).
- **Updating**: `git pull` then `sudo webapp/deploy/free/setup.sh` (rebuilds what changed, runs migrations).
- **Backups**: everything lives in Docker volumes on this VM (`studio_pgdata`, `studio_media`). A free VM has no
  backup; for anything you can't lose, copy them off (`docker run --rm -v studio_pgdata:/d -v $PWD:/b alpine tar czf
  /b/pg.tgz -C /d .`) or use the boot volume's backup policy.
- **Logs**: `docker compose -f webapp/deploy/free/docker-compose.yml --env-file webapp/deploy/free/.env logs -f api worker-agent`
- **Idle VMs**: Oracle may reclaim Always Free instances that stay nearly idle for 7 days (CPU, network and memory
  all under 20 %). Regular use keeps it; upgrading the account to Pay As You Go (still $0 within the free limits)
  removes the rule.
- **Limits**: one Claude turn and one media job run at a time (two worker containers). Renders on 2 Arm cores are
  slower than a laptop; fine for testing.
