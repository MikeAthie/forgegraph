from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict


class AvailableAccountingMetricPayload(TypedDict):
    status: Literal["available"]
    value: float
    currency: str
    computed_at: str
    source: str


class NotInstrumentedAccountingMetricPayload(TypedDict):
    status: Literal["not_instrumented"]
    reason: str
    computed_at: str
    source: str


AccountingMetricPayload = AvailableAccountingMetricPayload | NotInstrumentedAccountingMetricPayload


@dataclass(frozen=True, slots=True)
class AvailableAccountingMetric:
    value: float
    currency: str
    computed_at: str
    source: str
    status: Literal["available"] = "available"

    def to_json(self) -> AvailableAccountingMetricPayload:
        return {
            "status": self.status,
            "value": self.value,
            "currency": self.currency,
            "computed_at": self.computed_at,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class NotInstrumentedAccountingMetric:
    reason: str
    computed_at: str
    source: str
    status: Literal["not_instrumented"] = "not_instrumented"

    def to_json(self) -> NotInstrumentedAccountingMetricPayload:
        return {
            "status": self.status,
            "reason": self.reason,
            "computed_at": self.computed_at,
            "source": self.source,
        }


AccountingMetric = AvailableAccountingMetric | NotInstrumentedAccountingMetric
