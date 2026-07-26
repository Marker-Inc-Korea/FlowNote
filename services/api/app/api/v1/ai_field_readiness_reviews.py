from __future__ import annotations

import json
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user
from app.core.config import Settings, get_settings
from app.db.models import (
    AIGroundTruthDatasetCase,
    AIGroundTruthDatasetVersion,
    AIFieldReadinessSampleReview,
    AISearchGroundTruthCase,
)
from app.db.session import get_db_session
from app.services.ai_field_readiness_reviews import (
    canonical_findings,
    content_hash,
    decision_snapshot,
    disagreement_case_keys,
    evaluation_snapshot_pair_is_stable,
    review_pair_hash,
    sample_review_summary,
)
from app.services.ai_readiness import QUESTION_CATEGORIES, SCENARIO_TYPES, database_scope
from app.services.ai_operations import audit_event


router = APIRouter(
    prefix="/ai-search/field-readiness",
    tags=["ai-search"],
    dependencies=[Depends(get_current_user)],
)
REVIEW_ROLES = {
    "admin",
    "system-admin",
    "document-admin",
    "manager",
    "assistant-manager",
    "department-manager",
}
SAMPLE_SIZE = len(QUESTION_CATEGORIES) * len(SCENARIO_TYPES)


class SampleFinding(BaseModel):
    case_key: str = Field(alias="caseKey", min_length=1, max_length=100)
    citation_trace: Literal["PASS", "FAIL"] = Field(alias="citationTrace")
    citation_meaning: Literal["PASS", "FAIL"] = Field(alias="citationMeaning")
    conflict_disclosure: Literal["PASS", "FAIL", "NOT_APPLICABLE"] = Field(
        alias="conflictDisclosure"
    )
    permission_boundary: Literal["PASS", "FAIL"] = Field(alias="permissionBoundary")
    note: str = Field(min_length=1, max_length=2000)


class SampleReviewCreate(BaseModel):
    dataset_version_id: str = Field(alias="datasetVersionId", min_length=1, max_length=64)
    evaluation_run_id: str = Field(alias="evaluationRunId", min_length=1, max_length=64)
    sampling_plan_reference: str = Field(
        alias="samplingPlanReference", min_length=1, max_length=500
    )
    review_role: Literal["INDEPENDENT", "CONSENSUS"] = Field(
        default="INDEPENDENT", alias="reviewRole"
    )
    resolves_review_ids: list[str] = Field(
        default_factory=list, alias="resolvesReviewIds", max_length=2
    )
    findings: list[SampleFinding] = Field(min_length=1, max_length=SAMPLE_SIZE)


def _require_review_role(user: CurrentUser) -> None:
    if user.role not in REVIEW_ROLES:
        raise HTTPException(status_code=403, detail="field-readiness sample review role required")


def _dataset(
    session: Session,
    settings: Settings,
    dataset_version_id: str,
) -> AIGroundTruthDatasetVersion:
    row = session.scalar(
        select(AIGroundTruthDatasetVersion).where(
            AIGroundTruthDatasetVersion.dataset_version_id == dataset_version_id,
            AIGroundTruthDatasetVersion.customer_scope == settings.ai_customer_scope,
            AIGroundTruthDatasetVersion.site_scope == settings.ai_site_scope,
            AIGroundTruthDatasetVersion.database_scope == database_scope(settings.database_url),
            AIGroundTruthDatasetVersion.readiness_track == "FIELD_READINESS",
            AIGroundTruthDatasetVersion.status == "APPROVED",
        )
    )
    if row is None or not row.snapshot_hash:
        raise HTTPException(
            status_code=404,
            detail="approved FIELD_READINESS dataset version does not exist in this scope",
        )
    return row


def _require_stable_evaluation_pair(
    session: Session,
    dataset: AIGroundTruthDatasetVersion,
    run_id: str,
) -> None:
    if not evaluation_snapshot_pair_is_stable(
        session,
        dataset_version_id=dataset.dataset_version_id,
        dataset_snapshot_hash=dataset.snapshot_hash or "",
        run_id=run_id,
    ):
        raise HTTPException(
            status_code=409,
            detail="two identical quality-passed evaluations of this dataset snapshot are required",
        )


def _dataset_case_scenarios(
    session: Session,
    dataset_version_id: str,
) -> dict[str, str]:
    rows = session.execute(
        select(AISearchGroundTruthCase.case_key, AISearchGroundTruthCase.category,
               AISearchGroundTruthCase.scenario_type)
        .join(
            AIGroundTruthDatasetCase,
            AIGroundTruthDatasetCase.ground_truth_case_id
            == AISearchGroundTruthCase.ground_truth_case_id,
        )
        .where(AIGroundTruthDatasetCase.dataset_version_id == dataset_version_id)
    ).all()
    return {case_key: f"{category}:{scenario_type}" for case_key, category, scenario_type in rows}


