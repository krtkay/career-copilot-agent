# Production deployment (free tier)

This app deploys to an **Oracle Cloud "Always Free" Ampere A1 VM** (a real,
perpetually-free root-access box — not a trial credit), with **GitHub
Actions + GHCR** handling CI/CD. Everything here is a one-time setup; after
it's done, every push to `main` auto-deploys.

Why this stack and not something managed (Render/Railway/Fly.io/AWS free
tier): this app needs a stateful Postgres+pgvector database with no expiry
*and* an API process with no sleep, running at the same time, for free,
forever. No managed free tier holds both simultaneously — Oracle's Always
Free compute does, because it's IaaS, not a hosted service.

## Prerequisites

- An Oracle Cloud account ([signup](https://signup.oraclecloud.com)) — needs
  a card for identity verification (a temporary ~$1 hold, no recurring
  charge). Occasionally triggers manual review; don't leave this for the day
  before a deadline.
- The GitHub repo created and pushed (see main README/chat history — `git
  remote add origin ...` then `git push -u origin main`).
- An SSH keypair dedicated to deployment (**do not reuse your personal key**):

  ```bash
  ssh-keygen -t ed25519 -f deploy_key -C "career-copilot-deploy" -N ""
  ```

  This produces `deploy_key` (private) and `deploy_key.pub` (public).

## 1. Provision the VM

In the OCI Console:

1. **Compute → Instances → Create instance.**
2. **Name:** `career-copilot-vm`.
3. **Placement:** pick **Frankfurt (eu-frankfurt-1)** or **Singapore
   (ap-singapore-1)** — US regions frequently report "out of A1 capacity."
4. **Image and shape:** Ubuntu **24.04**, then Shape → Ampere → **VM.Standard.A1.Flex**
   — set **2 OCPU / 12 GB RAM** (the current Always Free allowance).
5. **Add SSH keys:** paste the contents of `deploy_key.pub` from above.
6. **Networking:** use the default VCN, or create one. Leave "Assign a
   public IPv4 address" checked for now — you'll convert it to a
   **reserved** IP next (an ephemeral IP changes on stop/start, which would
   break DNS/TLS every time the VM restarts).
7. **Create.** Boot takes a couple of minutes.

### Reserve the public IP

Networking → Virtual Cloud Networks → your VCN → **Reserved Public IPs** →
create one, then attach it to the instance's VNIC (replacing the ephemeral
IP). Note this IP — call it `VM_IP` below.

## 2. Firewall — two layers, both must open 80/443 only

OCI has **two independent firewalls**; a rule in only one still blocks
traffic. Keep 5432/9090/3000 closed at both layers — they're loopback-bound
in `docker-compose.prod.yml` already, but a closed firewall is defense in
depth.

**a) OCI Security List** (Networking → VCN → Security Lists → default):
add stateful ingress rules for `0.0.0.0/0` → TCP destination ports `80` and
`443`. Leave everything else as-is (22 for SSH should already be open from
the default list).

**b) Ubuntu's host firewall** (`iptables`/`netfilter`, via SSH once the VM is up):

```bash
ssh -i deploy_key ubuntu@VM_IP
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

## 3. Install Docker

Still SSHed into the VM:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
sudo systemctl enable docker   # survives reboots/maintenance events
newgrp docker
```

## 4. First-boot setup

```bash
sudo mkdir -p /opt/career-copilot
sudo chown ubuntu:ubuntu /opt/career-copilot
cd /opt/career-copilot
```

Copy `docker-compose.prod.yml` and `Caddyfile` from your machine to the VM
once by hand (CI will keep them in sync on every subsequent deploy):

```bash
scp -i deploy_key docker-compose.prod.yml Caddyfile ubuntu@VM_IP:/opt/career-copilot/
```

### Point a hostname at the VM

