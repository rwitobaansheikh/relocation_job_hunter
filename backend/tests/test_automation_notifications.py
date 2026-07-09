"""Automation run-summary email tests."""

import asyncio
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import AutomationLoop, AutomationRun, Base, Job, JobApplication, User, UserProfile
from app.services.automation_notifications import build_run_summary_email, notify_run_complete


class FakeUser:
    email = "user@example.com"


class FakeLoop:
    id = 7
    name = "Frontend roles in Germany"
    role = "Frontend Engineer"
    user_profile_id = 1


class FakeRun:
    jobs_found = 3
    jobs_tailored = 2


class FakeJob:
    def __init__(self, title, company, location):
        self.title = title
        self.company = company
        self.location = location


class FakeApp:
    def __init__(self, title, company, location, score):
        self.job = FakeJob(title, company, location)
        self.ai_match_score = score


def test_run_email_lists_new_jobs_and_link():
    apps = [
        FakeApp("Frontend Engineer", "Acme", "Berlin, Germany", 91),
        FakeApp("React Developer", "Globex", "Munich, Germany", 84),
    ]
    to, subject, text, html = build_run_summary_email(
        FakeUser(), FakeLoop(), FakeRun(), apps, "2026-07-09"
    )
    assert to == "user@example.com"
    assert "3 new jobs" in subject and "Frontend roles in Germany" in subject
    assert "Frontend Engineer" in text and "Acme" in text and "91/100" in text
    assert "2 already tailored" in text
    assert "/app/applications" in text
    assert "Frontend Engineer" in html and "Review your new jobs" in html


def test_run_email_no_jobs_variant():
    run = FakeRun()
    run.jobs_found = 0
    run.jobs_tailored = 0
    to, subject, text, html = build_run_summary_email(
        FakeUser(), FakeLoop(), run, [], "2026-07-09"
    )
    assert "no new jobs" in subject.lower()
    assert "No new jobs matched" in text
    assert "/app/automation" in text and "/app/automation" in html


def test_notify_run_complete_sends_email_with_top_jobs():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()

    user = User(email="owner@example.com", password_hash="x")
    s.add(user)
    s.flush()
    profile = UserProfile(user_id=user.id, full_name="Owner", email=user.email)
    s.add(profile)
    s.flush()
    loop = AutomationLoop(user_profile_id=profile.id, name="ML loop", role="ML Engineer")
    s.add(loop)
    s.flush()

    batch = "2026-07-09"
    for i, score in enumerate([88, 72]):
        job = Job(external_id=f"j{i}", source="test", title=f"ML Engineer {i}", company="Acme", url="u")
        s.add(job)
        s.flush()
        s.add(JobApplication(
            user_profile_id=profile.id, job_id=job.id, status="discovered",
            ai_match_score=score, automation_batch_date=batch,
        ))
    run = AutomationRun(
        user_profile_id=profile.id, automation_loop_id=loop.id,
        status="success", jobs_found=2, jobs_tailored=1,
    )
    s.add(run)
    s.commit()

    sent = {}

    async def fake_send(to, subject, text, html=None, attachments=None):
        sent.update(to=to, subject=subject, text=text)
        return True, None

    with patch("app.services.automation_notifications.send_system_email", fake_send):
        ok = asyncio.run(notify_run_complete(s, loop, run, batch))

    assert ok is True
    assert sent["to"] == "owner@example.com"
    assert "2 new jobs" in sent["subject"]
    assert "ML Engineer 0" in sent["text"]  # highest score listed
