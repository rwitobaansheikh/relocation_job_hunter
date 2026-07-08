"""Job matcher tests: seniority word boundaries, location restriction, scoring."""

from datetime import datetime, timedelta

from app.services.job_matcher import JobMatcher
from app.services.scraper.base import RawJob


class FakeProfile:
    cv_text = "python developer with fastapi react sql docker experience building web apps"
    target_roles = "software engineer, python developer"
    target_countries = "germany"
    skills = "python, fastapi, react, sql, docker"


def _job(title="Software Engineer", description="", location="Berlin, Germany",
         source="linkedin", posted_at=None, tags=None):
    return RawJob(
        external_id="x-1",
        source=source,
        title=title,
        company="Acme",
        url="https://example.com/job",
        description=description,
        location=location,
        posted_at=posted_at,
        tags=tags or [],
    )


matcher = JobMatcher()


# ---- detect_experience_level: word boundaries -------------------------------
def test_leadership_program_not_rejected_as_senior():
    job = _job(title="Graduate Leadership Development Program",
               description="Early careers program for recent graduates.")
    assert matcher.detect_experience_level(job) != ""


def test_staffing_coordinator_not_rejected_as_senior():
    job = _job(title="Staffing Coordinator", description="Entry level junior role.")
    assert matcher.detect_experience_level(job) != ""


def test_senior_and_lead_titles_still_rejected():
    assert matcher.detect_experience_level(_job(title="Senior Engineer")) == ""
    assert matcher.detect_experience_level(_job(title="Lead Engineer")) == ""
    assert matcher.detect_experience_level(_job(title="Engineering Manager")) == ""


def test_grad_word_boundary_no_upgrade_false_positive():
    job = _job(title="Software Engineer", description="You will upgrade our systems.")
    assert matcher.detect_experience_level(job) == "unspecified"


# ---- classify_seniority ------------------------------------------------------
def test_associate_director_is_executive():
    assert matcher.classify_seniority(_job(title="Associate Director of Engineering")) == "executive"


def test_associate_engineer_is_entry():
    assert matcher.classify_seniority(_job(title="Associate Software Engineer")) == "entry"


# ---- matches_locations: worldwide must respect explicit country -------------
def test_worldwide_job_does_not_bypass_country_restriction():
    job = _job(title="Engineer", description="Work from anywhere, worldwide team.",
               location="Worldwide")
    assert matcher.matches_locations(job, ["germany"]) is False


def test_worldwide_job_passes_remote_search():
    job = _job(title="Engineer", description="Work from anywhere, worldwide team.",
               location="Worldwide")
    assert matcher.matches_locations(job, ["remote"]) is True


def test_country_match_still_works():
    assert matcher.matches_locations(_job(location="Berlin, Germany"), ["germany"]) is True
    assert matcher.matches_locations(_job(location="Munich"), ["germany"]) is True  # alias


def test_empty_locations_allow_all():
    assert matcher.matches_locations(_job(location="Tokyo, Japan"), []) is True


# ---- score_relevance ---------------------------------------------------------
def test_score_role_in_title_beats_role_in_description():
    profile = FakeProfile()
    in_title = _job(title="Python Developer", description="Great role.")
    in_desc = _job(title="Backend Wizard", description="We need a python developer.")
    no_role = _job(title="Backend Wizard", description="Great role.")
    s1 = matcher.score_relevance(in_title, profile)
    s2 = matcher.score_relevance(in_desc, profile)
    s3 = matcher.score_relevance(no_role, profile)
    assert s1 > s2 > s3


def test_score_does_not_stack_multiple_roles():
    # Empty CV isolates role scoring from the CV-overlap component.
    profile = FakeProfile()
    profile.cv_text = ""
    profile.target_roles = "software engineer, data analyst"
    one_role = _job(title="Software Engineer", location="")
    both_roles = _job(title="Software Engineer / Data Analyst", location="")
    # Best-match-only: naming both target roles must not add another +20.
    assert matcher.score_relevance(both_roles, profile) == matcher.score_relevance(one_role, profile)


def test_freshness_bonus_ranks_recent_above_undated():
    profile = FakeProfile()
    fresh = _job(posted_at=datetime.utcnow() - timedelta(hours=1))
    undated = _job(posted_at=None)
    assert matcher.score_relevance(fresh, profile) > matcher.score_relevance(undated, profile)


def test_strong_match_does_not_saturate_at_100():
    profile = FakeProfile()
    strong = _job(
        title="Python Developer",
        description="python fastapi react sql docker relocation package to Germany "
        "for a python developer building web apps",
        posted_at=datetime.utcnow(),
    )
    score = matcher.score_relevance(strong, profile)
    assert 50 <= score < 100


def test_skills_bonus_capped():
    # Empty CV isolates the skills component from CV-overlap.
    profile = FakeProfile()
    profile.cv_text = ""
    all_skills = _job(title="X", description="python fastapi react sql docker", location="")
    one_skill = _job(title="X", description="python", location="")
    diff = matcher.score_relevance(all_skills, profile) - matcher.score_relevance(one_skill, profile)
    # 5 skills at +4 uncapped would add 16 over one skill; the 15 cap keeps it at 11.
    assert diff == 11
