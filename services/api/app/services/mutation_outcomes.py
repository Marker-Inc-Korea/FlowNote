from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Generic, TypeVar


T = TypeVar("T")


class MutationOutcomeStatus(StrEnum):
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    CONFLICT = "CONFLICT"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class MutationOutcome(Generic[T]):
    """Versioned internal result for state-changing application services.

    API routers adapt this result to their existing public response contracts.  The
    model intentionally does not become an API DTO so that adding internal guidance
    never changes older clients' JSON payloads.
    """

    status: MutationOutcomeStatus
    code: str
    message: str
    value: T | None = None
    receipt: str | None = None
    revision: int | None = None
    source_preserved: bool = True
    responsible_role: str | None = None
    action_route: str | None = None
    retry_item_ids: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = "mutation-outcome-v1"

    @property
    def succeeded(self) -> bool:
        return self.status in {
            MutationOutcomeStatus.SUCCESS,
            MutationOutcomeStatus.PARTIAL_SUCCESS,
        }

    @classmethod
    def success(
        cls,
        value: T,
        *,
        code: str = "SUCCESS",
        message: str = "변경이 저장되었습니다.",
        receipt: str | None = None,
        revision: int | None = None,
        responsible_role: str | None = None,
        action_route: str | None = None,
    ) -> MutationOutcome[T]:
        return cls(
            status=MutationOutcomeStatus.SUCCESS,
            code=code,
            message=message,
            value=value,
            receipt=receipt,
            revision=revision,
            responsible_role=responsible_role,
            action_route=action_route,
        )

    @classmethod
    def partial_success(
        cls,
        value: T,
        *,
        code: str,
        message: str,
        retry_item_ids: tuple[str, ...],
        responsible_role: str | None = None,
        action_route: str | None = None,
    ) -> MutationOutcome[T]:
        return cls(
            status=MutationOutcomeStatus.PARTIAL_SUCCESS,
            code=code,
            message=message,
            value=value,
            retry_item_ids=retry_item_ids,
            responsible_role=responsible_role,
            action_route=action_route,
        )

    @classmethod
    def conflict(
        cls,
        *,
        code: str,
        message: str,
        value: T | None = None,
        receipt: str | None = None,
        revision: int | None = None,
        source_preserved: bool = True,
        responsible_role: str | None = None,
        action_route: str | None = None,
    ) -> MutationOutcome[T]:
        return cls(
            status=MutationOutcomeStatus.CONFLICT,
            code=code,
            message=message,
            value=value,
            receipt=receipt,
            revision=revision,
            source_preserved=source_preserved,
            responsible_role=responsible_role,
            action_route=action_route,
        )

    @classmethod
    def rejected(
        cls,
        *,
        code: str,
        message: str,
        value: T | None = None,
        receipt: str | None = None,
        revision: int | None = None,
        source_preserved: bool = True,
        responsible_role: str | None = None,
        action_route: str | None = None,
        retry_item_ids: tuple[str, ...] = (),
    ) -> MutationOutcome[T]:
        return cls(
            status=MutationOutcomeStatus.REJECTED,
            code=code,
            message=message,
            value=value,
            receipt=receipt,
            revision=revision,
            source_preserved=source_preserved,
            responsible_role=responsible_role,
            action_route=action_route,
            retry_item_ids=retry_item_ids,
        )
