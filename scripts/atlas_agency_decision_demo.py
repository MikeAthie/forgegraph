#!/usr/bin/env python
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_API_BASE = "http://127.0.0.1:8000/api"
DEFAULT_OUTPUT_JSON = ROOT / "frontend" / "test-results" / "atlas-agency-decision-system.json"
DEFAULT_OUTPUT_MD = ROOT / "frontend" / "test-results" / "atlas-agency-decision-system.md"
DEFAULT_DOCKER_LLM_BASE_URL = "http://localhost:12434/engines/v1"
DEFAULT_DOCKER_LLM_MODEL = "docker.io/ai/llama3.1:latest"

COMPANY_NAME = "Atlas Growth Agency OS"
COMPANY_TYPE = "digital marketing agency"
COMPANY_OBJECTIVE = "Design and execute high-quality marketing strategies for clients"
CLIENT_CONTEXT = {
    "name": "Legacy",
    "industry": "Luxury glasses",
    "market": "Mexico City",
    "goal": "Launch a luxury glasses brand in Mexico City",
}

SWITCHING_ALTERNATIVES = ["boutique", "optician", "buying_abroad", "doing_nothing"]
TRADEOFF_PRESSURES = ["scale_vs_control", "brand_vs_performance", "awareness_vs_conversion"]
BEHAVIORAL_ACTION_TERMS = [
    "appointment",
    "booked",
    "request",
    "qualified",
    "show-up",
    "show up",
    "referral",
    "conversion",
    "deposit",
    "consult",
    "fitting",
]
PERFORMANCE_METRIC_CATALOG = [
    "qualified appointment request rate",
    "booked fitting rate",
    "show-up rate",
    "referral qualification rate",
    "consult-to-purchase intent",
    "deposit intent rate",
    "cost per qualified fitting",
]
WEAK_LANGUAGE_EXAMPLES = [
    "premium",
    "high-quality",
    "luxury experience",
    "generic luxury",
]
DISALLOWED_PRIMARY_METRICS = [
    "survey",
    "surveys",
    "focus group",
    "focus groups",
    "awareness",
    "reach",
    "impressions",
    "traffic",
    "engagement",
    "market share",
    "market presence",
    "customer base",
    "loyal customer",
    "sales growth",
    "sales",
    "revenue",
    "satisfaction",
]
WEAK_POSITIONING_LABELS = [
    "luxury brand",
    "luxury glasses brand",
    "high-end alternative",
    "fashion-forward alternative",
    "premium eyewear",
    "unique, authentic luxury brand",
    "unique authentic luxury brand",
    "positioning as a luxury brand",
]

PROTOCOL_FIELDS = {
    "type": "proposal | critique | decision",
    "department": "string",
    "content": "string",
    "reasoning": "string",
    "alternatives": ["string"],
    "constraints": {
        "brand": "string",
        "legal": "string",
        "performance": "string",
    },
    "evaluates": ["proposal or critique id/name"],
    "rejections": [
        {
            "option": "string",
            "classification": "hard_constraint | strategic_conflict | tactical_misalignment",
            "reason": "string",
        }
    ],
    "predicted_outcomes": [
        {
            "scenario": "string",
            "expected_result": "string",
            "reasoning": "string",
        }
    ],
    "behavioral_metrics": [
        {
            "conversion_action": "string",
            "measurable_signal": "string",
            "success_threshold": "string",
        }
    ],
    "irreversibility": {
        "reversible": ["string"],
        "irreversible": ["string"],
    },
    "confidence": {
        "level": "low | medium | high",
        "key_uncertainties": ["string"],
        "biggest_risk": "string",
    },
    "decision_payload": "strategy_decision | null",
}

INTERACTION_RULES = [
    "Strategy defines category, competitive alternatives, differentiated value, and constraints before concepts or copy.",
    "Strategy must define concrete switching logic from boutiques, opticians, buying abroad, and doing nothing.",
    "Creative and Copywriting propose in parallel against Strategy direction; neither department can define final positioning.",
    "Legal and Performance critique independently and return constraints, risks, and compliant or measurable alternatives.",
    "Strategy must evaluate all proposals, critiques, and constraints before accepting, rejecting, or requesting revision.",
    "Strategy selects among department work and defines execution plus test criteria; it must not repair every weak input.",
    "At least one viable option must be rejected in every final Strategy decision.",
    "At least one rejection must involve a real pressure: scale vs control, brand vs performance, or awareness vs conversion.",
    "Performance must forecast likely outcomes and failure modes, not only challenge assumptions.",
    "Performance must define behavioral metrics with conversion action, measurable signal, and success threshold.",
    "Experiments must use behavioral conversion signals, not surveys, focus groups, awareness, sales growth, or satisfaction alone.",
    "Strategy must prioritize irreversible decisions before reversible tests.",
    "A decision is invalid if it accepts every proposal, ignores constraints, or turns execution into a disconnected channel list.",
]

REJECTION_RULES = [
    "Reject vague positioning that does not name the competitive alternative or category.",
    "Reject positioning that is only a label such as luxury brand, high-end, premium, or fashion-forward.",
    "Reject proposals that lack credible, provable differentiated value.",
    "Reject claims that cannot be substantiated or safely modified by Legal.",
    "Reject options that dilute luxury positioning through cheap scale, discounting, or mass-market signals.",
    "Reject execution plans that are only a list of channels without an operating logic.",
    "Reject work that cannot be measured through a clear hypothesis, test design, and success metrics.",
    "Reject experiments based on surveys, focus groups, awareness, sales growth, or satisfaction unless tied to a measurable user action.",
    "Classify every rejection as hard_constraint, strategic_conflict, or tactical_misalignment.",
]

STRATEGY_DECISION_SCHEMA = {
    "strategy_decision": {
        "competitive_frame": "",
        "demand_situation": "",
        "chosen_position": "",
        "switching_logic": {
            "boutique": "",
            "optician": "",
            "buying_abroad": "",
            "doing_nothing": "",
        },
        "differentiated_value": "",
        "constraints_applied": {
            "brand": "",
            "legal": "",
            "performance": "",
        },
        "tradeoffs": {
            "chosen": "",
            "rejected": [{"option": "", "classification": "", "reason": ""}],
        },
        "tradeoff_pressure": {
            "scale_vs_control": "",
            "brand_vs_performance": "",
            "awareness_vs_conversion": "",
        },
        "constraint_hierarchy": {
            "hard_constraint": [{"constraint": "", "implication": ""}],
            "strategic_conflict": [{"constraint": "", "implication": ""}],
            "tactical_misalignment": [{"constraint": "", "implication": ""}],
        },
        "material_constraint_change": {
            "constraint": "",
            "changed_decision": "",
            "rejected_default": "",
            "why_material": "",
        },
        "execution_policy": {
            "approach": "",
            "channels": [],
            "constraints": [],
        },
        "experiment_plan": {
            "hypothesis": "",
            "test_design": "",
            "success_metrics": [],
            "behavioral_metrics": [
                {
                    "conversion_action": "",
                    "measurable_signal": "",
                    "success_threshold": "",
                }
            ],
        },
        "decision_irreversibility": {
            "reversible": [{"decision": "", "reason": ""}],
            "irreversible": [{"decision": "", "reason": ""}],
            "prioritization": "",
        },
        "confidence": {
            "level": "",
            "key_uncertainties": [],
            "biggest_risk": "",
        },
        "final_decision": "",
    }
}

RESEARCH_PRINCIPLES = [
    {
        "source": "GTM 80/20 positioning framework",
        "url": "https://www.gtm8020.com/blog/create-product-positioning-framework",
        "principle": (
            "Positioning starts with real competitive alternatives, differentiated value, target fit, and category choice; "
            "messaging follows positioning."
        ),
    },
    {
        "source": "LICERA Strategy 101: The Anatomy of a Choice",
        "url": "https://licerainc.com/51194/strategy-101-the-anatomy-of-a-choice-strategic-fundamentals/",
        "principle": (
            "Strategy is a coherent set of choices protected by tradeoffs, guided policy, and aligned action."
        ),
    },
]


class ApiError(RuntimeError):
    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self.payload = payload
        super().__init__(f"API request failed with status {status}: {json.dumps(payload)[:800]}")


@dataclass(frozen=True)
class Department:
    id: str
    name: str
    responsibility: str
    system_prompt: str


@dataclass(frozen=True)
class AgencyMessage:
    type: str
    department: str
    content: str
    reasoning: str
    alternatives: list[str]
    constraints: dict[str, str] | None = None
    evaluates: list[str] | None = None
    rejections: list[dict[str, str]] | None = None
    predicted_outcomes: list[dict[str, str]] | None = None
    behavioral_metrics: list[dict[str, str]] | None = None
    irreversibility: dict[str, list[str]] | None = None
    confidence: dict[str, Any] | None = None
    decision_payload: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "type": self.type,
            "department": self.department,
            "content": self.content,
            "reasoning": self.reasoning,
            "alternatives": self.alternatives,
            "constraints": self.constraints or {},
            "evaluates": self.evaluates or [],
            "rejections": self.rejections or [],
            "predicted_outcomes": self.predicted_outcomes or [],
            "behavioral_metrics": self.behavioral_metrics or [],
        }
        if self.irreversibility is not None:
            payload["irreversibility"] = self.irreversibility
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        if self.decision_payload is not None:
            payload["decision_payload"] = self.decision_payload
        return payload


DEPARTMENTS = [
    Department(
        id="dept_strategy",
        name="Strategy",
        responsibility=(
            "Sets category, competitive alternatives, differentiated value, constraints, tradeoffs, revisions, "
            "and final decisions."
        ),
        system_prompt=(
            "You are Strategy. Define the competitive frame, behavioral demand situation, position, differentiated value, "
            "tradeoffs, execution policy, test plan, decision irreversibility, and confidence. Compare department inputs, "
            "choose the strongest option, reject weak or misaligned options, and classify rejections. Do not rewrite every "
            "department output into a new idea; Strategy selects, rejects, and defines execution plus test criteria."
        ),
    ),
    Department(
        id="dept_creative_specialist",
        name="Creative Specialist",
        responsibility="Generates distinct brand concepts within Strategy's position and revises them after critique.",
        system_prompt=(
            "You are Creative Specialist. Generate two or three distinct concepts, not small variations. "
            "Work inside Strategy's category and constraints; do not define final positioning. For each concept, state "
            "concept logic, why it works, and what it sacrifices. Reject generic luxury branding or concepts that lack "
            "differentiation."
        ),
    ),
    Department(
        id="dept_copywriting",
        name="Copywriting",
        responsibility="Turns approved strategic position and concepts into concise campaign messaging options.",
        system_prompt=(
            "You are Copywriting. Convert Strategy's position and Creative concepts into messaging options. "
            "Do not invent the category, positioning, or strategic direction. If positioning is unclear, flag it rather "
            "than filling the gap. Avoid generic luxury language; phrases such as premium, high-quality, or luxury "
            "experience are invalid unless tied to a specific proof point, service behavior, or buyer action. Avoid claims "
            "that cannot be substantiated."
        ),
    ),
    Department(
        id="dept_legal",
        name="Legal",
        responsibility="Reviews claims, privacy, disclosures, and compliant alternatives.",
        system_prompt=(
            "You are Legal. Flag risky claims, reject non-compliant language, identify proof requirements, "
            "and propose compliant alternatives. Do not only reject; provide safe replacement language or execution "
            "conditions for every issue you flag."
        ),
    ),
    Department(
        id="dept_performance",
        name="Performance",
        responsibility="Challenges assumptions, expected outcomes, channel fit, measurement, and test design.",
        system_prompt=(
            "You are Performance. Challenge optimistic assumptions, require measurable demand signals, "
            "predict likely outcomes and failure modes with causal reasoning, reject disconnected channel lists, and define "
            "tests before scale. Act as a predictive critic: each forecast must explain 'this will fail/work because "
            "X -> Y -> Z', where X is the assumption, Y is the mechanism, and Z is the expected buyer behavior. Define "
            "behavioral metrics with conversion action, measurable signal, and success threshold. Reject awareness, reach, "
            "traffic, engagement, market share, sales, revenue, satisfaction, and surveys as primary validation. Use behavioral "
            "outcomes such as qualified appointment requests, booked fittings, show-up rate, referral quality, "
            "consult-to-purchase intent, deposit intent, or cost per qualified fitting. Choose measurable_signal values from "
            "the approved behavioral metric catalog only."
        ),
    ),
]


