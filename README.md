# Relocation Job Hunter

Automated job hunting tool that finds relocation-friendly graduate/junior/intern roles, generates tailored CVs and cover letters, and sends outreach emails to hiring teams.

## Features

- **Job scraping** from LinkedIn (public guest search) plus relocation-friendly sources (RemoteOK, Remotive, We Work Remotely, Relocate.me)
- **Smart filtering** for roles posted in the last 48 hours at graduate, junior, or intern level (relocation/visa support boosts ranking but is not required)
- **CV-based relevance scoring** to rank up to 100 best-matching jobs
- **AI document tailoring** — generates a per-job one-page CV and cover letter (PDF) using Google Gemini, with an AI match score, score breakdown, and gap analysis
- **Email outreach** — finds up to 5 contacts per company via Hunter.io and sends tailored applications
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
│       │   ├── email_finder.py
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
- API keys (see `.env.example`):
  - **Google Gemini** — for CV/cover letter tailoring
  - **Hunter.io** — for finding/verifying hiring manager emails (optional; falls back to generic addresses)
  - **SMTP** — for sending outreach emails (Gmail app password works)

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
# Edit .env with your API keys

uvicorn app.main:app --reload --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 in your browser.

## Usage Flow

1. **Profile** — Create your profile with name, skills, target roles/countries
2. **Upload** — Upload your CV (PDF/DOCX) and baseline cover letter
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
| POST | `/api/applications/send-outreach` | Send outreach emails |
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
| `APP_ENV` | Full contents of a filled-in `.env.production.example` (Gemini/Hunter/SMTP keys, etc.) |

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
- **HTTPS/domain (later)**: port 443 is already open in the security group. To add
  TLS, put Caddy or nginx + Let's Encrypt in front (or an ALB + ACM cert) and add
  your domain to `CORS_ORIGINS`.
- **Rate limits**: tailoring + per-contact email generation make several Gemini
  calls; on the free tier you may hit `429`. Consider enabling billing for steady use.

## License

MIT
