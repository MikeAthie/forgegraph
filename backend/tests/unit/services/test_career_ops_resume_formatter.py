from __future__ import annotations

from application.services.career_ops_resume_formatter import render_career_ops_ats_resume


def _tailored_resume(*, sections: list[dict[str, object]] | None = None) -> dict[str, object]:
    resume_sections = sections or [
        {"heading": "SUMMARY", "items": ["Backend engineer building Python APIs and AI workflow systems."]},
        {"heading": "TECHNICAL SKILLS", "items": ["Python", "FastAPI", "PostgreSQL", "RAG"]},
        {
            "heading": "SELECTED EXPERIENCE",
            "items": [
                {"text": "Built production APIs using Python, FastAPI, PostgreSQL, and Redis."},
                {"text": "Delivered RAG and agentic workflow prototypes with observability."},
            ],
        },
        {"heading": "PROJECTS", "items": [{"text": "Created workflow automation prototypes for backend teams."}]},
        {"heading": "EDUCATION", "items": [{"text": "B.S. Computer Science."}]},
    ]
    return {
        "status": "draft",
        "format": "ats_resume_v1",
        "opportunity": {
            "employer_name": "Acme AI",
            "role_title": "Backend Engineer, AI Platform",
            "job_url": "https://jobs.example.test/acme/backend-ai",
        },
        "sections": resume_sections,
        "plain_text": "",
        "claim_source_map": [
            {"claim": "Built production APIs using Python, FastAPI, PostgreSQL, and Redis.", "source_ref": {"type": "cv_proof_point", "index": 0}}
        ],
        "quality": {"external_side_effects_allowed": False},
    }


def test_render_ats_resume_text_preserves_standard_section_order() -> None:
    artifacts = render_career_ops_ats_resume(
        tailored_resume=_tailored_resume(),
        candidate_identity={"name": "Miguel Athie", "title": "Backend Engineer"},
    )

    text = artifacts.text
    positions = [text.index(heading) for heading in ("SUMMARY", "TECHNICAL SKILLS", "SELECTED EXPERIENCE", "PROJECTS", "EDUCATION")]
    assert positions == sorted(positions)
    assert "MIGUEL ATHIE" in text
    assert "Backend Engineer" in text
    assert "Built production APIs using Python" in text
    assert "source_ref" not in text
    assert "metadata_json" not in text
    assert "ForgeGraph" not in text


def test_render_ats_resume_html_uses_semantic_single_column_markup() -> None:
    artifacts = render_career_ops_ats_resume(tailored_resume=_tailored_resume())

    html = artifacts.html
    lower = html.casefold()
    assert "<h1" in lower
    assert "<section" in lower
    assert "<h2" in lower
    assert "<ul" in lower
    assert "<li" in lower
    assert "TECHNICAL SKILLS" in html
    for forbidden in ("<table", "<img", "<svg", "<canvas", "display:none", "visibility:hidden", "grid-template", "column-count"):
        assert forbidden not in lower


def test_render_ats_resume_pdf_has_valid_pdf_bytes_and_expected_text_hash() -> None:
    artifacts = render_career_ops_ats_resume(tailored_resume=_tailored_resume())

    assert artifacts.pdf_bytes.startswith(b"%PDF-")
    assert artifacts.pdf_bytes.rstrip().endswith(b"%%EOF")
    report = artifacts.parseability_report
    assert report["status"] == "passed"
    assert report["checks"]["pdf_bytes_valid"] == "pass"
    assert report["checks"]["expected_text_embedded"] == "pass"
    assert report["expected_text_sha256"]
    assert report["external_side_effects_allowed"] is False


