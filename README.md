# Job Application Flow

Automated job search platform that discovers roles across major job boards, suggests target job titles from your CV, generates tailored CVs and cover letters, and sends outreach emails to hiring teams.

## Features

- **Job scraping** from LinkedIn (public guest search) plus relocation-friendly sources (RemoteOK, Remotive, We Work Remotely, Relocate.me)
- **Smart filtering** by seniority, location, salary and posted date; relocation/visa support boosts ranking when relevant
- **AI role suggestions** from your uploaded CV and cover letter
- **CV-based relevance scoring** to rank up to 100 best-matching jobs
- **AI document tailoring** — generates a per-job one-page CV and cover letter (PDF) using a local LLM (Ollama), with match score, score breakdown, and gap analysis
- **Email outreach** — built-in recruiting email scraper (website + search + AI) finds 3–6 HR contacts per company and sends tailored applications
- **Web dashboard** — upload documents, track applications, manage follow-ups

## Architecture

```
relocation-job-hunter/
├── backend/          # FastAPI + SQLAlchemy
│   └── app/
│       ├── services/
│       │   ├── scraper/     # Job board scrapers
│       │   ├── job_search.py
│       │   ├── job_matcher.py
│       │   ├── document_generator.py
│       │   ├── email_scraper.py
│       │   └── email_service.py
│       ├── routes.py
│       └── main.py
└── frontend/         # React + Vite
    └── src/
        └── pages/    # Dashboard, Profile, Jobs, Applications
```

## Prerequisites

