from __future__ import annotations

from typing import cast

import pytest

from application.services.career_ops_opportunities import (
    ensure_opportunity_for_signal,
    record_scanned_job,
)
from application.services.career_ops_tasks import (
    CAREER_OPS_URL_PIPELINE_TASK_STAGES,
    materialize_url_pipeline_tasks,
)
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import Graph, GraphVersion, Run, TaskRecord, User

pytestmark = pytest.mark.django_db


def _create_company(user: User, *, with_version: bool = True) -> Graph:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(Graph, Graph.objects.create(owner=user, organization=organization, name="CareerOps Task Co"))
    if with_version:
        GraphVersion.objects.create(graph=company, version=1, graph_json={"nodes": [], "edges": [], "metadata": {}})
    return company


def _run(company: Graph, user: User) -> Run:
    version = GraphVersion.objects.filter(graph=company).first() or GraphVersion.objects.create(
        graph=company,
        version=1,
        graph_json={"nodes": [], "edges": [], "metadata": {}},
    )
    return Run.objects.create(owner=user, organization=company.organization, graph_version=version, status="running")


def _posting() -> dict[str, object]:
    return {
        "title": "Senior AI Product Engineer",
        "company": "Acme AI",
        "url": "https://jobs.ashbyhq.com/acme/123?utm_source=spam",
        "location": "Remote",
        "provider": "ashby",
    }


def _opportunity(company: Graph, user: User):
    signal = record_scanned_job(company=company, user=user, posting=_posting())
    opportunity = ensure_opportunity_for_signal(signal=signal, user=user)
    assert opportunity is not None
    return opportunity


def test_materialize_url_pipeline_tasks_creates_expected_stage_tasks(user: User) -> None:
    company = _create_company(user)
    run = _run(company, user)
    opportunity = _opportunity(company, user)

    tasks = materialize_url_pipeline_tasks(
        company=company,
        run=run,
        opportunity_external_key=opportunity.external_key,
    )

    assert [task.source_node_id for task in tasks] == list(CAREER_OPS_URL_PIPELINE_TASK_STAGES)
    assert len(tasks) == 6
    assert TaskRecord.objects.filter(organization=company.organization).count() == 6
    approval = next(task for task in tasks if task.source_node_id == "stage_07_candidate_approval")
    assert approval.status == "waiting_for_decision"


def test_materialize_url_pipeline_tasks_replays_by_external_key_and_updates_run(user: User) -> None:
    company = _create_company(user)
    first_run = _run(company, user)
    second_run = _run(company, user)
    opportunity = _opportunity(company, user)

    first = materialize_url_pipeline_tasks(
        company=company,
        run=first_run,
        opportunity_external_key=opportunity.external_key,
    )
    second = materialize_url_pipeline_tasks(
        company=company,
        run=second_run,
        opportunity_external_key=opportunity.external_key,
    )

    assert [task.id for task in second] == [task.id for task in first]
    assert TaskRecord.objects.filter(organization=company.organization).count() == 6
    assert all(task.execution_id == second_run.id for task in second)


def test_materialize_url_pipeline_tasks_hashes_long_opportunity_external_keys(user: User) -> None:
    company = _create_company(user)
    run = _run(company, user)
    very_long_external_key = "career_ops:posting:" + "remote-talent-latam/" * 30

    tasks = materialize_url_pipeline_tasks(
        company=company,
        run=run,
        opportunity_external_key=very_long_external_key,
    )

    assert len(tasks) == 6
    assert all(len(task.external_key) <= 255 for task in tasks)
    assert all(very_long_external_key in task.summary for task in tasks)