class ForgeGraphClient:
    def __init__(self, api_base: str) -> None:
        self.api_base = api_base.rstrip("/")
        self.access_token = ""

    def login(self, email: str, password: str) -> None:
        payload = self.request(
            "POST",
            "/auth/login",
            {"email": email, "password": password},
            auth=False,
            unwrap=False,
        )
        token = str(payload.get("access") or "").strip()
        if not token:
            raise RuntimeError("Login succeeded but no access token was returned.")
        self.access_token = token

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        auth: bool = True,
        unwrap: bool = True,
        query: dict[str, str] | None = None,
    ) -> Any:
        body = None
        headers = {"Content-Type": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {self.access_token}"
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        suffix = path
        if query:
            suffix = f"{suffix}?{urlencode(query)}"
        url = f"{self.api_base}{suffix}"
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read()
                data = json.loads(raw.decode("utf-8")) if raw else {}
        except HTTPError as exc:
            raw = exc.read()
            try:
                data = json.loads(raw.decode("utf-8")) if raw else {}
            except json.JSONDecodeError:
                data = {"detail": raw.decode("utf-8", errors="replace")}
            raise ApiError(exc.code, data) from exc
        except URLError as exc:
            raise RuntimeError(f"Could not reach ForgeGraph API at {self.api_base}: {exc}") from exc
        return data.get("data") if unwrap and isinstance(data, dict) and "data" in data else data

    def create_company(self, graph_json: dict[str, Any]) -> dict[str, Any]:
        digest = hashlib.sha256(json.dumps(graph_json, sort_keys=True).encode()).hexdigest()[:12]
        return self.request(
            "POST",
            "/graphs/external-workflows",
            {
                "name": COMPANY_NAME,
                "description": COMPANY_OBJECTIVE,
                "external_source": "codex-agency-decision-demo",
                "external_ref": "atlas-growth-agency-os",
                "idempotency_key": f"atlas-growth-agency-os:{digest}",
                "strict": False,
                "require_entry_exit": False,
                "graph_json": graph_json,
            },
        )

    def start_operation(self, graph_version_id: str) -> dict[str, Any]:
        input_json = {
            "company_name": COMPANY_NAME,
            "company_type": COMPANY_TYPE,
            "objective": COMPANY_OBJECTIVE,
            "operation_name": "Legacy Mexico City Launch Decision Loop",
            "operation_brief": CLIENT_CONTEXT["goal"],
            "client_context": CLIENT_CONTEXT,
            "interaction_protocol": PROTOCOL_FIELDS,
            "interaction_rules": INTERACTION_RULES,
            "rejection_rules": REJECTION_RULES,
            "strategy_decision_schema": STRATEGY_DECISION_SCHEMA,
            "departments": [department.name for department in DEPARTMENTS],
        }
        try:
            return self.request(
                "POST",
                "/runs/start",
                {
                    "graph_version_id": graph_version_id,
                    "llm_mode": "managed",
                    "provider": "openai",
                    "input_json": input_json,
                },
            )
        except ApiError as exc:
            if not _is_engine_unavailable(exc.payload):
                raise
            runs = self.request(
                "GET",
                "/runs",
                query={"graph_version_id": graph_version_id},
            )
            if not isinstance(runs, list) or not runs:
                raise
            recovered = runs[0]
            self.post_run_event(
                str(recovered["id"]),
                {
                    "event_type": "run.updated",
                    "run": {
                        "status": "running",
                        "started_at": _iso_now(),
                        "error_message": "",
                    },
                },
            )
            recovered["status"] = "running"
            recovered["recovered_from_engine_unavailable"] = True
            return recovered

    def cancel_run(self, run_id: str) -> dict[str, Any] | None:
        try:
            return self.request("POST", f"/runs/{run_id}/cancel")
        except ApiError as exc:
            if exc.status == 400 and "cannot cancel" in json.dumps(exc.payload).lower():
                return None
            raise

    def post_run_event(self, run_id: str, event: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", f"/runs/{run_id}/events", event)

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self.request("GET", f"/runs/{run_id}")

    def list_agents(self) -> list[dict[str, Any]]:
        data = self.request("GET", "/agents/")
        return data if isinstance(data, list) else []

    def list_tasks(self) -> list[dict[str, Any]]:
        data = self.request("GET", "/tasks/")
        return data if isinstance(data, list) else []

    def generate_strategy_report(self, company_id: str, operation_id: str) -> dict[str, Any] | None:
        try:
            return self.request(
                "POST",
                "/reports/strategy-report",
                {
                    "company_id": company_id,
                    "operation_id": operation_id,
                    "audience": "client",
                    "format": "md",
                },
            )
        except ApiError:
            return None


class DockerModelRunnerClient:
    def __init__(
        self,
        base_url: str = DEFAULT_DOCKER_LLM_BASE_URL,
        model: str = DEFAULT_DOCKER_LLM_MODEL,
        timeout_seconds: int = 120,
    ) -> None:
        self.base_url = _normalize_openai_base_url(base_url)
        self.model = model.strip() or DEFAULT_DOCKER_LLM_MODEL
        self.timeout_seconds = timeout_seconds
        self.call_count = 0
        self.json_repair_count = 0
        self.response_format_supported: bool | None = None

    def list_models(self) -> list[str]:
        payload = self._request("GET", "/models")
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            return []
        models = []
        for item in data:
            if isinstance(item, dict) and str(item.get("id") or "").strip():
                models.append(str(item["id"]).strip())
        return models

    def resolve_model(self) -> str:
        models = self.list_models()
        if self.model in models:
            return self.model
        if self.model == DEFAULT_DOCKER_LLM_MODEL and models:
            self.model = models[0]
            return self.model
        if not models:
            raise RuntimeError(
                f"Docker Model Runner is reachable at {self.base_url}, but no models were listed."
            )
        raise RuntimeError(
            f"Docker Model Runner model '{self.model}' is not available. Available models: {', '.join(models)}"
        )

    def chat_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1600,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        response = self._chat_with_optional_json_format(payload)
        self.call_count += 1
        content = _chat_completion_content(response)
        try:
            return _extract_json_object(content)
        except RuntimeError:
            repaired = self._repair_json_response(
                raw_content=content,
                original_system_prompt=system_prompt,
                original_user_prompt=user_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return _extract_json_object(repaired)

    def _repair_json_response(
        self,
        *,
        raw_content: str,
        original_system_prompt: str,
        original_user_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        repair_payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You repair malformed JSON responses. Return exactly one valid JSON object and no markdown."
                    ),
                },
                {
                    "role": "user",
                    "content": "\n".join(
                        [
                            "The previous local model response was not valid JSON.",
                            "Repair it into one complete JSON object that satisfies the original task.",
                            "",
                            "Original system prompt:",
                            original_system_prompt,
                            "",
                            "Original user prompt:",
                            original_user_prompt,
                            "",
                            "Malformed response:",
                            raw_content[:6000],
                        ]
                    ),
                },
            ],
            "temperature": min(temperature, 0.1),
            "max_tokens": max(max_tokens, 2400),
        }
        response = self._chat_with_optional_json_format(repair_payload)
        self.call_count += 1
        self.json_repair_count += 1
        return _chat_completion_content(response)

    def _chat_with_optional_json_format(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.response_format_supported is False:
            return self._request("POST", "/chat/completions", payload)
        with_response_format = dict(payload)
        with_response_format["response_format"] = {"type": "json_object"}
        try:
            response = self._request("POST", "/chat/completions", with_response_format)
            self.response_format_supported = True
            return response
        except ApiError as exc:
            if exc.status not in {400, 404, 422}:
                raise
            self.response_format_supported = False
            return self._request("POST", "/chat/completions", payload)

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except HTTPError as exc:
            raw = exc.read()
            try:
                data = json.loads(raw.decode("utf-8")) if raw else {}
            except json.JSONDecodeError:
                data = {"detail": raw.decode("utf-8", errors="replace")}
            raise ApiError(exc.code, data) from exc
        except URLError as exc:
            raise RuntimeError(
                f"Could not reach Docker Model Runner at {self.base_url}: {exc}. "
                "Enable Docker Model Runner TCP support and make sure a model is available."
            ) from exc


def _normalize_openai_base_url(base_url: str) -> str:
    value = (base_url or DEFAULT_DOCKER_LLM_BASE_URL).strip().rstrip("/")
    if value.endswith("/chat/completions"):
        value = value[: -len("/chat/completions")]
    return value


def _chat_completion_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError(f"Docker Model Runner response missing choices: {json.dumps(response)[:800]}")
    first = choices[0]
    if not isinstance(first, dict):
        raise RuntimeError(f"Docker Model Runner choice has unexpected shape: {json.dumps(first)[:800]}")
    message_payload = first.get("message")
    if isinstance(message_payload, dict):
        content = message_payload.get("content")
        if isinstance(content, str) and content.strip():
            return content
    text = first.get("text")
    if isinstance(text, str) and text.strip():
        return text
    raise RuntimeError(f"Docker Model Runner response missing message content: {json.dumps(response)[:800]}")


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = _strip_markdown_fence(text.strip())
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    candidate = _balanced_json_object(cleaned)
    if candidate:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"LLM returned invalid JSON object: {exc}; raw={text[:1200]}") from exc
    raise RuntimeError(f"LLM returned no JSON object: {text[:1200]}")


def _strip_markdown_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _balanced_json_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        return ""
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return ""


def _iso_now(offset_seconds: int = 0) -> str:
    value = datetime.now(UTC) + timedelta(seconds=offset_seconds)
    return value.isoformat().replace("+00:00", "Z")


