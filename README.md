# Relocation Job Hunter

Automated job hunting tool that finds relocation-friendly graduate/junior/intern roles, generates tailored CVs and cover letters, and sends outreach emails to hiring teams.

## Features

- **Job scraping** from relocation-friendly sources (RemoteOK, Remotive, We Work Remotely, Relocate.me)
- **Smart filtering** for roles posted in the last 48 hours with relocation/visa support at graduate, junior, or intern level
- **CV-based relevance scoring** to rank up to 100 best-matching jobs
- **AI document tailoring** — generates per-job CV and cover letter using OpenAI
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
  - **OpenAI** — for CV/cover letter tailoring
  - **Hunter.io** — for finding hiring manager emails (optional; falls back to generic addresses)
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
- **LinkedIn/Indeed**: Not included in v1 due to ToS restrictions. Can be added via official APIs with proper credentials.
- **Dry run mode**: Always test email outreach with dry run before sending live emails.

## Environment Variables

See `.env.example` for all configuration options.

## License

MIT
