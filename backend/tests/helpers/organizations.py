from __future__ import annotations

from infrastructure.orm.models import Graph, Organization


def required_company_organization(company: Graph) -> Organization:
    organization = company.organization
    assert organization is not None
    return organization