def _is_engine_unavailable(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    text = json.dumps(payload).lower()
    return "engine_unavailable" in text or "engine connection failed" in text


def build_department_prompt(department: Department) -> str:
    lines = [
        department.system_prompt,
        f"Company: {COMPANY_NAME}",
        f"Objective: {COMPANY_OBJECTIVE}",
        f"Responsibility: {department.responsibility}",
        "Interaction rules:",
        *[f"- {rule}" for rule in INTERACTION_RULES],
        "Rejection rules:",
        *[f"- {rule}" for rule in REJECTION_RULES],
        "Use only this JSON message format:",
        json.dumps(PROTOCOL_FIELDS, separators=(",", ":")),
    ]
    if department.name == "Strategy":
        lines.extend(
            [
                "Strategy final decisions must include this structured payload:",
                json.dumps(STRATEGY_DECISION_SCHEMA, separators=(",", ":")),
            ]
        )
    return "\n".join(lines)


def build_company_graph_json(llm_model: str = DEFAULT_DOCKER_LLM_MODEL) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    positions: dict[str, dict[str, int]] = {}
    for index, department in enumerate(DEPARTMENTS):
        nodes.append(
            {
                "id": department.id,
                "type": "agent",
                "name": department.name,
                "config": {
                    "role": department.name,
                    "job_description": department.responsibility,
                    "system_prompt": department.system_prompt,
                    "instructions": build_department_prompt(department),
                    "output_protocol": PROTOCOL_FIELDS,
                    "provider": "openai",
                    "model": llm_model,
                    "temperature": 0.2,
                    "tools": [],
                    "max_steps": 1,
                },
            }
        )
        positions[department.id] = {"x": 120 + (index % 3) * 260, "y": 120 + (index // 3) * 180}

    nodes.append(
        {
            "id": "final_strategy_direction",
            "type": "output",
            "name": "Final Strategy Direction",
            "config": {
                "output_mapping": {
                    "final_decision": "run.output_json.strategy_decision",
                    "decision_messages": "run.output_json.strategy_decisions",
                    "client": "input.client_context.name",
                }
            },
        }
    )
    positions["final_strategy_direction"] = {"x": 460, "y": 500}

    edges = [
        {"id": "start-strategy", "from": "START", "to": "dept_strategy"},
        {"id": "strategy-to-creative", "from": "dept_strategy", "to": "dept_creative_specialist"},
        {"id": "strategy-to-copy", "from": "dept_strategy", "to": "dept_copywriting"},
        {"id": "creative-to-legal", "from": "dept_creative_specialist", "to": "dept_legal"},
        {"id": "copy-to-legal", "from": "dept_copywriting", "to": "dept_legal"},
        {"id": "creative-to-performance", "from": "dept_creative_specialist", "to": "dept_performance"},
        {"id": "copy-to-performance", "from": "dept_copywriting", "to": "dept_performance"},
        {"id": "legal-back-to-strategy", "from": "dept_legal", "to": "dept_strategy"},
        {"id": "performance-back-to-strategy", "from": "dept_performance", "to": "dept_strategy"},
        {"id": "strategy-to-final", "from": "dept_strategy", "to": "final_strategy_direction"},
        {"id": "final-to-end", "from": "final_strategy_direction", "to": "END"},
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "metadata": {
            "name": COMPANY_NAME,
            "description": COMPANY_OBJECTIVE,
            "allow_cycles": True,
            "system_type": "multi_agent_decision_system",
            "interaction_protocol": PROTOCOL_FIELDS,
            "interaction_rules": INTERACTION_RULES,
            "rejection_rules": REJECTION_RULES,
            "strategy_decision_schema": STRATEGY_DECISION_SCHEMA,
            "research_principles": RESEARCH_PRINCIPLES,
            "company_profile": {
                "schema": "company_workspace.v1",
                "companyName": COMPANY_NAME,
                "companyType": COMPANY_TYPE,
                "objective": COMPANY_OBJECTIVE,
                "autonomyMode": "assisted",
                "aiAccessMode": "managed",
                "intelligenceProvider": "openai",
                "companyStatus": "Decision system ready",
                "departments": [
                    {
                        "id": department.id,
                        "label": department.name,
                        "responsibility": department.responsibility,
                        "tools": [],
                        "category": "department",
                    }
                    for department in DEPARTMENTS
                ],
                "skills": ["concept generation", "messaging", "compliance review", "performance challenge"],
                "client_context": CLIENT_CONTEXT,
            },
            "decision_loop": [
                "Strategy defines competitive frame, category, differentiated value, and constraints",
                "Creative and Copywriting propose options against that direction in parallel",
                "Legal and Performance critique independently with constraints and alternatives",
                "Strategy evaluates all inputs, rejects or requests revision, and resolves conflicts",
                "Strategy makes a coherent, testable selection without relying on repeated downstream repair",
            ],
        },
        "editor_state": {
            "viewport": {"x": 0, "y": 0, "zoom": 1},
            "nodePositions": positions,
        },
    }


def message(
    kind: str,
    department: str,
    content: str,
    reasoning: str,
    alternatives: list[str] | None = None,
    constraints: dict[str, str] | None = None,
    evaluates: list[str] | None = None,
    rejections: list[dict[str, str]] | None = None,
    predicted_outcomes: list[dict[str, str]] | None = None,
    behavioral_metrics: list[dict[str, str]] | None = None,
    irreversibility: dict[str, list[str]] | None = None,
    confidence: dict[str, Any] | None = None,
    decision_payload: dict[str, Any] | None = None,
) -> AgencyMessage:
    if kind not in {"proposal", "critique", "decision"}:
        raise ValueError(f"Invalid message type: {kind}")
    return AgencyMessage(
        type=kind,
        department=department,
        content=content,
        reasoning=reasoning,
        alternatives=alternatives or [],
        constraints=constraints,
        evaluates=evaluates,
        rejections=rejections,
        predicted_outcomes=predicted_outcomes,
        behavioral_metrics=behavioral_metrics,
        irreversibility=irreversibility,
        confidence=confidence,
        decision_payload=decision_payload,
    )


def build_docker_llm_interaction_loop(
    llm: DockerModelRunnerClient,
) -> dict[str, Any]:
    history: list[dict[str, Any]] = []

    direction = generate_department_message(
        llm,
        department_name="Strategy",
        kind="decision",
        turn_name="initial_strategy_direction",
        task=(
            "Set the initial strategic direction. Define competitive alternatives, category, behavioral demand situation, "
            "brand/legal/performance constraints, and at least one rejected path. Do not generate concepts."
        ),
        history=history,
    )
    history.append(direction)

    creative_initial = generate_department_message(
        llm,
        department_name="Creative Specialist",
        kind="proposal",
        turn_name="creative_initial_options",
        task=(
            "Propose 2-3 distinct creative concepts inside Strategy's direction. They must be meaningfully different, "
            "not variants of the same idea. For each concept, define concept logic, why it works, and what it sacrifices."
        ),
        history=history,
    )
    copy_initial = generate_department_message(
        llm,
        department_name="Copywriting",
        kind="proposal",
        turn_name="copy_initial_messaging",
        task=(
            "Translate Strategy's position and Creative's concepts into messaging options. Do not redefine category or "
            "positioning. Flag any claim that needs substantiation, and do not use premium, high-quality, or luxury "
            "experience unless each phrase has specific proof or service meaning."
        ),
        history=history + [creative_initial],
    )
    history.extend([creative_initial, copy_initial])

    legal_initial = generate_department_message(
        llm,
        department_name="Legal",
        kind="critique",
        turn_name="legal_initial_review",
        task=(
            "Review Strategy, Creative, and Copywriting outputs. Reject or modify risky claims, classify rejections, "
            "and provide compliant alternatives or execution conditions for every flagged issue."
        ),
        history=history,
    )
    performance_initial = generate_department_message(
        llm,
        department_name="Performance",
        kind="critique",
        turn_name="performance_initial_forecast",
        task=(
            "Challenge assumptions and forecast likely outcomes. Predict outcomes for the leading options with reasoning, "
            "identify measurement weaknesses, and require a behavioral conversion test before scale. Use metrics such as "
            "qualified appointment request rate, booked fitting rate, show-up rate, referral quality, consult-to-purchase intent, "
            "deposit intent, or cost per qualified fitting. Define behavioral_metrics with conversion_action, measurable_signal, "
            "and success_threshold. Do not use awareness, reach, traffic, engagement, market share, sales, revenue, or purchase "
            "as Performance validation. Use measurable_signal values from the approved behavioral metric catalog only."
        ),
        history=history + [legal_initial],
    )
    performance_failures = validate_performance_message_quality(performance_initial)
    if performance_failures:
        raise RuntimeError(
            "Performance response for performance_initial_forecast failed hard constraints: "
            + "; ".join(performance_failures)
        )
    history.extend([legal_initial, performance_initial])

    strategy_revision = generate_department_message(
        llm,
        department_name="Strategy",
        kind="decision",
        turn_name="strategy_revision_request",
        task=(
            "Evaluate all proposals, critiques, and constraints. Request a revision, explicitly reject at least one viable "
            "alternative, and explain the constraint hierarchy driving the revision."
        ),
        history=history,
    )
    history.append(strategy_revision)

    creative_revision = generate_department_message(
        llm,
        department_name="Creative Specialist",
        kind="proposal",
        turn_name="creative_revision",
        task=(
            "Revise Creative's proposal based on Strategy's revision request, Legal constraints, and Performance forecasts. "
            "Keep distinct roles for lead concept, proof assets, and any secondary assets. For each revised concept, state "
            "logic, why it works, and what it sacrifices."
        ),
        history=history,
    )
    copy_revision = generate_department_message(
        llm,
        department_name="Copywriting",
        kind="proposal",
        turn_name="copy_revision",
        task=(
            "Revise messaging based on Strategy's revision request, Legal constraints, and Performance forecasts. "
            "Keep copy aligned to positioning and one primary action. Do not invent a new position or use vague premium "
            "language without specific proof."
        ),
        history=history + [creative_revision],
    )
    history.extend([creative_revision, copy_revision])

    legal_revision = generate_department_message(
        llm,
        department_name="Legal",
        kind="critique",
        turn_name="legal_revision_review",
        task=(
            "Review the revised creative and copy. Provide conditional clearance or rejection with compliant alternatives. "
            "Classify any remaining rejection as hard_constraint, strategic_conflict, or tactical_misalignment."
        ),
        history=history,
    )
    performance_revision = generate_department_message(
        llm,
        department_name="Performance",
        kind="critique",
        turn_name="performance_revision_forecast",
        task=(
            "Review the revised system and forecast likely outcomes by cell/scenario. Define what should happen before Strategy "
            "allows scale, including user-action success thresholds such as qualified appointment request rate, booked fitting rate, "
            "show-up rate, referral quality, consult-to-purchase intent, deposit intent, or cost per qualified fitting. Return "
            "behavioral_metrics with conversion_action, measurable_signal, and success_threshold. Each forecast must explain "
            "the causal chain from assumption to mechanism to buyer behavior. Use approved behavioral metrics only."
        ),
        history=history + [legal_revision],
    )
    performance_failures = validate_performance_message_quality(performance_revision)
    if performance_failures:
        raise RuntimeError(
            "Performance response for performance_revision_forecast failed hard constraints: "
            + "; ".join(performance_failures)
        )
    history.extend([legal_revision, performance_revision])

    final_decision = generate_department_message(
        llm,
        department_name="Strategy",
        kind="decision",
        turn_name="final_strategy_decision",
        task=(
            "Make the final decision as Strategy. Choose a defensible position, explain why customers switch from real "
            "alternatives, apply the constraint hierarchy, classify all rejections, separate reversible and irreversible "
            "decisions, provide confidence level, key uncertainties, biggest risk, and an experiment plan with behavioral "
            "metrics. Strategy must choose and reject; do not repair every department output."
        ),
        history=history,
        require_strategy_decision=True,
        max_tokens=2600,
    )
    strategy_decision = normalize_strategy_decision(final_decision["decision_payload"]["strategy_decision"])
    quality_failures = validate_strategy_decision_quality(strategy_decision)
    if quality_failures:
        raise RuntimeError(
            "Final Strategy decision failed schema or hard constraints: "
            + "; ".join(quality_failures)
        )

    history.append(final_decision)
    final_decision["decision_payload"] = {"strategy_decision": strategy_decision}
    final_decision["content"] = strategy_decision["final_decision"]
    final_decision["reasoning"] = (
        f"Strategy chose {strategy_decision['chosen_position']} because the switch logic is stronger than generic luxury "
        f"positioning and because the material constraint changed the default path: "
        f"{strategy_decision['material_constraint_change']['changed_decision']}"
    )
    final_decision["rejections"] = strategy_decision["tradeoffs"]["rejected"]
    final_decision["constraints"] = strategy_decision["constraints_applied"]
    final_decision["irreversibility"] = {
        "reversible": [item["decision"] for item in strategy_decision["decision_irreversibility"]["reversible"]],
        "irreversible": [item["decision"] for item in strategy_decision["decision_irreversibility"]["irreversible"]],
    }
    final_decision["confidence"] = strategy_decision["confidence"]

    messages = history
    proposals = [item for item in messages if item["type"] == "proposal"]
    critiques = [item for item in messages if item["type"] == "critique"]
    decisions = [item for item in messages if item["type"] == "decision"]
    return {
        "messages": messages,
        "proposals": proposals,
        "critiques": critiques,
        "decisions": decisions,
        "final_decision": final_decision,
        "strategy_decision": strategy_decision,
        "conflict_resolution": final_decision.get("reasoning", ""),
        "quality_gate": {
            "failures": quality_failures,
            "passed": not quality_failures,
        },
    }


def generate_department_message(
    llm: DockerModelRunnerClient,
    *,
    department_name: str,
    kind: str,
    turn_name: str,
    task: str,
    history: list[dict[str, Any]],
    require_strategy_decision: bool = False,
    max_tokens: int = 1600,
) -> dict[str, Any]:
    department = department_by_name(department_name)
    system_prompt = "\n".join(
        [
            build_department_prompt(department),
            "Return JSON only. Do not wrap the JSON in markdown fences.",
            "Do not ask for external inputs. Use only the provided client context and interaction history.",
            "Keep language concrete, constraint-driven, and specific to Legacy's Mexico City luxury glasses launch.",
            "Weak language examples must be replaced with specific meaning: "
            + ", ".join(WEAK_LANGUAGE_EXAMPLES)
            + ".",
        ]
    )
    response_schema = {
        "type": kind,
        "department": department_name,
        "content": "one concise paragraph with the department output",
        "reasoning": "one concise paragraph explaining why",
        "alternatives": ["2-5 concrete options or alternatives"],
        "constraints": {"brand": "", "legal": "", "performance": ""},
        "evaluates": ["names of prior messages evaluated"],
        "rejections": [
            {
                "option": "",
                "classification": "hard_constraint | strategic_conflict | tactical_misalignment",
                "reason": "",
            }
        ],
        "predicted_outcomes": [
            {
                "scenario": "",
                "expected_result": "",
                "reasoning": "causal chain: assumption -> mechanism -> expected buyer behavior",
            }
        ],
        "behavioral_metrics": [
            {
                "conversion_action": "",
                "measurable_signal": "",
                "success_threshold": "",
            }
        ],
    }
    if require_strategy_decision:
        response_schema["decision_payload"] = STRATEGY_DECISION_SCHEMA
    strategy_quality_rules = ""
    if require_strategy_decision:
        strategy_quality_rules = "\n".join(
            [
                "Strategy quality rules for the final decision:",
                "- differentiated_value must explain why a buyer switches from real alternatives, including boutiques, opticians, buying abroad, and doing nothing.",
                "- do not merely say the value explains switching; write the actual switch logic for each alternative.",
                "- fill switching_logic with one concrete paragraph each for boutique, optician, buying_abroad, and doing_nothing.",
                "- demand_situation must be behavioral; do not describe demographics such as affluent consumers.",
                "- choose the best department option; reject weak options instead of repairing every department output.",
                "- do not choose generic high-end/fashion-forward positioning unless it is made defensible through a specific service or buying context.",
                "- execution_policy must define an operating approach, not a disconnected channel list.",
                "- reject at least one viable direction involving scale vs control, brand vs performance, or awareness vs conversion.",
                "- tradeoff_pressure must explain scale_vs_control, brand_vs_performance, and awareness_vs_conversion.",
                "- material_constraint_change must name a constraint that changed the decision and the default path it rejected.",
                "- execution_policy must include a coherent approach, at least two channels, and operating constraints.",
                "- experiment_plan must include a behavioral hypothesis, test design, and behavioral_metrics.",
                "- each behavioral metric must include conversion_action, measurable_signal, and success_threshold.",
                "- experiments cannot use awareness, sales, satisfaction, or surveys as primary validation.",
                "- decision_irreversibility must include both reversible and irreversible decisions.",
                "- confidence must include level, at least two key uncertainties, and biggest risk.",
            ]
        )
    creative_quality_rules = ""
    if department_name == "Creative Specialist":
        creative_quality_rules = "\n".join(
            [
                "Creative quality rules:",
                "- Propose distinct concepts, not naming or visual variations of one concept.",
                "- Each alternative must include concept logic, why it works, and what it sacrifices.",
                "- Reject generic luxury branding and concepts that do not create a different strategic option for Strategy.",
                "- Do not invent positioning outside Strategy's direction.",
            ]
        )
    copy_quality_rules = ""
    if department_name == "Copywriting":
        copy_quality_rules = "\n".join(
            [
                "Copywriting quality rules:",
                "- Align to Strategy and Creative; do not invent a new position.",
                "- If Strategy direction is unclear, flag the gap in constraints or rejections.",
                "- Do not use premium, high-quality, or luxury experience unless tied to a concrete proof point or buyer action.",
                "- Convert the chosen direction into copy options with one primary action.",
            ]
        )
    legal_quality_rules = ""
    if department_name == "Legal":
        legal_quality_rules = "\n".join(
            [
                "Legal quality rules:",
                "- Flag legal, claim, consent, disclosure, or substantiation issues.",
                "- For every flagged issue, propose safer replacement language or execution conditions.",
                "- Classify hard legal constraints separately from strategic or tactical concerns.",
            ]
        )
    performance_quality_rules = ""
    if department_name == "Performance":
        response_schema["predicted_outcomes"] = [
            {
                "scenario": "option or failure mode being forecast",
                "expected_result": "effect on approved behavioral signals only; no sales, revenue, traffic, reach, awareness, or market share",
                "reasoning": "Assumption -> mechanism -> expected buyer behavior",
            }
        ]
        response_schema["behavioral_metrics"] = [
            {
                "conversion_action": "specific buyer action before purchase",
                "measurable_signal": "one approved metric from the provided catalog",
                "success_threshold": "numeric threshold and time window",
            }
        ]
        performance_quality_rules = "\n".join(
            [
                "Performance quality rules:",
                "- Approved behavioral metric catalog: " + "; ".join(PERFORMANCE_METRIC_CATALOG) + ".",
                "- measurable_signal must use one of the approved catalog metrics, or a stricter variant of one.",
                "- predicted_outcomes must include likely failure modes and why they would happen.",
                "- Each predicted_outcomes.expected_result must name at least one approved behavioral metric from the catalog.",
                "- Each predicted_outcomes.reasoning must use causal-chain reasoning: assumption -> mechanism -> expected buyer behavior.",
                "- Do not forecast success as market share, sales, revenue, traffic, engagement, reach, or impressions.",
                "- If a scenario critiques a disallowed metric, expected_result must name the behavioral metric that would expose the failure.",
                "- behavioral_metrics must include at least three metrics.",
                "- Each behavioral metric must include conversion_action, measurable_signal, and success_threshold.",
                "- Reject awareness, reach, traffic, engagement, market share, sales, revenue, purchases, satisfaction, and surveys as primary validation.",
                "- Use measurable user actions: qualified appointment request, booked fitting, show-up rate, referral quality, consult-to-purchase intent, deposit intent, or cost per qualified fitting.",
                "- Challenge assumptions with causal reasoning, not generic concern language.",
                "- Bad metric: Customer purchases a product / sales revenue. Good replacement: request a private fitting / qualified appointment request rate / at least 6% in six weeks.",
                "- Bad forecast: the brand increases market share. Good replacement: the appointment-led cell clears booked fitting rate and show-up thresholds because the offer resolves taste risk before asking for commitment.",
            ]
        )
    user_prompt = "\n".join(
        [
            f"Turn: {turn_name}",
            f"Required message type: {kind}",
            f"Required department: {department_name}",
            f"Task: {task}",
            "",
            "Client context JSON:",
            json.dumps(CLIENT_CONTEXT, indent=2),
            "",
            "Company objective:",
            COMPANY_OBJECTIVE,
            "",
            "Compact interaction history JSON:",
            json.dumps(compact_history(history), indent=2),
            "",
            "Required response JSON shape:",
            json.dumps(response_schema, indent=2),
            "",
            strategy_quality_rules,
            "",
            creative_quality_rules,
            "",
            copy_quality_rules,
            "",
            legal_quality_rules,
            "",
            performance_quality_rules,
            "",
            "Return exactly one JSON object. Use empty arrays only when the field is not relevant. "
            "For Performance turns, predicted_outcomes and behavioral_metrics must not be empty. "
            "For Strategy final decision, decision_payload.strategy_decision must be complete.",
        ]
    )
    raw = llm.chat_json(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=max_tokens)
    return coerce_agency_message(
        raw,
        expected_type=kind,
        expected_department=department_name,
        require_strategy_decision=require_strategy_decision,
    )


def validate_strategy_decision_quality(strategy_decision: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    differentiated_value = strategy_decision["differentiated_value"].lower()
    demand_situation = strategy_decision["demand_situation"].lower()
    chosen_position = strategy_decision["chosen_position"].lower()
    switching_logic = strategy_decision["switching_logic"]
    rejected = strategy_decision["tradeoffs"]["rejected"]
    tradeoff_pressure = strategy_decision["tradeoff_pressure"]
    hierarchy = strategy_decision["constraint_hierarchy"]
    material_constraint_change = strategy_decision["material_constraint_change"]
    execution = strategy_decision["execution_policy"]
    experiment = strategy_decision["experiment_plan"]
    irreversibility = strategy_decision["decision_irreversibility"]
    confidence = strategy_decision["confidence"]

    if not strategy_decision["competitive_frame"]:
        failures.append("competitive_frame is required")
    if not strategy_decision["final_decision"]:
        failures.append("final_decision is required")
    if not has_complete_switching_logic(switching_logic):
        failures.append("switching_logic must explain why customers switch from boutique, optician, buying abroad, and doing nothing")
    if is_weak_differentiated_value(differentiated_value):
        failures.append("differentiated_value must explain why customers switch from real alternatives")
    if not any(term in demand_situation for term in ["when", "moment", "occasion", "situation"]):
        failures.append("demand_situation must be behavioral, not demographic")
    if is_positioning_label(chosen_position):
        failures.append("chosen_position is too generic to be defensible")
    if not all(strategy_decision["constraints_applied"].values()):
        failures.append("constraints_applied must include brand, legal, and performance constraints")
    if not rejected:
        failures.append("tradeoffs.rejected must include at least one rejected alternative")
    if not has_meaningful_tradeoff(rejected, tradeoff_pressure):
        failures.append("tradeoffs must reject a viable direction involving scale vs control, brand vs performance, or awareness vs conversion")
    classifications = {item["classification"] for item in rejected}
    if not classifications <= {"hard_constraint", "strategic_conflict", "tactical_misalignment"}:
        failures.append("all rejections must use valid constraint hierarchy classifications")
    if not hierarchy["hard_constraint"]:
        failures.append("constraint_hierarchy.hard_constraint must not be empty")
    if not hierarchy["strategic_conflict"]:
        failures.append("constraint_hierarchy.strategic_conflict must not be empty")
    if not hierarchy["tactical_misalignment"]:
        failures.append("constraint_hierarchy.tactical_misalignment must not be empty")
    if not has_material_constraint_change(material_constraint_change):
        failures.append("a material constraint must change the decision and reject a default path")
    if not execution["approach"] or len(execution["channels"]) < 2 or not execution["constraints"]:
        failures.append("execution_policy must include a coherent approach and at least two channels")
    if not is_behavioral_experiment(experiment):
        failures.append("experiment_plan must include behavioral metrics with action, signal, and threshold")
    if not irreversibility["reversible"] or not irreversibility["irreversible"]:
        failures.append("decision_irreversibility must include reversible and irreversible decisions")
    if confidence["level"] not in {"low", "medium", "high"}:
        failures.append("confidence.level must be low, medium, or high")
    if len(confidence["key_uncertainties"]) < 2 or not confidence["biggest_risk"]:
        failures.append("confidence must include at least two key uncertainties and biggest risk")
    return failures


def validate_performance_message_quality(message: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    predicted_outcomes = coerce_predicted_outcomes(message.get("predicted_outcomes"))
    behavioral_metrics = coerce_behavioral_metrics(message.get("behavioral_metrics"))
    if len(predicted_outcomes) < 2:
        failures.append("Performance must predict at least two outcomes or failure modes")
    for index, outcome in enumerate(predicted_outcomes, start=1):
        if not outcome["scenario"] or not outcome["expected_result"] or not outcome["reasoning"]:
            failures.append(f"Performance predicted_outcomes[{index}] must include scenario, expected_result, and reasoning")
        if not contains_any(
            outcome["reasoning"],
            ["because", "if ", "when ", "therefore", "driven by", "caused by", "assumption", "mechanism", "expected buyer behavior", "->"],
        ):
            failures.append(f"Performance predicted_outcomes[{index}].reasoning must explain causality")
    if not any(
        contains_any(
            json.dumps(outcome, sort_keys=True),
            [
                "fail",
                "failure",
                "risk",
                "underperform",
                "weak",
                "dilute",
                "low-quality",
                "decrease",
                "lower",
                "less likely",
                "mistrust",
                "uncertainty",
                "lack",
            ],
        )
        for outcome in predicted_outcomes
    ):
        failures.append("Performance must predict at least one failure mode")
    for index, outcome in enumerate(predicted_outcomes, start=1):
        if contains_disallowed_primary_metric(outcome["expected_result"]):
            failures.append(f"Performance predicted_outcomes[{index}] uses a disallowed primary outcome")
        if not contains_any(outcome["expected_result"], PERFORMANCE_METRIC_CATALOG):
            failures.append(f"Performance predicted_outcomes[{index}] must name an approved behavioral signal")
    if len(behavioral_metrics) < 3:
        failures.append("Performance must define at least three behavioral metrics")
    for index, metric in enumerate(behavioral_metrics, start=1):
        if not metric["conversion_action"] or not metric["measurable_signal"] or not metric["success_threshold"]:
            failures.append(f"Performance behavioral_metrics[{index}] must include conversion_action, measurable_signal, and success_threshold")
        if contains_disallowed_primary_metric(
            f"{metric['conversion_action']} {metric['measurable_signal']} {metric['success_threshold']}"
        ):
            failures.append(f"Performance behavioral_metrics[{index}] uses a disallowed primary metric")
        if not contains_any(metric["measurable_signal"], PERFORMANCE_METRIC_CATALOG):
            failures.append(f"Performance behavioral_metrics[{index}] must use an approved behavioral signal")
    return failures


def contains_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def contains_disallowed_primary_metric(text: str) -> bool:
    lowered = text.lower()
    for term in DISALLOWED_PRIMARY_METRICS:
        pattern = rf"(?<![a-z]){re.escape(term)}(?![a-z])"
        if re.search(pattern, lowered):
            return True
    return False


def is_weak_differentiated_value(value: str) -> bool:
    text = value.lower()
    switch_terms = ["boutique", "optician", "abroad", "doing nothing", "status quo"]
    switch_term_count = sum(1 for term in switch_terms if term in text)
    return (
        switch_term_count < 3
        or not contains_any(text, ["switch", "choose", "instead", "alternative", "from "])
        or len(text) < 180
    )


def is_positioning_label(chosen_position: str) -> bool:
    text = chosen_position.strip().lower()
    if not text:
        return True
    has_context = contains_any(text, ["private", "appointment", "fitting", "service", "concierge", "proof", "occasion"])
    if contains_any(text, WEAK_POSITIONING_LABELS) and not has_context:
        return True
    return len(text.split()) < 5


def has_complete_switching_logic(switching_logic: dict[str, str]) -> bool:
    for key in SWITCHING_ALTERNATIVES:
        value = switching_logic.get(key, "").lower()
        if len(value) < 50:
            return False
        if not contains_any(value, ["switch", "choose", "because", "instead", "alternative"]):
            return False
    return True


def has_meaningful_tradeoff(
    rejected: list[dict[str, str]],
    tradeoff_pressure: dict[str, str],
) -> bool:
    pressure_text = json.dumps(tradeoff_pressure, sort_keys=True).lower()
    rejected_text = json.dumps(rejected, sort_keys=True).lower()
    combined = f"{pressure_text} {rejected_text}"
    if not all(tradeoff_pressure.get(key) for key in TRADEOFF_PRESSURES):
        return False
    if not any(item["option"] and item["reason"] for item in rejected):
        return False
    return contains_any(
        combined,
        ["scale", "control", "brand", "performance", "awareness", "conversion", "legal", "claim", "appointment"],
    )


def has_material_constraint_change(change: dict[str, str]) -> bool:
    text = json.dumps(change, sort_keys=True).lower()
    return (
        bool(change["constraint"])
        and bool(change["changed_decision"])
        and bool(change["rejected_default"])
        and bool(change["why_material"])
        and contains_any(text, ["legal", "brand", "performance", "constraint", "privacy", "claim", "scale", "metric", "appointment", "conversion"])
    )


def is_behavioral_experiment(experiment: dict[str, Any]) -> bool:
    metrics = coerce_behavioral_metrics(experiment.get("behavioral_metrics"))
    success_metrics = [metric.lower() for metric in experiment.get("success_metrics", [])]
    if not experiment["hypothesis"] or not experiment["test_design"]:
        return False
    if metrics:
        return len(metrics) >= 3 and all(
            metric["conversion_action"] and metric["measurable_signal"] and metric["success_threshold"]
            for metric in metrics
        )
    if len(success_metrics) < 3:
        return False
    metric_hits = sum(1 for metric in success_metrics if contains_any(metric, BEHAVIORAL_ACTION_TERMS))
    return metric_hits >= 3


def compact_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for item in history:
        compacted.append(
            {
                "type": item.get("type"),
                "department": item.get("department"),
                "content": coerce_string(item.get("content"))[:500],
                "reasoning": coerce_string(item.get("reasoning"))[:500],
                "alternatives": coerce_string_list(item.get("alternatives"))[:4],
                "rejections": coerce_rejections(item.get("rejections"))[:4],
                "predicted_outcomes": coerce_predicted_outcomes(item.get("predicted_outcomes"))[:3],
                "behavioral_metrics": coerce_behavioral_metrics(item.get("behavioral_metrics"))[:3],
            }
        )
    return compacted


def department_by_name(name: str) -> Department:
    for department in DEPARTMENTS:
        if department.name == name:
            return department
    raise KeyError(f"Unknown department: {name}")


def coerce_agency_message(
    raw: dict[str, Any],
    *,
    expected_type: str,
    expected_department: str,
    require_strategy_decision: bool = False,
) -> dict[str, Any]:
    payload = raw
    for wrapper_key in ("message", "agency_message", "output"):
        wrapped = payload.get(wrapper_key)
        if isinstance(wrapped, dict):
            payload = wrapped
            break
    decision_payload = payload.get("decision_payload")
    if require_strategy_decision:
        if not isinstance(decision_payload, dict):
            strategy_decision = payload.get("strategy_decision")
            if isinstance(strategy_decision, dict):
                decision_payload = {"strategy_decision": strategy_decision}
        if not isinstance(decision_payload, dict) or not isinstance(decision_payload.get("strategy_decision"), dict):
            raise RuntimeError(f"Strategy final response missing decision payload: {json.dumps(raw)[:1200]}")
        decision_payload = {"strategy_decision": normalize_strategy_decision(decision_payload["strategy_decision"])}

    return AgencyMessage(
        type=expected_type,
        department=expected_department,
        content=coerce_string(payload.get("content")),
        reasoning=coerce_string(payload.get("reasoning")),
        alternatives=coerce_string_list(payload.get("alternatives")),
        constraints=coerce_constraints(payload.get("constraints")),
        evaluates=coerce_string_list(payload.get("evaluates")),
        rejections=coerce_rejections(payload.get("rejections")),
        predicted_outcomes=coerce_predicted_outcomes(payload.get("predicted_outcomes")),
        behavioral_metrics=coerce_behavioral_metrics(payload.get("behavioral_metrics")),
        irreversibility=coerce_irreversibility(payload.get("irreversibility")),
        confidence=coerce_confidence(payload.get("confidence")) if isinstance(payload.get("confidence"), dict) else None,
        decision_payload=decision_payload,
    ).as_dict()


def normalize_strategy_decision(raw: dict[str, Any]) -> dict[str, Any]:
    constraints = coerce_constraints(raw.get("constraints_applied"))
    tradeoffs_raw = raw.get("tradeoffs") if isinstance(raw.get("tradeoffs"), dict) else {}
    rejected = coerce_rejections(tradeoffs_raw.get("rejected"))
    switching_logic = normalize_switching_logic(raw.get("switching_logic"))
    hierarchy = normalize_constraint_hierarchy(raw.get("constraint_hierarchy"))
    irreversibility = normalize_decision_irreversibility(raw.get("decision_irreversibility"))
    confidence = coerce_confidence(raw.get("confidence"))
    differentiated_value = coerce_string(raw.get("differentiated_value"))
    final_decision = coerce_string(raw.get("final_decision"))
    decision = {
        "competitive_frame": coerce_string(raw.get("competitive_frame")),
        "demand_situation": coerce_string(raw.get("demand_situation")),
        "chosen_position": coerce_string(raw.get("chosen_position")),
        "switching_logic": switching_logic,
        "differentiated_value": differentiated_value,
        "constraints_applied": constraints,
        "tradeoffs": {
            "chosen": coerce_string(tradeoffs_raw.get("chosen")),
            "rejected": rejected,
        },
        "tradeoff_pressure": normalize_tradeoff_pressure(raw.get("tradeoff_pressure")),
        "constraint_hierarchy": hierarchy,
        "material_constraint_change": normalize_material_constraint_change(raw.get("material_constraint_change")),
        "execution_policy": normalize_execution_policy(raw.get("execution_policy")),
        "experiment_plan": normalize_experiment_plan(raw.get("experiment_plan")),
        "decision_irreversibility": irreversibility,
        "confidence": confidence,
        "final_decision": final_decision,
    }
    return decision


def normalize_switching_logic(raw: Any) -> dict[str, str]:
    source = raw if isinstance(raw, dict) else {}
    return {key: coerce_string(source.get(key)) for key in SWITCHING_ALTERNATIVES}


def normalize_tradeoff_pressure(raw: Any) -> dict[str, str]:
    source = raw if isinstance(raw, dict) else {}
    return {key: coerce_string(source.get(key)) for key in TRADEOFF_PRESSURES}


def normalize_material_constraint_change(raw: Any) -> dict[str, str]:
    source = raw if isinstance(raw, dict) else {}
    return {
        "constraint": coerce_string(source.get("constraint")),
        "changed_decision": coerce_string(source.get("changed_decision")),
        "rejected_default": coerce_string(source.get("rejected_default")),
        "why_material": coerce_string(source.get("why_material")),
    }


def normalize_constraint_hierarchy(raw: Any) -> dict[str, list[dict[str, str]]]:
    source = raw if isinstance(raw, dict) else {}
    return {
        "hard_constraint": coerce_constraint_items(source.get("hard_constraint")),
        "strategic_conflict": coerce_constraint_items(source.get("strategic_conflict")),
        "tactical_misalignment": coerce_constraint_items(source.get("tactical_misalignment")),
    }


def normalize_execution_policy(raw: Any) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    return {
        "approach": coerce_string(source.get("approach")),
        "channels": coerce_string_list(source.get("channels")),
        "constraints": coerce_string_list(source.get("constraints")),
    }


def normalize_experiment_plan(raw: Any) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    return {
        "hypothesis": coerce_string(source.get("hypothesis")),
        "test_design": coerce_string(source.get("test_design")),
        "success_metrics": coerce_string_list(source.get("success_metrics")),
        "behavioral_metrics": coerce_behavioral_metrics(source.get("behavioral_metrics")),
    }


def normalize_decision_irreversibility(raw: Any) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    return {
        "reversible": coerce_decision_items(source.get("reversible")),
        "irreversible": coerce_decision_items(source.get("irreversible")),
        "prioritization": coerce_string(source.get("prioritization")),
    }


def coerce_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [coerce_string(item) for item in value if coerce_string(item)]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return [coerce_string(value)]


def coerce_constraints(value: Any) -> dict[str, str]:
    source = value if isinstance(value, dict) else {}
    return {
        "brand": coerce_string(source.get("brand")),
        "legal": coerce_string(source.get("legal")),
        "performance": coerce_string(source.get("performance")),
    }


def coerce_rejections(value: Any) -> list[dict[str, str]]:
    items = value if isinstance(value, list) else []
    rejections: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, dict):
            option = coerce_string(item.get("option"))
            reason = coerce_string(item.get("reason"))
            classification = normalize_rejection_classification(item.get("classification"), option, reason)
        else:
            option = coerce_string(item)
            reason = ""
            classification = normalize_rejection_classification("", option, reason)
        if option or reason:
            rejections.append({"option": option, "classification": classification, "reason": reason})
    return rejections


def normalize_rejection_classification(raw: Any, option: str, reason: str) -> str:
    value = coerce_string(raw).lower()
    if value in {"hard_constraint", "strategic_conflict", "tactical_misalignment"}:
        return value
    text = f"{option} {reason}".lower()
    if any(term in text for term in ["legal", "compliance", "privacy", "claim", "substantiation", "medical"]):
        return "hard_constraint"
    if any(term in text for term in ["brand", "position", "luxury", "category", "dilute"]):
        return "strategic_conflict"
    return "tactical_misalignment"


def coerce_predicted_outcomes(value: Any) -> list[dict[str, str]]:
    items = value if isinstance(value, list) else []
    outcomes: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        scenario = coerce_string(item.get("scenario"))
        expected_result = coerce_string(item.get("expected_result"))
        reasoning = coerce_string(item.get("reasoning"))
        if scenario or expected_result or reasoning:
            outcomes.append(
                {
                    "scenario": scenario,
                    "expected_result": expected_result,
                    "reasoning": reasoning,
                }
            )
    return outcomes


def coerce_behavioral_metrics(value: Any) -> list[dict[str, str]]:
    items = value if isinstance(value, list) else []
    metrics: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, dict):
            conversion_action = coerce_string(item.get("conversion_action"))
            measurable_signal = coerce_string(item.get("measurable_signal"))
            success_threshold = coerce_string(item.get("success_threshold"))
        else:
            conversion_action = coerce_string(item)
            measurable_signal = ""
            success_threshold = ""
        if conversion_action or measurable_signal or success_threshold:
            metrics.append(
                {
                    "conversion_action": conversion_action,
                    "measurable_signal": measurable_signal,
                    "success_threshold": success_threshold,
                }
            )
    return metrics


def coerce_irreversibility(value: Any) -> dict[str, list[str]] | None:
    if not isinstance(value, dict):
        return None
    return {
        "reversible": coerce_string_list(value.get("reversible")),
        "irreversible": coerce_string_list(value.get("irreversible")),
    }


def coerce_confidence(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    level = coerce_string(source.get("level")).lower()
    if level not in {"low", "medium", "high"}:
        level = "medium"
    return {
        "level": level,
        "key_uncertainties": coerce_string_list(source.get("key_uncertainties")),
        "biggest_risk": coerce_string(source.get("biggest_risk")),
    }


def coerce_constraint_items(value: Any) -> list[dict[str, str]]:
    items = value if isinstance(value, list) else []
    normalized: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, dict):
            constraint = coerce_string(item.get("constraint"))
            implication = coerce_string(item.get("implication"))
        else:
            constraint = coerce_string(item)
            implication = ""
        if constraint or implication:
            normalized.append({"constraint": constraint, "implication": implication})
    return normalized


def coerce_decision_items(value: Any) -> list[dict[str, str]]:
    items = value if isinstance(value, list) else []
    normalized: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, dict):
            decision = coerce_string(item.get("decision"))
            reason = coerce_string(item.get("reason"))
        else:
            decision = coerce_string(item)
            reason = ""
        if decision or reason:
            normalized.append({"decision": decision, "reason": reason})
    return normalized


def build_interaction_loop() -> dict[str, Any]:
    direction = message(
        "decision",
        "Strategy",
        (
            "Strategic frame: Legacy will compete as an appointment-led luxury eyewear service, not as a mass fashion "
            "drop or a medical optics claim. The real alternatives are established luxury boutiques, trusted opticians, "
            "designer frames bought while traveling, and doing nothing until a buyer has a visible social or professional need."
        ),
        (
            "Positioning must precede concepts and copy. Strategy is defining category, competitive alternatives, "
            "behavioral demand, and constraints before departments propose work."
        ),
        [
            "Mass paid reach as a fashion launch.",
            "Medicalized optical-performance positioning.",
            "Editorial-only luxury awareness.",
        ],
        constraints={
            "brand": "Luxury signal must come from curation, restraint, and private service rather than discounts or mass reach.",
            "legal": "No optical, medical, scarcity, or superiority claims without substantiation.",
            "performance": "Every route must lead to a measurable appointment signal before scale.",
        },
        rejections=[
            {
                "option": "Paid-first reach launch as default direction",
                "classification": "strategic_conflict",
                "reason": "It treats luxury as awareness volume before proving high-intent demand.",
            }
        ],
    )
    creative_initial = message(
        "proposal",
        "Creative Specialist",
        (
            "Initial distinct concepts: 1) Private Gallery Standard, 2) Quiet Authority, 3) City Light Drop. "
            "Creative favors City Light Drop for visual memorability but flags Private Gallery Standard as the strongest "
            "fit with Strategy's appointment-led frame."
        ),
        (
            "The options are intentionally different: a service-led luxury experience, an understated status proof system, "
            "and a city-night limited release. City Light Drop creates stronger imagery but weakens the private-service signal."
        ),
        [
            "Private Gallery Standard: logic is private service as the first brand signal; works because it lowers taste risk; sacrifices fast reach.",
            "Quiet Authority: logic is proof-led restraint; works because it makes service and materials credible; sacrifices visual drama.",
            "City Light Drop: logic is cinematic city memorability; works because it earns attention; sacrifices appointment clarity.",
        ],
        constraints={
            "brand": "All concepts avoid discounting and mass-market language.",
            "legal": "City Light Drop may need proof if scarcity or limited availability is stated.",
            "performance": "Private Gallery Standard has the clearest appointment event; City Light Drop needs conversion proof.",
        },
        evaluates=["Strategy direction"],
    )
    copy_initial = message(
        "proposal",
        "Copywriting",
        (
            "Messaging options aligned to Strategy: 'Private fittings for frames chosen with intention', "
            "'Eyewear for those who do not need to announce status', and 'Crafted for precise fit in Mexico City'."
        ),
        (
            "Copywriting is not redefining the category. It is translating the appointment-led luxury position into messaging. "
            "'Precise fit' should remain a craft/service claim unless Legal confirms stronger substantiation."
        ),
        [
            "Private fitting CTA for appointment capture.",
            "Quiet-status headline for luxury tone.",
            "Craft and fit proof line for credibility.",
        ],
        constraints={
            "brand": "Tone must be restrained and service-led.",
            "legal": "Avoid optical superiority, health outcomes, or unverifiable performance language.",
            "performance": "Each message must map to a testable appointment action.",
        },
        evaluates=["Private Gallery Standard", "Quiet Authority", "City Light Drop"],
    )
    legal_initial = message(
        "critique",
        "Legal",
        (
            "Reject any unsubstantiated 'best', 'perfect', 'optical precision', or superiority claim. Modify scarcity language "
            "to 'limited opening appointments' only if capacity is true. Appointment capture requires privacy consent, and "
            "creator/stylist content requires disclosure."
        ),
        (
            "Luxury eyewear can speak to craft, fit experience, materials, and curation. Performance, medical, or scarcity claims "
            "need evidence. Legal is providing compliant alternatives instead of only blocking."
        ),
        [
            "Use 'crafted for a precise-feeling fit' only if the fitting process is documented.",
            "Use 'private fitting request' with consent language.",
            "Use 'limited opening appointments' only if actual appointment inventory is capped.",
        ],
        constraints={
            "brand": "Compliance language must be quiet and premium, not fear-based.",
            "legal": "Claims need substantiation; privacy and paid partnership disclosures are mandatory.",
            "performance": "Legal constraints must be built into landing forms and tracking surfaces before launch.",
        },
        evaluates=["Copywriting initial messaging", "Creative City Light Drop"],
        rejections=[
            {
                "option": "Optical precision/superiority copy",
                "classification": "hard_constraint",
                "reason": "Unsubstantiated and adjacent to regulated claims.",
            },
            {
                "option": "False scarcity",
                "classification": "hard_constraint",
                "reason": "Scarcity must reflect real capacity or inventory limits.",
            },
        ],
    )
    performance_initial = message(
        "critique",
        "Performance",
        (
            "Challenge: City Light Drop is memorable but does not prove high-intent appointment demand. A broad awareness push "
            "is likely to produce cheaper engagement but lower appointment quality. Require a two-cell pilot before scale."
        ),
        (
            "Prediction: broad visual reach should win on recall and low-cost traffic, but appointment-led proof should win on "
            "qualified fitting rate because the buying job involves trust, taste risk, and privacy. The strategy should be judged "
            "by qualified appointment requests, booked fitting cost, referral quality, show-up rate, and consult-to-purchase intent."
        ),
        [
            "Test Private Gallery Standard vs Quiet Authority proof before scale.",
            "Keep City Light Drop as retargeting only if it improves appointment completion.",
            "Measure booked fittings, qualified leads, and show-up rate.",
        ],
        constraints={
            "brand": "Performance tactics cannot force discounting, urgency spam, or broad cheap-reach optimization.",
            "legal": "Tracking and lead capture must preserve consent and disclosure requirements.",
            "performance": "No scale without a measurable hypothesis, baseline, and decision threshold.",
        },
        evaluates=["Creative initial concepts", "Copywriting initial messaging"],
        rejections=[
            {
                "option": "City Light Drop as lead concept",
                "classification": "strategic_conflict",
                "reason": "It optimizes recall before proving qualified appointment intent.",
            },
            {
                "option": "Disconnected channel list",
                "classification": "tactical_misalignment",
                "reason": "Channels need a testable operating logic and decision thresholds.",
            },
        ],
        predicted_outcomes=[
            {
                "scenario": "City Light Drop as lead with broad paid reach",
                "expected_result": "More low-intent visits, but lower qualified appointment request rate and weaker booked fitting rate.",
                "reasoning": "It likely underperforms because the creative hook is attention-rich but does not resolve buyer risk around taste, fit, or private service.",
            },
            {
                "scenario": "Private Gallery Standard appointment pilot",
                "expected_result": "Lower volume, stronger qualified appointment request rate, and more interpretable booked fitting rate data.",
                "reasoning": "It should produce stronger signal because the action matches the buying context: buyers with visible occasions need confidence before committing.",
            },
        ],
        behavioral_metrics=[
            {
                "conversion_action": "Request a private fitting",
                "measurable_signal": "qualified appointment request rate",
                "success_threshold": "At least 6% of qualified landing visitors request a fitting.",
            },
            {
                "conversion_action": "Book the fitting time",
                "measurable_signal": "booked fitting rate",
                "success_threshold": "At least 45% of qualified requests convert to booked fittings.",
            },
            {
                "conversion_action": "Attend the appointment",
                "measurable_signal": "show-up rate",
                "success_threshold": "At least 70% of booked fittings show up.",
            },
        ],
    )
    strategy_revision = message(
        "decision",
        "Strategy",
        (
            "Request revision: reject City Light Drop as the lead concept, reject optical-performance language, and combine "
            "Private Gallery Standard with Quiet Authority proof. Return a coherent appointment-led pilot with compliant claims "
            "and measurable decision thresholds."
        ),
        (
            "Legal and Performance introduced material constraints that change the decision. Strategy is rejecting a viable "
            "awareness-led option because it dilutes the chosen position and cannot yet prove appointment demand."
        ),
        [
            "Accept City Light Drop unchanged",
            "Run paid-first awareness",
            "Revise around private appointments and quiet-status proof",
        ],
        constraints={
            "brand": "The revised system must protect luxury restraint and private-service perception.",
            "legal": "All claims must be evidence-backed or softened into process language.",
            "performance": "The next proposal must include a measurable appointment pilot.",
        },
        evaluates=["Legal critique", "Performance critique", "Creative initial proposal", "Copywriting initial proposal"],
        rejections=[
            {
                "option": "City Light Drop lead",
                "classification": "strategic_conflict",
                "reason": "A viable creative idea, but it positions Legacy around visual buzz instead of private luxury service.",
            },
            {
                "option": "Optical precision language",
                "classification": "hard_constraint",
                "reason": "It is not credible without substantiation and creates avoidable compliance risk.",
            },
        ],
    )
    creative_revision = message(
        "proposal",
        "Creative Specialist",
        (
            "Revised concept: Private Gallery Standard. Visual system uses discreet appointment rooms, artisan frame details, "
            "and optician-led fitting moments. City Light Drop becomes a minor retargeting asset, not the launch idea."
        ),
        (
            "The revision keeps the premium visual world but makes the conversion moment private, credible, and easier to test."
        ),
        [
            "Lead concept: Private Gallery Standard | logic: private service first | works: lowers taste risk | sacrifices: fast reach.",
            "Support concept: Quiet Authority proof cards | logic: evidence before desire | works: makes fit and craft credible | sacrifices: cinematic impact.",
            "Retargeting asset only: City Light evening detail cutdowns | logic: memory aid | works: reactivates intent | sacrifices: cannot lead positioning.",
        ],
        constraints={
            "brand": "Premium cues come from space, service, craft, and restraint.",
            "legal": "No unsupported scarcity or optical superiority claims in visuals.",
            "performance": "Assets are separated into lead and retargeting roles for measurable tests.",
        },
        evaluates=["Strategy revision request"],
    )
    copy_revision = message(
        "proposal",
        "Copywriting",
        (
            "Revised messaging: 'Private fittings for frames chosen with intention', "
            "'Quiet-status eyewear for Mexico City', and 'Request a private Legacy fitting'."
        ),
        (
            "The revision removes unverified claims, strengthens appointment intent, and keeps the luxury tone restrained."
        ),
        [
            "Primary CTA: Request a private fitting.",
            "Proof line: crafted fit, curated frame selection, optician-led service.",
            "Brand line: quiet-status eyewear for Mexico City.",
        ],
        constraints={
            "brand": "Messaging is restrained, service-led, and avoids loud status language.",
            "legal": "Claims are framed around process and curation rather than medical outcomes.",
            "performance": "Primary action is one appointment request, not multiple competing CTAs.",
        },
        evaluates=["Creative revision", "Strategy revision request"],
    )
    legal_revision = message(
        "critique",
        "Legal",
        (
            "Conditional clearance: revised copy is acceptable if landing page includes consent language, creator disclosures, "
            "and no medical outcome claims. Keep 'crafted fit' but do not imply vision correction superiority."
        ),
        (
            "The revised proposal resolves the rejected claim and gives compliant alternatives without weakening the offer."
        ),
        [
            "Add privacy consent near appointment form.",
            "Add paid partnership disclosure for stylist or creator content.",
            "Keep claim substantiation file for craft and materials language.",
        ],
        constraints={
            "brand": "Disclosures must be integrated cleanly without cheapening the experience.",
            "legal": "Conditional clearance requires consent, disclosure, and claim substantiation controls.",
            "performance": "Compliance checks must be part of launch readiness and not a post-launch fix.",
        },
        evaluates=["Creative revision", "Copywriting revision"],
    )
    performance_revision = message(
        "critique",
        "Performance",
        (
            "Accept the revised pilot with constraints: two concept cells, three channels, six-week test, cap scale until booked "
            "fittings and show-up rate beat thresholds. Predicted outcome is fewer total leads than broad awareness but a higher "
            "share of qualified private-fitting demand."
        ),
        (
            "The revision can be evaluated. It protects luxury perception while producing measurable demand signals. Probability "
            "of learning is higher than the original path because the test isolates service-led demand from proof-led demand."
        ),
        [
            "Cell A: Private Gallery Standard.",
            "Cell B: Quiet Authority proof cards.",
            "Scale only if booked fitting rate, qualified lead cost, and show-up rate are acceptable.",
        ],
        constraints={
            "brand": "Paid optimization is capped so the algorithm cannot chase low-quality leads at the expense of luxury.",
            "legal": "Lead sources and retargeting pools must follow consent and disclosure constraints.",
            "performance": "Use a six-week test with Strategy decision gate before scaling.",
        },
        evaluates=["Creative revision", "Copywriting revision", "Legal revision"],
        predicted_outcomes=[
            {
                "scenario": "Private Gallery Standard cell",
                "expected_result": "Best chance of booked fitting rate and show-up rate, with slower top-of-funnel growth.",
                "reasoning": "It should win on appointment behavior because the offer reduces switching friction by making the first action private, curated, and service-led.",
            },
            {
                "scenario": "Quiet Authority proof-card cell",
                "expected_result": "Likely lower immediate booked fitting rate but stronger referral qualification rate.",
                "reasoning": "It likely trails on immediate booking because proof cards build credibility before asking buyers to commit to a fitting.",
            },
            {
                "scenario": "Scale before thresholds",
                "expected_result": "Higher spend with weaker cost per qualified fitting and greater risk of diluting luxury perception.",
                "reasoning": "This likely fails because without appointment-quality thresholds, paid channels optimize toward cheap intent rather than qualified buyers.",
            },
        ],
        behavioral_metrics=[
            {
                "conversion_action": "Submit a qualified fitting request",
                "measurable_signal": "qualified appointment request rate",
                "success_threshold": "Private Gallery Standard beats Quiet Authority by 20% or clears 6% qualified request rate.",
            },
            {
                "conversion_action": "Book a fitting from an approved source",
                "measurable_signal": "cost per qualified fitting",
                "success_threshold": "Cost per qualified booked fitting stays under MXN 1,800.",
            },
            {
                "conversion_action": "Attend the booked fitting",
                "measurable_signal": "show-up rate",
                "success_threshold": "Show-up rate reaches at least 70% before spend scales.",
            },
        ],
    )
    strategy_decision = {
        "competitive_frame": (
            "Legacy competes against established luxury eyewear boutiques, trusted opticians, designer frames purchased abroad, "
            "and the status quo of postponing a purchase. The category to own is private luxury eyewear fitting in Mexico City, "
            "not generic fashion eyewear or medical optics."
        ),
        "demand_situation": (
            "Target the moment when a buyer needs frames for visible professional or social settings and wants a refined status "
            "signal without conspicuous logos. Action happens when the appointment feels curated, private, credible, and low-risk."
        ),
        "chosen_position": (
            "Quiet-status luxury eyewear discovered through a private fitting, supported by craft, curation, and service proof."
        ),
        "switching_logic": {
            "boutique": (
                "From boutiques, the buyer switches because boutique browsing offers luxury inventory but not enough private "
                "guidance for a high-visibility occasion; Legacy makes the first action a curated fitting that reduces taste risk."
            ),
            "optician": (
                "From opticians, the buyer switches because functional confidence alone does not deliver the quiet-status luxury "
                "signal; Legacy keeps optician-led fit credibility while adding curation, materials proof, and private service."
            ),
            "buying_abroad": (
                "From buying abroad, the buyer switches because prestige shopping while traveling adds friction, delay, and poor "
                "local follow-up; Legacy offers a local concierge appointment with Mexico City context and post-fitting continuity."
            ),
            "doing_nothing": (
                "From doing nothing, the buyer switches because a visible professional or social occasion creates risk in delaying; "
                "Legacy lowers the commitment barrier with a private request, curated options, and proof before purchase pressure."
            ),
        },
        "differentiated_value": (
            "A buyer switches to Legacy when the alternative feels incomplete. From boutiques, the buyer gets luxury inventory but "
            "not enough private guidance to reduce taste risk for a visible occasion. From opticians, the buyer gets functional "
            "confidence but not a quiet-status luxury signal. From buying abroad, the buyer gets prestige but adds travel friction, "
            "delay, and weak local follow-up. From doing nothing, the buyer avoids risk but remains unprepared when a professional "
            "or social moment makes frames visible. Legacy wins by combining private taste guidance, optician-led fit confidence, "
            "materials proof, and local concierge access in one appointment."
        ),
        "constraints_applied": {
            "brand": "No discounting, no mass-market urgency, no loud status language, and no broad reach before luxury trust is proven.",
            "legal": "No optical-performance, health, superiority, or false-scarcity claims without substantiation; privacy consent and creator disclosures are mandatory.",
            "performance": "Scale is blocked until qualified appointments, booked fitting cost, show-up rate, and lead quality beat thresholds.",
        },
        "tradeoffs": {
            "chosen": "Appointment-led Private Gallery Standard with Quiet Authority proof messaging.",
            "rejected": [
                {
                    "option": "City Light Drop as lead concept",
                    "classification": "strategic_conflict",
                    "reason": "Viable and visually distinctive, but it competes on campaign energy instead of private luxury service.",
                },
                {
                    "option": "Paid-first awareness launch",
                    "classification": "strategic_conflict",
                    "reason": "It may create reach, but it risks cheapening luxury perception before proving qualified demand.",
                },
                {
                    "option": "Optical precision or superiority claim",
                    "classification": "hard_constraint",
                    "reason": "It is not defensible without substantiation and creates avoidable legal risk.",
                },
            ],
        },
        "tradeoff_pressure": {
            "scale_vs_control": (
                "Strategy chooses controlled appointment demand over broad scale because luxury trust and lead quality are more "
                "valuable than cheap reach before the category signal is established."
            ),
            "brand_vs_performance": (
                "Performance optimization is allowed only after brand-safe constraints are set; cheap lead volume is rejected if it "
                "pulls the system toward discount cues or low-quality appointment requests."
            ),
            "awareness_vs_conversion": (
                "Awareness creative is rejected as the lead because the business needs qualified private fitting requests before "
                "it can justify broader campaign visibility."
            ),
        },
        "constraint_hierarchy": {
            "hard_constraint": [
                {
                    "constraint": "No optical-performance, health, superiority, or false-scarcity claims without substantiation.",
                    "implication": "Copy and creative must use craft, fit-process, materials, and service language unless evidence is supplied.",
                },
                {
                    "constraint": "Privacy consent and creator/stylist disclosures are mandatory.",
                    "implication": "Lead capture, retargeting, and referral content cannot launch until disclosure surfaces are approved.",
                },
            ],
            "strategic_conflict": [
                {
                    "constraint": "Luxury positioning depends on restraint, curation, and private service.",
                    "implication": "Broad paid reach, discounting, and visually loud launch behavior are rejected even if they can create traffic.",
                },
                {
                    "constraint": "The category is private luxury eyewear fitting, not generic fashion eyewear.",
                    "implication": "Creative work must make the appointment experience the product-entry point.",
                },
            ],
            "tactical_misalignment": [
                {
                    "constraint": "Channels must serve the appointment-led operating logic.",
                    "implication": "Retargeting and referral outreach are allowed only when they move qualified buyers toward private fittings.",
                },
                {
                    "constraint": "Measurement must isolate high-quality demand.",
                    "implication": "Scale decisions use booked fitting quality and show-up rate, not low-cost traffic volume.",
                },
            ],
        },
        "material_constraint_change": {
            "constraint": "Performance and brand constraints required qualified appointment proof before scale.",
            "changed_decision": "City Light Drop moved from lead launch concept to capped retargeting support.",
            "rejected_default": "A paid-first awareness launch built around visually memorable city-night creative.",
            "why_material": "The constraint changed budget allocation, channel role, and creative hierarchy before launch.",
        },
        "execution_policy": {
            "approach": (
                "Run a guarded six-week appointment pilot. Lead with Private Gallery Standard, support it with Quiet Authority "
                "proof cards, and use retargeting only to complete appointment intent."
            ),
            "channels": [
                "private appointment landing flow",
                "stylist and concierge referral outreach",
                "controlled paid social retargeting",
            ],
            "constraints": [
                "one primary CTA: request a private fitting",
                "no discount-led acquisition",
                "no claim leaves review without substantiation or approved alternative language",
                "no budget scale until Strategy reviews the experiment metrics",
            ],
        },
        "experiment_plan": {
            "hypothesis": (
                "Behavioral buyers seeking discreet status will book private fittings at higher quality than a visual drop concept "
                "when the offer is framed as curated service plus proof."
            ),
            "test_design": (
                "Six-week two-cell test: Cell A uses Private Gallery Standard service-led creative; Cell B uses Quiet Authority proof "
                "cards. Both drive to the same private fitting request flow. Retargeting is capped and only supports incomplete "
                "appointment intent."
            ),
            "success_metrics": [
                "qualified appointment request rate",
                "cost per qualified booked fitting",
                "show-up rate",
                "consult-to-purchase intent",
                "legal review pass rate before launch",
            ],
            "behavioral_metrics": [
                {
                    "conversion_action": "Request a private fitting",
                    "measurable_signal": "qualified appointment request rate",
                    "success_threshold": "At least 6% of qualified landing visitors request a fitting.",
                },
                {
                    "conversion_action": "Book the fitting",
                    "measurable_signal": "cost per qualified fitting",
                    "success_threshold": "Cost per qualified booked fitting stays under MXN 1,800.",
                },
                {
                    "conversion_action": "Attend the fitting",
                    "measurable_signal": "show-up rate",
                    "success_threshold": "At least 70% of booked fittings show up.",
                },
            ],
        },
        "decision_irreversibility": {
            "reversible": [
                {
                    "decision": "Creative weighting between Private Gallery Standard and Quiet Authority proof cards.",
                    "reason": "The pilot can shift budget and surface area after early appointment-quality signals.",
                },
                {
                    "decision": "Retargeting creative mix and spend cap.",
                    "reason": "Retargeting can be paused or reallocated without changing the brand position.",
                },
                {
                    "decision": "Concierge and stylist partner shortlist.",
                    "reason": "Partners can be added or removed if lead quality or disclosure readiness is weak.",
                },
            ],
            "irreversible": [
                {
                    "decision": "Public category signal as private luxury eyewear fitting.",
                    "reason": "Once launched publicly, the first market memory is hard to undo and should not be diluted by mass fashion cues.",
                },
                {
                    "decision": "Legal claim posture around optical performance.",
                    "reason": "A misleading claim can create compliance exposure and trust damage that cannot be fixed by later optimization.",
                },
                {
                    "decision": "Luxury pricing and discount posture.",
                    "reason": "Early discounting would anchor expectations and weaken the premium signal.",
                },
            ],
            "prioritization": (
                "Protect irreversible brand, legal, and pricing decisions first; use reversible pilots to learn which appointment-led "
                "message earns the strongest qualified demand."
            ),
        },
        "confidence": {
            "level": "medium",
            "key_uncertainties": [
                "Whether Mexico City luxury eyewear buyers will book private fittings from a new brand without existing social proof.",
                "Whether concierge and stylist referrals produce enough qualified appointments at acceptable cost.",
                "Whether quiet-status messaging differentiates strongly enough from established luxury boutiques.",
            ],
            "biggest_risk": (
                "The appointment-led position may be strategically coherent but underpowered if Legacy lacks enough proof assets, "
                "referral partners, or visible early adopters to make switching feel safe."
            ),
        },
        "final_decision": (
            "Approve the appointment-led luxury launch with medium confidence. Protect irreversible brand and legal choices first. "
            "Reject City Light Drop as the lead, reject paid-first awareness, and reject unsubstantiated optical claims. Strategy "
            "will only approve scale after the pilot proves qualified appointment demand."
        ),
    }
    final_decision = message(
        "decision",
        "Strategy",
        (
            "Final direction: approve an appointment-led luxury launch using Private Gallery Standard as the lead concept, "
            "Quiet Authority as proof messaging, and guarded retargeting only after appointment intent. Reject City Light Drop "
            "as the lead, reject paid-first awareness, and reject unsubstantiated optical-performance claims. Confidence is medium "
            "because switching behavior and referral quality remain uncertain."
        ),
        (
            "This direction uses Creative and Copywriting proposals but incorporates Legal modifications and Performance "
            "measurement constraints. It resolves disagreement by choosing private-service positioning over a viable visual-drop "
            "alternative because the chosen system better protects brand perception and creates measurable demand."
        ),
        [
            "Rejected: City Light Drop as lead concept.",
            "Rejected: paid-first awareness launch.",
            "Rejected: optical precision claims without substantiation.",
            "Accepted: private appointment proof before scale.",
        ],
        constraints=strategy_decision["constraints_applied"],
        evaluates=["Creative revision", "Copywriting revision", "Legal revision", "Performance revision"],
        rejections=strategy_decision["tradeoffs"]["rejected"],
        irreversibility={
            "reversible": [item["decision"] for item in strategy_decision["decision_irreversibility"]["reversible"]],
            "irreversible": [item["decision"] for item in strategy_decision["decision_irreversibility"]["irreversible"]],
        },
        confidence=strategy_decision["confidence"],
        decision_payload={"strategy_decision": strategy_decision},
    )

    messages = [
        direction,
        creative_initial,
        copy_initial,
        legal_initial,
        performance_initial,
        strategy_revision,
        creative_revision,
        copy_revision,
        legal_revision,
        performance_revision,
        final_decision,
    ]
    proposals = [item.as_dict() for item in messages if item.type == "proposal"]
    critiques = [item.as_dict() for item in messages if item.type == "critique"]
    decisions = [item.as_dict() for item in messages if item.type == "decision"]
    return {
        "messages": [item.as_dict() for item in messages],
        "proposals": proposals,
        "critiques": critiques,
        "decisions": decisions,
        "final_decision": final_decision.as_dict(),
        "strategy_decision": strategy_decision,
        "conflict_resolution": (
            "Creative preferred visual memorability, Legal rejected unsupported claims and required disclosure, and Performance "
            "challenged broad awareness. Strategy chose the coherent appointment-led route and rejected the viable visual-drop "
            "and paid-first alternatives."
        ),
    }


def build_operation_output(loop: dict[str, Any]) -> dict[str, Any]:
    final = loop["final_decision"]
    strategy_decision = loop["strategy_decision"]
    constraints_applied = strategy_decision["constraints_applied"]
    execution_policy = strategy_decision["execution_policy"]
    experiment_plan = strategy_decision["experiment_plan"]
    performance_predictions = [
        outcome
        for critique in loop["critiques"]
        if critique["department"] == "Performance"
        for outcome in critique.get("predicted_outcomes", [])
    ]
    performance_metrics = [
        metric
        for critique in loop["critiques"]
        if critique["department"] == "Performance"
        for metric in critique.get("behavioral_metrics", [])
    ]
    return {
        "client_context": CLIENT_CONTEXT,
        "interaction_protocol": PROTOCOL_FIELDS,
        "interaction_rules": INTERACTION_RULES,
        "rejection_rules": REJECTION_RULES,
        "strategy_decision_schema": STRATEGY_DECISION_SCHEMA,
        "iteration_loop": {
            "completed": True,
            "shape": "proposal -> critique -> revision -> decision",
            "forced_disagreement": True,
            "strategy_final_authority": True,
            "non_linear": True,
            "strategy_evaluates_all_inputs": True,
        },
        "intermediate_proposals": loop["proposals"],
        "critiques": loop["critiques"],
        "strategy_decisions": loop["decisions"],
        "strategy_decision": strategy_decision,
        "switching_logic": strategy_decision["switching_logic"],
        "tradeoff_pressure": strategy_decision["tradeoff_pressure"],
        "constraint_hierarchy": strategy_decision["constraint_hierarchy"],
        "material_constraint_change": strategy_decision["material_constraint_change"],
        "decision_irreversibility": strategy_decision["decision_irreversibility"],
        "confidence": strategy_decision["confidence"],
        "quality_gate": loop.get(
            "quality_gate",
            {"failures": [], "passed": True},
        ),
        "performance_predictions": performance_predictions,
        "performance_metrics": performance_metrics,
        "final_strategy_decision": final,
        "final_reasoning": strategy_decision["final_decision"],
        "conflict_resolution": loop["conflict_resolution"],
        "positioning": strategy_decision["chosen_position"],
        "target_audience": [
            strategy_decision["demand_situation"],
            "Behavioral segment: buyers with a visible social or professional occasion who want discreet status and private guidance.",
        ],
        "approach": execution_policy["approach"],
        "constraints": [
            "Strategy is final decision authority",
            constraints_applied["brand"],
            constraints_applied["legal"],
            constraints_applied["performance"],
            *execution_policy["constraints"],
        ],
        "execution_plan": {
            "approach": execution_policy["approach"],
            "channels": execution_policy["channels"],
            "rollout_phases": [
                "Finalize compliant Private Gallery Standard creative and copy.",
                "Launch two-cell appointment pilot: Private Gallery Standard vs Quiet Authority.",
                "Review booked fitting rate, qualified lead cost, and show-up rate before scale.",
            ],
            "timeline": "Six-week pilot before scale decisions.",
            "campaign_structure": experiment_plan["test_design"],
        },
        "risks": [
            strategy_decision["confidence"]["biggest_risk"],
            "Appointment-led growth may be slower than a paid-first launch.",
            "Retargeting must not cheapen the premium brand signal.",
            "Claims and creator disclosures require disciplined review before launch.",
        ],
        "recommendations": [
            "Approve the Private Gallery Standard appointment-led pilot.",
            "Keep City Light Drop as secondary retargeting creative only.",
            "Reject unsubstantiated optical-performance claims.",
            "Hold broad paid awareness until appointment quality is proven.",
        ],
        "decision_traces": [
            {
                "decision": strategy_decision["final_decision"],
                "alternatives": final["alternatives"],
                "constraints": [
                    constraints_applied["brand"],
                    constraints_applied["legal"],
                    constraints_applied["performance"],
                ],
                "departments": [department.name for department in DEPARTMENTS],
                "rationale": final["reasoning"],
                "rejected": strategy_decision["tradeoffs"]["rejected"],
                "switching_logic": strategy_decision["switching_logic"],
                "tradeoff_pressure": strategy_decision["tradeoff_pressure"],
                "constraint_hierarchy": strategy_decision["constraint_hierarchy"],
                "material_constraint_change": strategy_decision["material_constraint_change"],
                "decision_irreversibility": strategy_decision["decision_irreversibility"],
                "confidence": strategy_decision["confidence"],
            }
        ],
        "experiment_plan": experiment_plan,
        "rejection_rules_applied": [
            "positioning must name alternatives and category",
            "positioning cannot be a generic label",
            "switching logic must cover boutique, optician, buying abroad, and doing nothing",
            "differentiated value must be credible and provable",
            "constraints must shape the final choice",
            "a material constraint must change the decision",
            "rejections must be classified by constraint hierarchy",
            "at least one viable scale/control, brand/performance, or awareness/conversion tradeoff must be rejected",
            "experiments must use behavioral user actions, not surveys or awareness metrics",
            "execution must be a coherent policy, not a channel list",
            "irreversible decisions must be protected before reversible tests",
            "confidence must name uncertainties and the biggest risk",
        ],
        "iteration_deltas": [
            {
                "what_changed": "City Light Drop moved from lead concept to secondary retargeting asset.",
                "why_changed": "Performance challenged weak appointment intent and Strategy accepted the critique.",
                "trigger": "performance disagreement",
                "department": "Strategy",
            },
            {
                "what_changed": "Optical precision copy was replaced with crafted-fit and private-fitting language.",
                "why_changed": "Legal rejected unsubstantiated optical-performance claims.",
                "trigger": "legal rejection",
                "department": "Strategy",
            },
        ],
        "memory_attributions": [
            {
                "memory_title": "Luxury appointment proof pattern",
                "changed_reasoning": "Prior premium retail patterns favor private appointment proof before broad reach.",
            }
        ],
    }


def department_outputs(loop: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_department: dict[str, list[dict[str, Any]]] = {department.name: [] for department in DEPARTMENTS}
    for item in loop["messages"]:
        by_department[item["department"]].append(item)
    return by_department


def persist_department_task_events(
    client: ForgeGraphClient,
    run_id: str,
    loop: dict[str, Any],
) -> None:
    outputs = department_outputs(loop)
    for index, department in enumerate(DEPARTMENTS):
        messages = outputs[department.name]
        event = {
            "event_type": "node_run.updated",
            "node_run": {
                "node_id": department.id,
                "node_type": "agent",
                "status": "succeeded",
                "attempt": 1,
                "started_at": _iso_now(index),
                "ended_at": _iso_now(index + 1),
                "input_json": {
                    "client_context": CLIENT_CONTEXT,
                    "operation_brief": CLIENT_CONTEXT["goal"],
                    "department_prompt": build_department_prompt(department),
                    "interaction_protocol": PROTOCOL_FIELDS,
                    "interaction_rules": INTERACTION_RULES,
                    "rejection_rules": REJECTION_RULES,
                    "strategy_decision_schema": STRATEGY_DECISION_SCHEMA,
                },
                "output_json": {
                    "department": department.name,
                    "messages": messages,
                    "summary": messages[-1]["content"] if messages else "",
                },
            },
        }
        client.post_run_event(run_id, event)


def complete_operation(
    client: ForgeGraphClient,
    run_id: str,
    output: dict[str, Any],
) -> None:
    client.post_run_event(
        run_id,
        {
            "event_type": "run.updated",
            "run": {
                "status": "succeeded",
                "ended_at": _iso_now(20),
                "output_json": output,
                "error_message": "",
            },
        },
    )


def prepare_operation_for_decision_loop(client: ForgeGraphClient, operation: dict[str, Any]) -> dict[str, Any]:
    run_id = str(operation["id"])
    status = str(operation.get("status") or "").lower()
    queue_status = str(operation.get("queue_status") or "").lower()
    if status == "running" and queue_status not in {"pending", "queued", "processing"}:
        client.cancel_run(run_id)
        time.sleep(1.0)
        client.post_run_event(
            run_id,
            {
                "event_type": "run.updated",
                "run": {
                    "status": "running",
                    "started_at": _iso_now(),
                    "ended_at": None,
                    "output_json": None,
                    "error_message": "",
                },
            },
        )
        operation["engine_execution_canceled_for_decision_loop"] = True
        operation["status"] = "running"
    return operation


def write_artifacts(
    *,
    result: dict[str, Any],
    output_json: Path,
    output_md: Path,
) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    output_md.write_text(render_markdown(result), encoding="utf-8")


def render_markdown(result: dict[str, Any]) -> str:
    output = result["operation_output"]
    final = output["final_strategy_decision"]
    strategy = output["strategy_decision"]
    constraints = strategy["constraints_applied"]
    tradeoffs = strategy["tradeoffs"]
    execution = strategy["execution_policy"]
    experiment = strategy["experiment_plan"]
    switching_logic = strategy["switching_logic"]
    tradeoff_pressure = strategy["tradeoff_pressure"]
    hierarchy = strategy["constraint_hierarchy"]
    material_change = strategy["material_constraint_change"]
    irreversibility = strategy["decision_irreversibility"]
    confidence = strategy["confidence"]
    performance_predictions = output["performance_predictions"]
    performance_metrics = output.get("performance_metrics", [])
    quality_gate = output.get("quality_gate", {})
    lines = [
        "# Atlas Growth Agency OS Decision Run",
        "",
        f"Company: {COMPANY_NAME}",
        f"Client: {CLIENT_CONTEXT['name']}",
        f"Goal: {CLIENT_CONTEXT['goal']}",
        f"Company ID: {result['company']['graph_id']}",
        f"Operation ID: {result['operation']['id']}",
        "",
        "## Final Strategy Decision",
        "",
        strategy["final_decision"],
        "",
        f"Reasoning: {final['reasoning']}",
        "",
        "## Structured Strategy Decision",
        "",
        f"Competitive frame: {strategy['competitive_frame']}",
        "",
        f"Demand situation: {strategy['demand_situation']}",
        "",
        f"Chosen position: {strategy['chosen_position']}",
        "",
        "Switching logic:",
        f"- Boutique: {switching_logic['boutique']}",
        f"- Optician: {switching_logic['optician']}",
        f"- Buying abroad: {switching_logic['buying_abroad']}",
        f"- Doing nothing: {switching_logic['doing_nothing']}",
        "",
        f"Differentiated value: {strategy['differentiated_value']}",
        "",
        "Constraints applied:",
        f"- Brand: {constraints['brand']}",
        f"- Legal: {constraints['legal']}",
        f"- Performance: {constraints['performance']}",
        "",
        f"Chosen tradeoff: {tradeoffs['chosen']}",
        "",
        "Tradeoff pressure:",
        f"- Scale vs control: {tradeoff_pressure['scale_vs_control']}",
        f"- Brand vs performance: {tradeoff_pressure['brand_vs_performance']}",
        f"- Awareness vs conversion: {tradeoff_pressure['awareness_vs_conversion']}",
        "",
        "Rejected options:",
        *[f"- {item['classification']} - {item['option']}: {item['reason']}" for item in tradeoffs["rejected"]],
        "",
        "Constraint hierarchy:",
        *[
            f"- hard_constraint - {item['constraint'].rstrip('.')}: {item['implication']}"
            for item in hierarchy["hard_constraint"]
        ],
        *[
            f"- strategic_conflict - {item['constraint'].rstrip('.')}: {item['implication']}"
            for item in hierarchy["strategic_conflict"]
        ],
        *[
            f"- tactical_misalignment - {item['constraint'].rstrip('.')}: {item['implication']}"
            for item in hierarchy["tactical_misalignment"]
        ],
        "",
        "Material constraint change:",
        f"- Constraint: {material_change['constraint']}",
        f"- Changed decision: {material_change['changed_decision']}",
        f"- Rejected default: {material_change['rejected_default']}",
        f"- Why material: {material_change['why_material']}",
        "",
        "Execution policy:",
        f"- Approach: {execution['approach']}",
        *[f"- Channel: {channel}" for channel in execution["channels"]],
        *[f"- Constraint: {constraint}" for constraint in execution["constraints"]],
        "",
        "Experiment plan:",
        f"- Hypothesis: {experiment['hypothesis']}",
        f"- Test design: {experiment['test_design']}",
        *[f"- Success metric: {metric}" for metric in experiment["success_metrics"]],
        *[
            f"- Behavioral metric: {metric['conversion_action']} | {metric['measurable_signal']} | threshold: {metric['success_threshold']}"
            for metric in experiment.get("behavioral_metrics", [])
        ],
        "",
        "Decision irreversibility:",
        *[
            f"- Reversible - {item['decision'].rstrip('.')}: {item['reason']}"
            for item in irreversibility["reversible"]
        ],
        *[
            f"- Irreversible - {item['decision'].rstrip('.')}: {item['reason']}"
            for item in irreversibility["irreversible"]
        ],
        f"- Prioritization: {irreversibility['prioritization']}",
        "",
        "Confidence:",
        f"- Level: {confidence['level']}",
        *[f"- Key uncertainty: {item}" for item in confidence["key_uncertainties"]],
        f"- Biggest risk: {confidence['biggest_risk']}",
        "",
        "Performance predictions:",
        *[
            f"- {item['scenario']}: {item['expected_result']} Reasoning: {item['reasoning']}"
            for item in performance_predictions
        ],
        *[
            f"- Metric: {metric['conversion_action']} | {metric['measurable_signal']} | threshold: {metric['success_threshold']}"
            for metric in performance_metrics
        ],
        "",
        "Quality gate:",
        f"- Passed: {quality_gate.get('passed', True)}",
        *[f"- Remaining failure: {item}" for item in quality_gate.get("failures", [])],
        "",
        f"Conflict resolution: {output['conflict_resolution']}",
        "",
        "## Intermediate Proposals",
        "",
    ]
    for proposal in output["intermediate_proposals"]:
        lines.extend(
            [
                f"### {proposal['department']}",
                "",
                proposal["content"],
                "",
                f"Reasoning: {proposal['reasoning']}",
                "",
                "Alternatives:",
                *[f"- {item}" for item in proposal["alternatives"]],
                "",
            ]
        )
    lines.extend(["## Critiques", ""])
    for critique in output["critiques"]:
        predicted_outcomes = critique.get("predicted_outcomes", [])
        behavioral_metrics = critique.get("behavioral_metrics", [])
        lines.extend(
            [
                f"### {critique['department']}",
                "",
                critique["content"],
                "",
                f"Reasoning: {critique['reasoning']}",
                "",
                "Alternatives:",
                *[f"- {item}" for item in critique["alternatives"]],
                "",
            ]
        )
        if predicted_outcomes:
            lines.extend(
                [
                    "Predicted outcomes:",
                    *[
                        f"- {item['scenario']}: {item['expected_result']} Reasoning: {item['reasoning']}"
                        for item in predicted_outcomes
                    ],
                    "",
                ]
            )
        if behavioral_metrics:
            lines.extend(
                [
                    "Behavioral metrics:",
                    *[
                        f"- {item['conversion_action']}: {item['measurable_signal']} threshold {item['success_threshold']}"
                        for item in behavioral_metrics
                    ],
                    "",
                ]
            )
    lines.extend(["## Strategy Decisions", ""])
    for decision in output["strategy_decisions"]:
        lines.extend(
            [
                f"### {decision['department']}",
                "",
                decision["content"],
                "",
                f"Reasoning: {decision['reasoning']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Atlas Growth Agency OS multi-department decision demo through ForgeGraph APIs."
    )
    parser.add_argument("--api-base", default=os.environ.get("FORGEGRAPH_API_BASE", DEFAULT_API_BASE))
    parser.add_argument("--email", default=os.environ.get("FORGEGRAPH_EMAIL", "test@example.com"))
    parser.add_argument("--password", default=os.environ.get("FORGEGRAPH_PASSWORD"))
    parser.add_argument(
        "--response-source",
        choices=["docker-llm", "scripted"],
        default=os.environ.get("ATLAS_AGENCY_RESPONSE_SOURCE", "docker-llm"),
        help="Use Docker Model Runner for department responses, or the deterministic scripted fixture.",
    )
    parser.add_argument(
        "--llm-base-url",
        default=os.environ.get("DOCKER_MODEL_RUNNER_BASE_URL", DEFAULT_DOCKER_LLM_BASE_URL),
        help="OpenAI-compatible Docker Model Runner base URL.",
    )
    parser.add_argument(
        "--llm-model",
        default=os.environ.get("DOCKER_MODEL_RUNNER_MODEL", DEFAULT_DOCKER_LLM_MODEL),
        help="Docker Model Runner model id to use.",
    )
    parser.add_argument(
        "--llm-timeout-seconds",
        type=int,
        default=int(os.environ.get("DOCKER_MODEL_RUNNER_TIMEOUT_SECONDS", "120")),
    )
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    password = args.password
    if not password:
        raise SystemExit("Set FORGEGRAPH_PASSWORD or pass --password.")

    client = ForgeGraphClient(args.api_base)
    client.login(args.email, password)

    docker_llm: DockerModelRunnerClient | None = None
    llm_model = args.llm_model
    llm_base_url = _normalize_openai_base_url(args.llm_base_url)
    if args.response_source == "docker-llm":
        docker_llm = DockerModelRunnerClient(
            base_url=llm_base_url,
            model=llm_model,
            timeout_seconds=args.llm_timeout_seconds,
        )
        llm_model = docker_llm.resolve_model()

    graph_json = build_company_graph_json(llm_model)
    company = client.create_company(graph_json)
    graph_id = str(company["graph_id"])
    graph_version_id = str(company["graph_version_id"])

    client.list_agents()
    operation = client.start_operation(graph_version_id)
    operation = prepare_operation_for_decision_loop(client, operation)
    run_id = str(operation["id"])

    if docker_llm is not None:
        loop = build_docker_llm_interaction_loop(docker_llm)
    else:
        loop = build_interaction_loop()
    persist_department_task_events(client, run_id, loop)
    operation_output = build_operation_output(loop)
    complete_operation(client, run_id, operation_output)

    persisted_run = client.get_run(run_id)
    agents = client.list_agents()
    tasks = [
        task
        for task in client.list_tasks()
        if str(task.get("execution_id") or "") == run_id
    ]
    report = client.generate_strategy_report(graph_id, run_id)

    result = {
        "company": company,
        "operation": persisted_run,
        "departments": agents,
        "tasks": tasks,
        "operation_output": operation_output,
        "strategy_report": report,
        "metadata": {
            "api_base": args.api_base,
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "response_source": args.response_source,
            "llm_base_url": llm_base_url if args.response_source == "docker-llm" else "",
            "llm_model": llm_model,
            "llm_call_count": docker_llm.call_count if docker_llm is not None else 0,
            "llm_json_repair_count": docker_llm.json_repair_count if docker_llm is not None else 0,
            "engine_execution_canceled_for_decision_loop": bool(
                operation.get("engine_execution_canceled_for_decision_loop")
            ),
            "used_backend_apis": [
                "POST /api/auth/login",
                "POST /api/graphs/external-workflows",
                "POST /api/runs/start",
                "POST /api/runs/{id}/events",
                "GET /api/runs/{id}",
                "GET /api/agents/",
                "GET /api/tasks/",
                "POST /api/reports/strategy-report",
            ],
        },
    }
    write_artifacts(result=result, output_json=args.output_json, output_md=args.output_md)

    final = operation_output["strategy_decision"]
    summary = {
        "company_id": graph_id,
        "operation_id": run_id,
        "strategy_decision": final,
        "proposal_count": len(operation_output["intermediate_proposals"]),
        "critique_count": len(operation_output["critiques"]),
        "response_source": args.response_source,
        "llm_model": llm_model,
        "llm_call_count": docker_llm.call_count if docker_llm is not None else 0,
        "llm_json_repair_count": docker_llm.json_repair_count if docker_llm is not None else 0,
        "quality_gate": operation_output["quality_gate"],
        "output_json": str(args.output_json),
        "output_md": str(args.output_md),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        time.sleep(0.05)
        raise SystemExit(1)
