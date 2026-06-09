"""LLM-based job/resume analysis: structured match scoring, gap analysis, and a
tailored cover letter, all in a single Gemini call.

The prompt and output schema are adapted from a precise job-matching assistant
spec. Output is parsed defensively (code fences, END_OF_JSON sentinel, and
brace-matching) so partial/decorated model output still yields valid JSON.
"""

import json
import logging
import re
from typing import Optional

from app.services.llm import llm_generate, resolve_gemini_api_key

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = "You are a precise job-matching assistant."

PROMPT_TEMPLATE = """You are a precise job-matching assistant.

Return ONE JSON object wrapped in ```json fences, followed by the line END_OF_JSON.
No extra prose. No Markdown inside the JSON. No comments.

INPUTS
Company: {{COMPANY}}
job_description: {{JOB_DESCRIPTION}}
my_resume: {{RESUME}}

TASKS
1) Parse job_description -> job_analysis with keys:
   title (string), company (string), must_have_skills (string[]), nice_to_have_skills (string[]),
   responsibilities (string[]), years_of_experience (string), education_certifications (string),
   location_constraints (string), domain_industry_focus (string), tech_stack (string[]), measurable_kpis (string[])

2) Parse my_resume -> resume_analysis:
   core_skills (string[]),
   tools_tech { programming_languages[], frontend_technologies[], backend_technologies[], databases_devops[] },
   years_of_experience_key_areas (object of short strings),
   accomplishments_with_metrics (string[]),
   education_certs (string[]), domains (string[]), roles_titles (string[]),
   leadership_collaboration (string[]), location_work_auth (string)

3) Scoring (integer 0-100):
   - Skills/Tools overlap: 40
   - Relevant experience & seniority: 25
   - Responsibilities alignment: 15
   - Education/Certs fit: 10
   - Domain/industry fit: 5
   - Logistics (location/work auth/availability): 5
   Allow partial credit; deduct up to 10 via red_flags. Clamp to [0,100], integer.

4) Explain the score:
   For each bucket, provide 1-3 concise evidence bullets. Cite "JD" or "Resume" and include short quoted fragments (escape quotes).

5) Gaps & Suggestions:
   List missing/weak requirements with 1-2 concrete upskilling steps per gap.

7) Cover letter:
   150-220 words (2-4 short paragraphs), tailored to the role/company.
   Concrete impacts; Start with greeting Hi hiring team from Company and end with Signature, Thanks for Considering my application, On the next line, Best Regards. End with candidate Name on last line. Output coverletter as Markup only.
JSON-safe: escape all " as \\", use \\n for newlines.

STRICT CONTENT RULES (to prevent invalid JSON)
- Do NOT paste raw paragraphs, markdown (**bold**, lists), headings, or multi-line blocks into any array fields.
- Every array element must be a short phrase (<= 140 characters), single line, no line breaks, no asterisks, no bullets.
- If a JD section is long, summarize into short phrases before placing into arrays.
- Do NOT include unrelated job text inside arrays or objects. Keep each value semantically atomic.
- Never invent company/title; use "" if unknown.
- No trailing commas anywhere.

STRICT OUTPUT RULES
- Output exactly the following schema (keys and types). No extra keys.

SCHEMA
```json
{
  "job_analysis": {
    "title": "",
    "company": "",
    "must_have_skills": [],
    "nice_to_have_skills": [],
    "responsibilities": [],
    "years_of_experience": "",
    "education_certifications": "",
    "location_constraints": "",
    "domain_industry_focus": "",
    "tech_stack": [],
    "measurable_kpis": []
  },
  "resume_analysis": {
    "core_skills": [],
    "tools_tech": {
      "programming_languages": [],
      "frontend_technologies": [],
      "backend_technologies": [],
      "databases_devops": []
    },
    "years_of_experience_key_areas": {},
    "accomplishments_with_metrics": [],
    "education_certs": [],
    "domains": [],
    "roles_titles": [],
    "leadership_collaboration": [],
    "location_work_auth": ""
  },
  "match_score": 0,
  "score_explanation": [
    { "category": "Skills/Tools overlap (40 points)", "score": 0, "evidence": [] },
    { "category": "Relevant experience depth & seniority (25 points)", "score": 0, "evidence": [] },
    { "category": "Responsibilities alignment (15 points)", "score": 0, "evidence": [] },
    { "category": "Education/Certs fit (10 points)", "score": 0, "evidence": [] },
    { "category": "Domain/industry fit (5 points)", "score": 0, "evidence": [] },
    { "category": "Logistics (location, work auth, availability) (5 points)", "score": 0, "evidence": [] }
  ],
  "red_flags": [],
  "gaps_and_suggestions": [
    { "gap": "", "suggestion": "" }
  ],
  "cover_letter": ""
}
```
END_OF_JSON"""


class JobAnalyzer:
    async def analyze(
        self,
        company: str,
        job_description: str,
        resume_text: str,
        api_key: Optional[str] = None,
        profile=None,
    ) -> Optional[dict]:
        """Return the structured analysis dict, or None if generation/parse fails."""
        if not resume_text:
            return None

        prompt = (
            PROMPT_TEMPLATE.replace("{{COMPANY}}", company or "")
            .replace("{{JOB_DESCRIPTION}}", (job_description or "")[:8000])
            .replace("{{RESUME}}", (resume_text or "")[:8000])
        )

        raw = await llm_generate(
            prompt,
            system=SYSTEM_INSTRUCTION,
            temperature=0.4,
            max_tokens=4096,
            api_key=api_key or resolve_gemini_api_key(profile),
            json_mode=True,
        )
        if not raw:
            return None
        return self._parse_json(raw)

    @staticmethod
    def _parse_json(raw: str) -> Optional[dict]:
        s = raw
        # Strip ```json / ``` fences.
        s = re.sub(r"`{2,3}(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*`{3}\s*$", "", s)
        # Normalize curly quotes.
        s = s.replace("\u201c", '"').replace("\u201d", '"').replace("\u2019", "'")
        # Cut at END_OF_JSON sentinel.
        end_idx = s.find("END_OF_JSON")
        if end_idx != -1:
            s = s[:end_idx]

        # Extract the first complete {...} object via brace counting.
        start = s.find("{")
        if start < 0:
            return None
        depth = 0
        in_str = False
        esc = False
        end = -1
        for i in range(start, len(s)):
            ch = s[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
        if end < 0:
            return None

        try:
            return json.loads(s[start:end])
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse analysis JSON: %s", exc)
            return None
