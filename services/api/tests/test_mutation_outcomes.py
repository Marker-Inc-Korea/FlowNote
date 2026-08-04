from app.api.v1.field_comment_contracts import (
    FieldCommentBulkReviewItemResponse,
    FieldCommentBulkReviewResponse,
)
from app.services.field_comment_review_service import bulk_review_outcome
from app.services.mutation_outcomes import MutationOutcomeStatus


def test_bulk_partial_outcome_retries_only_failed_items() -> None:
    response = FieldCommentBulkReviewResponse(
        requested_count=2,
        success_count=1,
        failure_count=1,
        items=[
            FieldCommentBulkReviewItemResponse(
                comment_id="comment-success",
                allowed=True,
                success=True,
            ),
            FieldCommentBulkReviewItemResponse(
                comment_id="comment-failed",
                allowed=False,
                success=False,
                failure_code="FIELD_COMMENT_STALE_REVIEW_REVISION",
            ),
        ],
    )

    outcome = bulk_review_outcome(response)

    assert outcome.schema_version == "mutation-outcome-v1"
    assert outcome.status == MutationOutcomeStatus.PARTIAL_SUCCESS
    assert outcome.value is response
    assert outcome.source_preserved is True
    assert outcome.retry_item_ids == ("comment-failed",)
    assert "comment-success" not in outcome.retry_item_ids


def test_bulk_success_outcome_has_no_retry_items() -> None:
    response = FieldCommentBulkReviewResponse(
        requested_count=1,
        success_count=1,
        failure_count=0,
        items=[
            FieldCommentBulkReviewItemResponse(
                comment_id="comment-success",
                allowed=True,
                success=True,
            )
        ],
    )

    outcome = bulk_review_outcome(response)

    assert outcome.status == MutationOutcomeStatus.SUCCESS
    assert outcome.retry_item_ids == ()


def test_bulk_rejected_outcome_keeps_every_failed_item() -> None:
    response = FieldCommentBulkReviewResponse(
        requested_count=1,
        success_count=0,
        failure_count=1,
        items=[
            FieldCommentBulkReviewItemResponse(
                comment_id="comment-failed",
                allowed=False,
                success=False,
            )
        ],
    )

    outcome = bulk_review_outcome(response)

    assert outcome.status == MutationOutcomeStatus.REJECTED
    assert outcome.retry_item_ids == ("comment-failed",)
