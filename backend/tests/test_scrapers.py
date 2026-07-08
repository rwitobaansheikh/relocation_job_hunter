"""Scraper tests for the new job sources (mocked HTTP) and sorting default."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeAsyncClient:
    """Stub for httpx.AsyncClient returning canned payloads."""

    payload: dict = {}
    raise_on_get = False

    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, **kwargs):
        if self.raise_on_get:
            raise RuntimeError("network down")
        return FakeResponse(self.payload)


def _run(coro):
    return asyncio.run(coro)


def test_greenhouse_scraper_parses_and_filters_roles():
    from app.services.scraper import greenhouse

    FakeAsyncClient.payload = {
        "jobs": [
            {
                "id": 111,
                "title": "Backend Engineer",
                "absolute_url": "https://boards.greenhouse.io/gitlab/jobs/111",
                "location": {"name": "Remote, Germany"},
                "content": "&lt;p&gt;Build &lt;b&gt;APIs&lt;/b&gt; in Python&lt;/p&gt;",
                "first_published": "2026-07-07T10:00:00-04:00",
                "company_name": "GitLab",
            },
            {
                "id": 222,
                "title": "Account Executive",
                "absolute_url": "https://boards.greenhouse.io/gitlab/jobs/222",
                "location": {"name": "Remote, Italy"},
                "content": "<p>Sales role</p>",
                "updated_at": "2026-07-07T10:00:00-04:00",
            },
        ]
    }
    FakeAsyncClient.raise_on_get = False
    with patch.object(greenhouse.httpx, "AsyncClient", FakeAsyncClient), patch.object(
        greenhouse.settings, "greenhouse_boards", "gitlab"
    ):
        jobs = _run(greenhouse.GreenhouseScraper().fetch_jobs(roles=["backend engineer"]))

    assert len(jobs) == 1
    job = jobs[0]
    assert job.external_id == "greenhouse-gitlab-111"
    assert job.company == "GitLab"
    assert "<" not in job.description and "Python" in job.description
    assert job.posted_at is not None


def test_reed_scraper_gated_on_key_and_parses_dates():
    from app.services.scraper import reed

    with patch.object(reed.settings, "reed_api_key", ""):
        assert _run(reed.ReedScraper().fetch_jobs(roles=["engineer"])) == []

    FakeAsyncClient.payload = {
        "results": [
            {
                "jobId": 555,
                "jobTitle": "Graduate Software Engineer",
                "employerName": "Acme Ltd",
                "locationName": "London",
                "jobDescription": "Great grad role",
                "jobUrl": "https://www.reed.co.uk/jobs/555",
                "date": "07/07/2026",
                "minimumSalary": 30000,
                "maximumSalary": 40000,
            }
        ]
    }
    FakeAsyncClient.raise_on_get = False
    with patch.object(reed.httpx, "AsyncClient", FakeAsyncClient), patch.object(
        reed.settings, "reed_api_key", "key123"
    ):
        jobs = _run(reed.ReedScraper().fetch_jobs(roles=["engineer"]))

    assert len(jobs) == 1
    assert jobs[0].external_id == "reed-555"
    assert jobs[0].posted_at == datetime(2026, 7, 7)
    assert jobs[0].salary_min == 30000 and jobs[0].salary_max == 40000


def test_jobicy_scraper_parses_jobs():
    from app.services.scraper import jobicy

    FakeAsyncClient.payload = {
        "jobs": [
            {
                "id": 146053,
                "jobTitle": "Junior AI Engineer",
                "companyName": "Ruby Labs",
                "url": "https://jobicy.com/jobs/146053",
                "jobDescription": "<p>Remote role</p>",
                "jobGeo": "Europe",
                "pubDate": "2026-07-07 12:00:00",
                "jobIndustry": ["engineering"],
                "jobType": "full-time",
            }
        ]
    }
    FakeAsyncClient.raise_on_get = False
    with patch.object(jobicy.httpx, "AsyncClient", FakeAsyncClient):
        jobs = _run(jobicy.JobicyScraper().fetch_jobs(roles=["ai engineer"]))

    assert len(jobs) == 1
    assert jobs[0].external_id == "jobicy-146053"
    assert jobs[0].location == "Europe"
    assert jobs[0].posted_at == datetime(2026, 7, 7, 12, 0, 0)
    assert "engineering" in jobs[0].tags


def test_google_jobs_scraper_gated_and_parses_relative_dates():
    from app.services.scraper import google_jobs

    with patch.object(google_jobs.settings, "serpapi_api_key", ""):
        assert _run(google_jobs.GoogleJobsScraper().fetch_jobs(roles=["engineer"])) == []

    FakeAsyncClient.payload = {
        "jobs_results": [
            {
                "job_id": "abc123",
                "title": "Software Engineer",
                "company_name": "Acme",
                "location": "Berlin, Germany",
                "description": "Engineering role",
                "share_link": "https://google.com/xyz",
                "detected_extensions": {"posted_at": "3 days ago"},
            }
        ]
    }
    FakeAsyncClient.raise_on_get = False
    with patch.object(google_jobs.httpx, "AsyncClient", FakeAsyncClient), patch.object(
        google_jobs.settings, "serpapi_api_key", "key"
    ):
        jobs = _run(google_jobs.GoogleJobsScraper().fetch_jobs(roles=["engineer"]))

    assert len(jobs) == 1
    assert jobs[0].external_id == "googlejobs-abc123"
    delta = datetime.utcnow() - jobs[0].posted_at
    assert timedelta(days=2, hours=23) < delta < timedelta(days=3, hours=1)


def test_scrapers_return_empty_on_network_failure():
    from app.services.scraper import greenhouse, jobicy

    FakeAsyncClient.raise_on_get = True
    try:
        with patch.object(jobicy.httpx, "AsyncClient", FakeAsyncClient):
            assert _run(jobicy.JobicyScraper().fetch_jobs(roles=["x"])) == []
        with patch.object(greenhouse.httpx, "AsyncClient", FakeAsyncClient), patch.object(
            greenhouse.settings, "greenhouse_boards", "gitlab"
        ):
            assert _run(greenhouse.GreenhouseScraper().fetch_jobs(roles=["x"])) == []
    finally:
        FakeAsyncClient.raise_on_get = False


def test_applications_default_sort_is_match_score_desc():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.database import Base, Job, JobApplication, User, UserProfile
    from app.routes import list_applications

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()

    user = User(email="u@example.com", password_hash="x")
    s.add(user)
    s.flush()
    profile = UserProfile(user_id=user.id, full_name="U", email="u@example.com")
    s.add(profile)
    s.flush()
    for i, score in enumerate([10, 90, 50]):
        job = Job(external_id=f"j{i}", source="test", title=f"Job {i}", company="C", url="u")
        s.add(job)
        s.flush()
        s.add(JobApplication(user_profile_id=profile.id, job_id=job.id,
                             status="discovered", ai_match_score=score))
    s.commit()

    default_order = list_applications(status=None, sort=None, automation_batch=None,
                                      manual_only=False, profile=profile, db=s)
    assert [a.ai_match_score for a in default_order] == [90, 50, 10]

    newest = list_applications(status=None, sort="newest", automation_batch=None,
                               manual_only=False, profile=profile, db=s)
    assert len(newest) == 3
