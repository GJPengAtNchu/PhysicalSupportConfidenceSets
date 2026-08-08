"""One-query-at-a-time capability with no score-table or oracle API."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping


class CandidateStatus(str, Enum):
    ADMISSIBLE = "ADMISSIBLE"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class QueryReceipt:
    query_number: int
    candidate_id: str
    status: CandidateStatus


class SealedQueryCapability:
    """Expose exactly one public operation: query one candidate ID."""

    __slots__ = ("__query_one", "__sealed")

    def __init__(self, query_one: Callable[[str], QueryReceipt]):
        object.__setattr__(self, "_SealedQueryCapability__query_one", query_one)
        object.__setattr__(self, "_SealedQueryCapability__sealed", False)

    def query(self, candidate_id: str) -> QueryReceipt:
        if object.__getattribute__(self, "_SealedQueryCapability__sealed"):
            raise RuntimeError("query capability is sealed")
        query_one = object.__getattribute__(self, "_SealedQueryCapability__query_one")
        return query_one(candidate_id)

    def seal(self) -> None:
        object.__setattr__(self, "_SealedQueryCapability__sealed", True)

    def __dir__(self) -> list[str]:
        return ["query", "seal"]

    def __getattr__(self, name: str):
        raise AttributeError(f"sealed capability has no attribute {name!r}")


class PrivateStoredStatusBackend:
    """Private immutable stored-status table; never passed to the controller."""

    __slots__ = ("__allowed_ids", "__statuses", "__queried", "__counter", "__capability")

    def __init__(
        self,
        public_candidate_ids: tuple[str, ...],
        stored_statuses: Mapping[str, CandidateStatus],
    ):
        if len(public_candidate_ids) != len(set(public_candidate_ids)):
            raise ValueError("candidate IDs must be unique")
        if set(public_candidate_ids) != set(stored_statuses):
            raise ValueError("stored status IDs do not match public manifest")
        object.__setattr__(self, "_PrivateStoredStatusBackend__allowed_ids", frozenset(public_candidate_ids))
        object.__setattr__(self, "_PrivateStoredStatusBackend__statuses", dict(stored_statuses))
        object.__setattr__(self, "_PrivateStoredStatusBackend__queried", set())
        object.__setattr__(self, "_PrivateStoredStatusBackend__counter", 0)
        object.__setattr__(
            self,
            "_PrivateStoredStatusBackend__capability",
            SealedQueryCapability(self.__query_one),
        )

    def capability(self) -> SealedQueryCapability:
        return object.__getattribute__(self, "_PrivateStoredStatusBackend__capability")

    def __query_one(self, candidate_id: str) -> QueryReceipt:
        allowed = object.__getattribute__(self, "_PrivateStoredStatusBackend__allowed_ids")
        queried = object.__getattribute__(self, "_PrivateStoredStatusBackend__queried")
        if candidate_id not in allowed:
            raise KeyError(f"candidate is not in public bank manifest: {candidate_id}")
        if candidate_id in queried:
            raise RuntimeError(f"duplicate candidate query: {candidate_id}")
        queried.add(candidate_id)
        counter = object.__getattribute__(self, "_PrivateStoredStatusBackend__counter") + 1
        object.__setattr__(self, "_PrivateStoredStatusBackend__counter", counter)
        statuses = object.__getattribute__(self, "_PrivateStoredStatusBackend__statuses")
        return QueryReceipt(counter, candidate_id, statuses[candidate_id])

    def queried_count_for_audit(self) -> int:
        return object.__getattribute__(self, "_PrivateStoredStatusBackend__counter")

    def seal(self) -> None:
        self.capability().seal()