def test_render_ats_resume_uses_professional_template_without_ats_hostile_layout() -> None:
    artifacts = render_career_ops_ats_resume(
        tailored_resume=_tailored_resume(),
        candidate_identity={
            "name": "Miguel Athie",
            "title": "Backend Software Engineer",
            "location": "Mexico / Spain / EU Remote",
            "education": [
                {
                    "institution": "Instituto Tecnológico Autónomo de México (ITAM)",
                    "degree": "BSc in Law",
                    "graduation_year": "2017",
                    "location": "Mexico City, Mexico",
                }
            ],
        },
    )

    assert "MIGUEL ATHIE" in artifacts.text
    assert "Backend Software Engineer" in artifacts.text
    assert "Mexico / Spain / EU Remote" in artifacts.text
    assert "Instituto Tecnológico Autónomo de México (ITAM)" in artifacts.text
    assert "BSc in Law" in artifacts.text
    assert "2017" in artifacts.text
    assert "Not provided in source CV" not in artifacts.text
    assert "/Helvetica-Bold" in artifacts.pdf_bytes.decode("latin-1")
    pdf_text_layer = artifacts.pdf_bytes.decode("latin-1")
    assert "Tecnologico Autonomo de Mexico" in pdf_text_layer
    assert "BSc in Law" in pdf_text_layer
    assert artifacts.parseability_report["checks"]["single_column_policy"] == "pass"
    assert artifacts.parseability_report["checks"]["professional_template"] == "pass"


def test_render_ats_resume_education_from_candidate_identity_replaces_placeholder() -> None:
    sections = [
        section
        for section in _tailored_resume()["sections"]
        if section["heading"] != "EDUCATION"
    ]

    artifacts = render_career_ops_ats_resume(
        tailored_resume=_tailored_resume(sections=sections),
        candidate_identity={
            "education": [
                {
                    "institution": "ITAM",
                    "degree": "BSc in Law",
                    "graduation_year": "2017",
                }
            ]
        },
    )

    assert "ITAM" in artifacts.text
    assert "BSc in Law" in artifacts.text
    assert artifacts.parseability_report["status"] == "passed"
    assert artifacts.parseability_report["checks"]["required_sections_present"] == "pass"


def test_render_ats_resume_includes_candidate_certifications() -> None:
    artifacts = render_career_ops_ats_resume(
        tailored_resume=_tailored_resume(),
        candidate_identity={
            "certifications": [
                "Cambridge English C2 Proficiency certificate",
                "Meta Back-End Developer Professional Certificate",
                "IBM RAG and Agentic AI Professional Certificate",
            ]
        },
    )

    assert "CERTIFICATIONS" in artifacts.text
    assert "Cambridge English C2 Proficiency certificate" in artifacts.text
    assert "Meta Back-End Developer Professional Certificate" in artifacts.text
    assert "IBM RAG and Agentic AI Professional Certificate" in artifacts.text
    pdf_text_layer = artifacts.pdf_bytes.decode("latin-1")
    assert "Cambridge English C2 Proficiency certificate" in pdf_text_layer


def test_validate_ats_resume_parseability_blocks_missing_section() -> None:
    sections = [section for section in _tailored_resume()["sections"] if section["heading"] != "EDUCATION"]

    artifacts = render_career_ops_ats_resume(tailored_resume=_tailored_resume(sections=sections))

    report = artifacts.parseability_report
    assert report["status"] == "blocked"
    assert report["checks"]["required_sections_present"] == "blocked"
    assert "missing_section:EDUCATION" in report["blockers"]


def test_validate_ats_resume_parseability_allows_source_backed_project_terms() -> None:
    resume = _tailored_resume()
    resume["sections"][3]["items"] = [
        "Forgegraph — AI-native backend platform using prompt/workflow design for agentic workflows."
    ]

    artifacts = render_career_ops_ats_resume(tailored_resume=resume)

    report = artifacts.parseability_report
    assert report["status"] == "passed"
    assert report["checks"]["no_internal_leakage"] == "pass"


def test_validate_ats_resume_parseability_blocks_internal_leakage() -> None:
    resume = _tailored_resume()
    resume["sections"][0]["items"] = ["Generated from metadata_json prompt inside ForgeGraph."]

    artifacts = render_career_ops_ats_resume(tailored_resume=resume)

    report = artifacts.parseability_report
    assert report["status"] == "blocked"
    assert report["checks"]["no_internal_leakage"] == "blocked"
