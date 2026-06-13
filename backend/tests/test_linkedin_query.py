from app.services.scraper.linkedin_query import (
    build_linkedin_search_params,
    build_linkedin_search_url,
    experience_codes_for_levels,
    resolve_work_type_codes,
    split_locations,
)


def test_experience_codes_for_intern_and_entry():
    assert experience_codes_for_levels(["intern", "entry"]) == "1,2,3"


def test_split_locations_extracts_remote_and_geo():
    geo, wt = split_locations(["Remote", "United Kingdom", "Hybrid"])
    assert geo == ["United Kingdom"]
    assert wt == ["2", "3"]


def test_build_params_matches_n8n_style_query():
    params = build_linkedin_search_params(
        keywords="Software Engineer",
        location="London",
        age_hours=6,
        experience_codes="1,2",
        work_type_codes=["2"],
        start=0,
    )
    assert params["f_TPR"] == "r21600"
    url = build_linkedin_search_url(params)
    assert url.startswith("https://www.linkedin.com/jobs/search/?")
    assert "keywords=Software+Engineer" in url


def test_split_locations_extracts_work_type_only():
    geo, wt = split_locations(["Remote", "Hybrid"])
    assert geo == []
    assert wt == ["2", "3"]


def test_resolve_work_type_codes_merges_ui_and_locations():
    codes = resolve_work_type_codes(["remote"], ["Germany", "Hybrid"])
    assert codes == ["2", "3"]
