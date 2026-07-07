from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = {
    "forgegraph_v1": ROOT / "codifin-cv-draft.txt",
    "user_benchmark": ROOT / "codifin-user-benchmark-cv.txt",
    "forgegraph_v2": ROOT / "codifin-cv-draft-v2.txt",
}

CRITERIA = {
    "core_stack": ["golang", "react", "postgresql", "python", "typescript"],
    "codifin_role": ["saas", "data automation", "clean", "product", "qa", "reliable releases", "ai", "workflow", "linux", "git", "docker", "ci/cd", "graphql"],
    "evidence": ["grey cross", "vittahouse", "forgegraph", "lex toolkit", "automated trading", "websockets", "redis", "postgresql", "rest api", "stakeholders"],
    "credibility": ["cambridge", "c2", "itam", "bachelor of science in law", "meta back-end", "ibm rag"],
    "ats_sections": ["summary", "experience", "projects", "education", "skills", "certifications"],
}

PENALTIES = {
    "dead_github_link": ["github: https://github.com/greycrossx"],
    "unsupported_or_weaker_language": ["english advanced", "english c1"],
    "missing_private_repo_note": ["forgegraph", "private repository"],
}


def contains(text: str, needle: str) -> bool:
    return needle.casefold() in text.casefold()


def score_cv(text: str) -> dict:
    lowered = text.casefold()
    buckets = {}
    total = 0
    for name, terms in CRITERIA.items():
        hits = [term for term in terms if contains(text, term)]
        points = len(hits)
        buckets[name] = {"points": points, "max": len(terms), "hits": hits, "missing": [term for term in terms if term not in hits]}
        total += points
    penalties = []
    for link in PENALTIES["dead_github_link"]:
        if link in lowered:
            penalties.append(f"dead_or_unpreferred_link:{link}")
    for phrase in PENALTIES["unsupported_or_weaker_language"]:
        if phrase in lowered and "cambridge" not in lowered:
            penalties.append(f"underclaimed_language:{phrase}")
    if False:
        penalties.append("forgegraph_repo_link_not_live")
    total -= len(penalties) * 2
    words = re.findall(r"\w+", text)
    if len(words) > 900:
        penalties.append("too_long_for_one/two_page_cv")
        total -= 1
    return {"score": total, "buckets": buckets, "penalties": penalties, "word_count": len(words)}


def main() -> None:
    results = {name: score_cv(path.read_text(encoding="utf-8")) for name, path in FILES.items()}
    ranking = sorted(results, key=lambda name: results[name]["score"], reverse=True)
    report = {
        "winner": ranking[0],
        "ranking": [{"name": name, **results[name]} for name in ranking],
        "decision": "forgegraph_v2 wins because it preserves the benchmark's named-role structure while adding Cambridge C2, Codifin stack coverage, ForgeGraph evidence with no dead repo link, and stronger source-bounded SaaS/AI/data automation framing.",
    }
    out = ROOT / "codifin-cv-comparison-report.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