- Python 3.11+
- Node.js 18+
- **Ollama** (local LLM, default) — [install Ollama](https://ollama.com), then `ollama pull llama3.2:3b`
- Optional API keys (see `.env.example`):
  - **SMTP** — for sending outreach emails (Gmail app password works)
  - **Google Gemini** — only if you set `LLM_PROVIDER=gemini` instead of local Ollama

## Setup

### 1. Backend

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
cp ../.env.example .env
# Edit .env (SMTP, etc.)

uvicorn app.main:app --reload --port 8000
```

### Local LLM (Ollama)

CV tailoring, outreach emails, and search suggestions use **Ollama** on your GPU by default — no cloud API key or per-token billing.

```bash
# Install Ollama from https://ollama.com, then pull a small instruct model:
ollama pull llama3.2:3b

# Verify:
curl http://localhost:11434/api/tags
curl http://localhost:8000/health   # should show llm.status: ok
```

Recommended models (light GPU / prose + JSON):

| Model | VRAM | Notes |
|-------|------|-------|
| `llama3.2:3b` | ~2 GB | Default; fast for emails and cover letters |
| `mistral:7b-instruct` | ~5 GB | Better prose quality |
| `qwen2.5:7b-instruct` | ~5 GB | Stronger structured JSON for CVs |

Set `OLLAMA_MODEL` in `backend/.env`. For heavier tailoring quality, use a 7B model; prose tasks do not need 70B models.

**AWS production:** run Ollama as a sidecar (see `docker-compose.yml`) on a GPU instance (`g4dn.xlarge` etc.), set `OLLAMA_BASE_URL=http://ollama:11434`, and pull the model on first boot. No Gemini key required unless you switch `LLM_PROVIDER=gemini`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 in your browser.

## Usage Flow

1. **Profile** — Create your profile with name, skills, and locations
2. **Upload** — Upload your CV (PDF/DOCX) and baseline cover letter; use **Analyze CV & suggest roles** or enter your own target roles
3. **Search** — Run a job search to find up to 100 relevant relocation-friendly roles
4. **Tailor** — Generate tailored CV and cover letter for each application
5. **Outreach** — Preview (dry run) or send emails to hiring contacts
6. **Track** — Monitor application status and schedule follow-ups

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/profiles` | Create user profile |
| POST | `/api/profiles/{id}/upload-cv` | Upload CV |
| POST | `/api/profiles/{id}/upload-cover-letter` | Upload cover letter |
| POST | `/api/jobs/search` | Search and store jobs |
| GET | `/api/applications` | List applications |
| POST | `/api/applications/tailor` | Tailor documents (batch) |
| POST | `/api/recruiting-emails/find` | Find HR/recruiting emails for a company |
| GET | `/api/applications/{id}/contacts` | Find contacts for an application |
| POST | `/api/applications/follow-up` | Log follow-up |
| GET | `/api/dashboard/stats` | Dashboard statistics |

## Important Notes

- **Scraping ethics**: Uses public APIs and RSS feeds where available. Respect robots.txt and rate limits for any custom scrapers added later.
- **Email compliance**: Only send outreach to professional contacts. Include an unsubscribe option for production use. CAN-SPAM/GDPR may apply depending on your jurisdiction.
- **LinkedIn**: Scraped via LinkedIn's unauthenticated public guest job-search endpoints (no login required). LinkedIn rate-limits aggressively and this may conflict with their Terms of Service — requests are throttled/bounded, but use responsibly. Indeed is not included due to ToS restrictions.
- **Dry run mode**: Always test email outreach with dry run before sending live emails.

## Environment Variables

See `.env.example` for all configuration options.

## Deployment (AWS + GitHub Actions)

The app ships as a **single Docker image** (FastAPI backend that also serves the
built React frontend on the same origin) running on **one EC2 instance** via
Docker Compose. SQLite and uploaded/generated files persist on the instance's
`/data` directory. CI/CD builds the image, pushes it to **ECR**, and deploys
over SSH.

```
GitHub push ──► GitHub Actions ──► build image ──► push to ECR
                                          │
                                          └─► SSH to EC2 ─► docker compose pull && up
EC2 (Docker): app container :80 ─► uvicorn :8000  (+ /data volume: SQLite, uploads, generated)
```

### Files

| Path | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage build: Vite frontend → Python backend serving it |
| `docker-compose.yml` | Runs the image on the instance (port 80, `/data` volume) |
| `.env.production.example` | Template for the instance env (becomes the `APP_ENV` secret) |
| `infra/terraform/` | Provisions ECR, EC2, Elastic IP, security group, IAM, GitHub OIDC role |
| `.github/workflows/deploy.yml` | Build → push to ECR → SSH deploy |

### 1. Provision infrastructure (Terraform)

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # fill in github_repo + ssh_public_key
terraform init
terraform apply
```

Note the outputs — you'll need them for the GitHub secrets below:
`ecr_repository_url`, `instance_public_ip`, `github_actions_role_arn`, `app_url`.

> Tip: lock SSH down by setting `allowed_ssh_cidr` to `<your-ip>/32`.

### 2. Configure GitHub repository secrets

| Secret | Value |
|--------|-------|
| `AWS_REGION` | e.g. `eu-west-2` |
| `AWS_DEPLOY_ROLE_ARN` | Terraform output `github_actions_role_arn` |
| `ECR_REPOSITORY` | The repo **name** (e.g. `relocation-job-hunter`) |
| `EC2_HOST` | Terraform output `instance_public_ip` |
| `EC2_USER` | `ec2-user` |
| `EC2_SSH_KEY` | The **private** key matching `ssh_public_key` |
| `APP_ENV` | Full contents of a filled-in `.env.production.example` (Gemini/Hunter/SMTP keys, plus the now-required `JWT_SECRET` and `ENCRYPTION_KEY`) |

### 3. Deploy

Push to `main` (or run the **Build & Deploy** workflow manually). The pipeline
builds and pushes the image, copies `docker-compose.yml` + a generated `.env`
to `/opt/app`, then runs `docker compose pull && up -d`.

Once finished, open the `app_url` output (`http://<elastic-ip>`).

### Notes

- **Single worker on purpose**: SQLite and local-file storage aren't safe across
  multiple worker processes, so the container runs one uvicorn worker. Fine for a
  single-user tool.
- **Backups**: everything stateful lives under `/data` on the instance — snapshot
  the EBS volume or `scp` `/data` to back up.
- **Rate limits**: tailoring + per-contact email generation make several Gemini
  calls; on the free tier you may hit `429`. Consider enabling billing for steady use.

### Custom domain + HTTPS (jobapplicationflow.com via Cloudflare)

The domain is registered at **Ionos** and routed through **Cloudflare**. Two
supported paths — the Tunnel option is recommended (no inbound ports, free TLS):

**A. Cloudflare Tunnel (recommended)**

1. Point the domain at Cloudflare: in the Ionos control panel set the domain's
   nameservers to the two Cloudflare nameservers shown when you add the site in
   the Cloudflare dashboard (Add a site → Free plan). DNS propagation takes a
   few minutes to a few hours.
2. In **Cloudflare Zero Trust → Networks → Tunnels**, create a tunnel and copy
   its **token** into `CLOUDFLARE_TUNNEL_TOKEN` in the `APP_ENV` secret.
3. Add **Public Hostnames** to the tunnel:
   - `jobapplicationflow.com` → Service `http://app:8000`
   - `www.jobapplicationflow.com` → Service `http://app:8000`
   Cloudflare auto-creates the proxied DNS records and serves HTTPS.
4. Deploy with the sidecar:
   `docker compose -f docker-compose.yml -f docker-compose.cloudflared.yml up -d`.
   You can then tighten the security group to drop inbound 80/443 entirely.

**B. Cloudflare proxy to the Elastic IP**

1. Same nameserver delegation from Ionos to Cloudflare as above.
2. In Cloudflare **DNS**, add a proxied (orange-cloud) `A` record for
   `jobapplicationflow.com` (and `www`) pointing at the EC2 **Elastic IP**.
3. Set **SSL/TLS → Overview** mode to **Full**. For a valid origin leg, install
   a Cloudflare **Origin Certificate** behind Caddy/nginx on port 443
   (port 443 is already open in the security group); "Flexible" works without an
   origin cert but leaves the Cloudflare↔origin hop unencrypted.

For both paths, add the domain to `CORS_ORIGINS` (already done in
`.env.production.example`).

Note: the billing page localizes the displayed price using Cloudflare's
`CF-IPCountry` request header, which is only present when traffic is **proxied
through Cloudflare** (orange-cloud or Tunnel). Direct-to-IP access falls back to
USD display. The actual charge currency is handled by Stripe Adaptive Pricing.

## Plans & billing (Stripe)

Subscriptions are optional: with no Stripe keys set, every account stays on the
free trial and an admin can grant **Unlimited access** to specific users from the
Admin page (useful for the dev/QA team).

Tiers (USD base price; Stripe Adaptive Pricing charges each buyer in their local
currency):

| Plan | Price | Automation loops | Auto applies / loop / day | Manual applies / day |
| --- | --- | --- | --- | --- |
| Free trial (7 days) | - | 1 | 5 | 20 |
| Basic | $15 | 1 | 5 | 20 |
| Standard | $25 | 3 | 20 | 100 |
| Pro | $45 | 5 | 25 | 300 |

Loops are hard-capped at 5 even for unlimited/superusers. A "manual application"
is one `Send Outreach` action on a job (independent of how many contacts get
emailed). Automated sends are capped per loop per day.

To enable payments:

1. In the **Stripe dashboard**, create one **recurring USD Price** per tier and
   put the price IDs in `STRIPE_PRICE_BASIC/STANDARD/PRO`.
2. Enable **Adaptive Pricing** (Settings → Payments) so checkout shows the
   buyer's local currency automatically.
3. Add a **webhook** endpoint at `https://jobapplicationflow.com/api/webhooks/stripe`
   subscribed to `checkout.session.completed`, `customer.subscription.*`, and
   `invoice.payment_failed`; copy the signing secret into `STRIPE_WEBHOOK_SECRET`.
4. Set `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, and
   `APP_BASE_URL=https://jobapplicationflow.com` in the `APP_ENV` secret.

The webhook keeps each user's `plan`/status in sync; plan limits are then
enforced server-side on sending and loop creation.

## Data & privacy (GDPR)

Users can exercise the right to erasure themselves: **Settings → Delete account**
(requires password + typing `DELETE`). This calls `DELETE /api/account`, which:

- cancels any active Stripe subscription (best-effort),
- erases the user, profile, applications, outreach emails, automation loops/runs,
  usage counters, and any reviews/contact messages they submitted (matched by
  email), and
- deletes their uploaded CV/cover letter and all generated PDFs from disk.

Shared, non-personal records (deduplicated `jobs`, aggregate `api_usage`) are
retained. The action is irreversible.

## License

MIT
