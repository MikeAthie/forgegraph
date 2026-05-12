from __future__ import annotations

from application.services.company_blueprints import CompanyBlueprintCompiler
from domain.services.graph_validator import GraphValidator


def _compile_payload():
    return CompanyBlueprintCompiler().compile(
        company_name="Acme Growth",
        objective="Build a repeatable growth motion with weekly campaign learning.",
        blueprint_id="digital_marketing_pro.v1",
        services=["campaign planning", "performance analysis"],
        regions=["US", "Mexico"],
        autonomy_mode="assisted",
        ai_access_mode="managed",
        intelligence_provider="openai",
    )


def test_pack_backed_company_blueprint_compiler_emits_valid_graph_json():
    result = _compile_payload()
    graph_json = result.graph_json

    assert GraphValidator().validate(graph_json, strict=True, require_entry_exit=True) == []
    assert {node["type"] for node in graph_json["nodes"]} == {
        "agent",
        "branch",
        "human_gate",
        "merge",
        "observation_context",
        "output",
    }
    assert graph_json["edges"][0] == {
        "id": "start-context",
        "from": "START",
        "to": "company_context",
    }
    assert graph_json["edges"][-1] == {
        "id": "output-end",
        "from": "final_deliverable",
        "to": "END",
    }

    assert graph_json["metadata"]["schema"] == "company_workspace.v1"
    assert graph_json["metadata"]["operating_model_pack"]["pack_id"] == ("digital_marketing_pro.v1")
    profile = graph_json["metadata"]["company_profile"]
    assert profile["companyName"] == "Acme Growth"
    assert profile["companyType"] == "Digital Marketing Agency"
    assert result.template_ids == [
        "operating_model_pack:digital_marketing_pro.v1",
        "program_template:dmp.engagement",
    ]


def test_pack_backed_departments_come_from_dmp_pack():
    result = _compile_payload()
    profile = result.graph_json["metadata"]["company_profile"]

    assert [department["label"] for department in profile["departments"]] == [
        "Strategy & Research",
        "Brand & Content",
        "Channel Execution",
        "CRM & Lifecycle",
        "Analytics & Performance",
        "QA & Compliance",
        "Client/Approval Operations",
    ]
    assert result.department_groups[0]["id"] == "installed-pack-departments"


def test_pack_backed_company_blueprint_compiler_is_deterministic():
    first = _compile_payload().as_payload()
    second = _compile_payload().as_payload()

    assert first == second
