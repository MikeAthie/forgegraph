"""
Retry policy value object.

Clean Architecture: Enterprise Business Rules layer.
"""

from dataclasses import dataclass
from enum import Enum


class BackoffStrategy(str, Enum):
    """Backoff strategy for retries."""

    FIXED = "fixed"
    EXPONENTIAL = "exponential"


@dataclass(frozen=True)
class RetryPolicy:
    """Configuration for retry behavior on node failures."""

    max_attempts: int = 3
    backoff_ms: int = 1000
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.backoff_ms < 0:
            raise ValueError("backoff_ms cannot be negative")

    def get_delay_ms(self, attempt: int) -> int:
        """Calculate the delay before the next retry attempt."""
        if attempt <= 1:
            return 0

        if self.backoff_strategy == BackoffStrategy.FIXED:
            return self.backoff_ms

        # Exponential backoff: delay * 2^(attempt-2)
        return int(self.backoff_ms * (2 ** (attempt - 2)))

    @classmethod
    def default(cls) -> "RetryPolicy":
        """Create a default retry policy."""
        return cls()

    @classmethod
    def no_retry(cls) -> "RetryPolicy":
        """Create a policy that doesn't retry."""
        return cls(max_attempts=1)