def _finding_dicts(payload: SampleReviewCreate) -> list[dict[str, str]]:
    return canonical_findings(
        [finding.model_dump(by_alias=True, mode="json") for finding in payload.findings]
    )


def _review_dict(
    row: AIFieldReadinessSampleReview,
    *,
    include_decision: bool = True,
) -> dict[str, object]:
    return {
        "reviewId": row.review_id,
        "datasetVersionId": row.dataset_version_id,
        "evaluationRunId": row.evaluation_run_id,
        "datasetSnapshotHash": row.dataset_snapshot_hash,
        "reviewRole": row.review_role,
        "reviewerId": row.reviewer_id,
        "samplingPlanReference": row.sampling_plan_reference,
        "sampleCaseKeys": json.loads(row.sample_case_keys_json),
        "sampleHash": row.sample_hash,
        "findings": json.loads(row.findings_json) if include_decision else None,
        "decisionHash": row.decision_hash if include_decision else None,
        "reviewPairHash": row.review_pair_hash,
        "resolvesReviewIds": (
            json.loads(row.resolved_review_ids_json)
            if row.resolved_review_ids_json
            else []
        ),
        "createdAt": row.created_at,
    }


@router.post("/sample-reviews", status_code=201)
def create_sample_review(
    payload: SampleReviewCreate,
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, object]:
    _require_review_role(user)
    dataset = _dataset(session, settings, payload.dataset_version_id)
    _require_stable_evaluation_pair(session, dataset, payload.evaluation_run_id)
    if session.scalar(
        select(AIFieldReadinessSampleReview.id).where(
            AIFieldReadinessSampleReview.dataset_version_id == dataset.dataset_version_id,
            AIFieldReadinessSampleReview.evaluation_run_id == payload.evaluation_run_id,
            AIFieldReadinessSampleReview.reviewer_id == user.user_id,
        )
    ) is not None:
        raise HTTPException(status_code=409, detail="this reviewer already reviewed this run")

    findings = _finding_dicts(payload)
    case_keys = [item["caseKey"] for item in findings]
    if len(case_keys) != len(set(case_keys)):
        raise HTTPException(status_code=422, detail="sample caseKey values must be unique")
    case_scenarios = _dataset_case_scenarios(session, dataset.dataset_version_id)
    if any(case_key not in case_scenarios for case_key in case_keys):
        raise HTTPException(status_code=422, detail="sample contains a case outside this dataset")
    for item in findings:
        is_conflict = case_scenarios[item["caseKey"]].endswith(":CONFLICT")
        if is_conflict == (item["conflictDisclosure"] == "NOT_APPLICABLE"):
            raise HTTPException(
                status_code=422,
                detail="conflictDisclosure must be assessed only for CONFLICT cases",
            )

    existing = list(
        session.scalars(
            select(AIFieldReadinessSampleReview)
            .where(
                AIFieldReadinessSampleReview.dataset_version_id == dataset.dataset_version_id,
                AIFieldReadinessSampleReview.evaluation_run_id == payload.evaluation_run_id,
            )
            .order_by(AIFieldReadinessSampleReview.id)
        ).all()
    )
    independent = [row for row in existing if row.review_role == "INDEPENDENT"]
    pair_hash: str | None = None
    if payload.review_role == "INDEPENDENT":
        if payload.resolves_review_ids:
            raise HTTPException(status_code=422, detail="independent review cannot resolve reviews")
        if len(independent) >= 2:
            raise HTTPException(status_code=409, detail="two independent reviews already exist")
        if len(findings) != SAMPLE_SIZE or set(case_scenarios[key] for key in case_keys) != {
            f"{category}:{scenario}" for category in QUESTION_CATEGORIES for scenario in SCENARIO_TYPES
        }:
            raise HTTPException(
                status_code=422,
                detail="independent sample must contain one case from each of the 24 category/scenario cells",
            )
        if independent:
            first = independent[0]
            if first.sampling_plan_reference != payload.sampling_plan_reference.strip():
                raise HTTPException(status_code=409, detail="sampling plan reference must match")
            if json.loads(first.sample_case_keys_json) != case_keys:
                raise HTTPException(status_code=409, detail="independent reviewers must use the same sample")
    else:
        if len(independent) != 2:
            raise HTTPException(status_code=409, detail="consensus requires two independent reviews")
        expected_ids = sorted(row.review_id for row in independent)
        if sorted(set(payload.resolves_review_ids)) != expected_ids:
            raise HTTPException(status_code=422, detail="resolvesReviewIds must identify both reviews")
        if user.user_id in {row.reviewer_id for row in independent}:
            raise HTTPException(status_code=409, detail="consensus reviewer must be a third person")
        disagreements = disagreement_case_keys(independent[0], independent[1])
        if not disagreements:
            raise HTTPException(status_code=409, detail="matching reviews do not require consensus")
        if case_keys != disagreements:
            raise HTTPException(
                status_code=422,
                detail="consensus findings must resolve every disputed case and no other case",
            )
        if payload.sampling_plan_reference.strip() != independent[0].sampling_plan_reference:
            raise HTTPException(status_code=409, detail="sampling plan reference must match")
        pair_hash = review_pair_hash(independent[0].review_id, independent[1].review_id)

    sample_hash = content_hash(case_keys if payload.review_role == "INDEPENDENT" else json.loads(
        independent[0].sample_case_keys_json
    ))
    row = AIFieldReadinessSampleReview(
        review_id=f"aifreview-{uuid4().hex}",
        dataset_version_id=dataset.dataset_version_id,
        evaluation_run_id=payload.evaluation_run_id,
        dataset_snapshot_hash=dataset.snapshot_hash,
        review_role=payload.review_role,
        reviewer_id=user.user_id,
        sampling_plan_reference=payload.sampling_plan_reference.strip(),
        sample_case_keys_json=json.dumps(
            case_keys if payload.review_role == "INDEPENDENT" else json.loads(
                independent[0].sample_case_keys_json
            ),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        sample_hash=sample_hash,
        findings_json=json.dumps(findings, ensure_ascii=False, separators=(",", ":")),
        decision_hash=content_hash(decision_snapshot(findings)),
        review_pair_hash=pair_hash,
        resolved_review_ids_json=(
            json.dumps(sorted(set(payload.resolves_review_ids)), separators=(",", ":"))
            if payload.review_role == "CONSENSUS"
            else None
        ),
    )
    session.add(row)
    audit_event(
        session,
        event_type="FIELD_READINESS_SAMPLE_REVIEW_RECORDED",
        actor_id=user.user_id,
        customer_scope=dataset.customer_scope,
        site_scope=dataset.site_scope,
        target_type="FIELD_READINESS_SAMPLE_REVIEW",
        target_id=row.review_id,
        detail={
            "datasetVersionId": dataset.dataset_version_id,
            "evaluationRunId": payload.evaluation_run_id,
            "reviewRole": payload.review_role,
            "sampleHash": sample_hash,
            "reviewPairHash": pair_hash,
        },
    )
    session.commit()
    session.refresh(row)
    return {
        "review": _review_dict(row),
        "summary": sample_review_summary(
            session,
            dataset_version_id=dataset.dataset_version_id,
            dataset_snapshot_hash=dataset.snapshot_hash,
            evaluation_run_id=payload.evaluation_run_id,
        ),
    }


@router.get("/sample-reviews")
def list_sample_reviews(
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
    dataset_version_id: Annotated[str, Query(alias="datasetVersionId")],
    evaluation_run_id: Annotated[str | None, Query(alias="evaluationRunId")] = None,
) -> dict[str, object]:
    _require_review_role(user)
    dataset = _dataset(session, settings, dataset_version_id)
    statement = select(AIFieldReadinessSampleReview).where(
        AIFieldReadinessSampleReview.dataset_version_id == dataset.dataset_version_id,
        AIFieldReadinessSampleReview.dataset_snapshot_hash == dataset.snapshot_hash,
    )
    if evaluation_run_id:
        statement = statement.where(
            AIFieldReadinessSampleReview.evaluation_run_id == evaluation_run_id
        )
    rows = session.scalars(statement.order_by(AIFieldReadinessSampleReview.id)).all()
    independent_count_by_run = {
        row.evaluation_run_id: sum(
            1
            for candidate in rows
            if candidate.evaluation_run_id == row.evaluation_run_id
            and candidate.review_role == "INDEPENDENT"
        )
        for row in rows
    }
    return {
        "reviews": [
            _review_dict(
                row,
                include_decision=(
                    row.reviewer_id == user.user_id
                    or independent_count_by_run[row.evaluation_run_id] >= 2
                ),
            )
            for row in rows
        ],
        "summary": sample_review_summary(
            session,
            dataset_version_id=dataset.dataset_version_id,
            dataset_snapshot_hash=dataset.snapshot_hash,
            evaluation_run_id=evaluation_run_id,
        ),
    }