No DNS purchase needed — [sslip.io](https://sslip.io) resolves
`<ip-with-dashes>.sslip.io` to that IP automatically. If `VM_IP` is
`203.0.113.10`, your hostname is `203-0-113-10.sslip.io`. Edit `Caddyfile`
on the VM (or set `DEPLOY_HOSTNAME` in `.env`, read by `docker-compose.prod.yml`'s
Caddy service) to match your real IP.

### Create the production `.env`

On the VM, at `/opt/career-copilot/.env` (never committed to git, `chmod 600`):

| Variable | Value | Why |
|---|---|---|
| `APP_ENV` | `production` | Trips `_validate_production_safety`. |
| `DEBUG` | `false` | Required by the same validator. |
| `JWT_SECRET_KEY` | output of `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` | Must not start with `change-me`. |
| `CORS_ORIGINS` | `https://<ip-with-dashes>.sslip.io` | Must not contain `*`. |
| `POSTGRES_USER` / `POSTGRES_DB` | e.g. `postgres` / `career_copilot` | As in dev. |
| `POSTGRES_PASSWORD` | a real generated password | The dev default (`postgres`) is a live vulnerability if ever exposed. |
| `GRAFANA_ADMIN_PASSWORD` | a real generated password | `docker-compose.prod.yml` templates this — no more hardcoded `admin`. |
| `LLM1_NAME` / `LLM1_MODEL` / `LLM1_BASE_URL` / `LLM1_API_KEY` | your real provider values | Needed for the app to answer at all. |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | your real values | Needed for job_search. |
| `DEPLOY_HOSTNAME` | `<ip-with-dashes>.sslip.io` | Read by the Caddy service (see Caddyfile). |

```bash
chmod 600 /opt/career-copilot/.env
```

### First manual boot (before CI takes over)

```bash
cd /opt/career-copilot
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.prod.yml up -d --remove-orphans
docker compose -f docker-compose.prod.yml logs api | grep graph_ready   # confirm Postgres checkpointer, not the MemorySaver fallback
```

The first `pull` needs an image to already exist at
`ghcr.io/<owner>/<repo>:latest` — push to `main` once (see below) so the
`build-and-push` job runs before you do this.

## 5. Wire up GitHub Actions

In the GitHub repo → **Settings → Secrets and variables → Actions**, add:

| Secret | Value |
|---|---|
| `DEPLOY_HOST` | `VM_IP` |
| `DEPLOY_USER` | `ubuntu` |
| `DEPLOY_SSH_KEY` | contents of `deploy_key` (the **private** key — never `deploy_key.pub`) |

No GHCR credentials are needed — the `build-and-push` job uses the
automatic `GITHUB_TOKEN`, and a **public** repo means no pull-auth is needed
on the VM either.

Push to `main`:

```bash
git push origin main
```

This runs `.github/workflows/ci-cd.yml`: `test` → `build-and-push` (cross-builds
`linux/arm64` since GitHub's runners are x86_64 but the VM is ARM) →
`deploy` (SCPs the compose/Caddy config, then SSHes in to pull, migrate,
and restart, with a health-check and a `graph_ready` log check — failing
the whole run loudly if either doesn't pass).

## 6. Verify

- `https://<ip-with-dashes>.sslip.io/docs` — FastAPI's Swagger UI over real HTTPS.
- `https://<ip-with-dashes>.sslip.io/api/v1/health` — health check.
- Reboot the VM (`sudo reboot`) and confirm the whole stack comes back on
  its own (`restart: unless-stopped` + `systemctl enable docker`) — no
  manual `docker compose up` needed.
- Admin access to Grafana/Prometheus (not public): `ssh -i deploy_key -L
  3000:localhost:3000 ubuntu@VM_IP`, then open `http://localhost:3000`
  locally.

## Rollback

Every image is also tagged with its commit SHA. To roll back without
waiting on a new build:

```bash
ssh -i deploy_key ubuntu@VM_IP
cd /opt/career-copilot
API_IMAGE=ghcr.io/<owner>/<repo>:<old-sha> docker compose -f docker-compose.prod.yml up -d
```

## Operational notes

- **Backups:** there is no automated Postgres backup yet. The VM is the
  sole copy of user/ticket/embedding/checkpoint data. Recommended: a cron
  `pg_dump` (via `docker compose exec db pg_dump ...`) rotated into Oracle's
  free Object Storage tier.
- **Idle reclamation:** Oracle can reclaim a genuinely idle A1 instance (a
  7-day rolling window where CPU/network/memory all sit under the 10th
  percentile). This stack's baseline load (10s Prometheus scrapes, Postgres
  background activity) should keep it above that threshold — worth a manual
  check in month one.
- **Portability:** nothing here is Oracle-proprietary. The whole stack (compose
  files, Caddy, GitHub Actions) moves to any other VM unmodified if Oracle's
  free-tier terms change again (they already did once, in June 2026).
