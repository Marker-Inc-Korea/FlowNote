using FlowNote.Windows.Core.FieldComments;
using FlowNote.Windows.Core.Storage;
using FlowNote.Windows.Core.ServerApi;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class FieldCommentWorkbenchTests
{
    private static readonly string DatabasePath = Path.Combine(
        FlowNoteLocalDatabase.DefaultDataDirectory,
        "field-comment-workbench-core-tests.sqlite");

    [Fact]
    public void SavedViewPersistsConflictAndOperationalFiltersAcrossRestart()
    {
        var database = new FlowNoteLocalDatabase(DatabasePath);
        database.Initialize();
        var service = new FieldCommentService(database);
        var name = $"상충 우선 보기 {Guid.NewGuid():N}";
        var expected = new FieldCommentReviewFilter(
            Status: "NEEDS_REVIEW",
            AssignedTo: "user-admin",
            AssignedRole: "admin",
            SignalLevel: "red",
            ChannelText: "품질 위험",
            DocumentVersionText: "3",
            LineText: "line-a",
            EquipmentText: "press-01",
            ProcessText: "forming",
            ErrorTypeText: "alignment",
            Overdue: true,
            Conflict: true,
            ReviewDueFrom: new DateTime(2026, 8, 1),
            ReviewDueTo: new DateTime(2026, 8, 31),
            PriorityOrder: true,
            Limit: 200);

        service.SaveView(name, expected);

        var restarted = new FieldCommentService(new FlowNoteLocalDatabase(DatabasePath));
        var actual = Assert.Single(restarted.ListSavedViews(), item => item.Name == name).Filter;
        Assert.Equal(expected, actual);
    }

    [Fact]
    public void SingleReviewSavePersistsFieldsAndAuditHistory()
    {
        var database = new FlowNoteLocalDatabase(DatabasePath);
        database.Initialize();
        var service = new FieldCommentService(database);
        var commentId = $"comment-review-save-{Guid.NewGuid():N}";
        using (var connection = database.OpenConnection())
        using (var insert = connection.CreateCommand())
        {
            insert.CommandText = """
                INSERT INTO field_comments (
                    comment_id, comment_type, input_mode, raw_content,
                    author_name, entry_source, status, created_at)
                VALUES (
                    $comment_id, 'issue', 'free_text', '원천 기록은 변경하지 않습니다.',
                    '현장 작성자', 'field_user', 'NEW', $created_at);
                """;
            insert.Parameters.AddWithValue("$comment_id", commentId);
            insert.Parameters.AddWithValue("$created_at", DateTime.UtcNow.ToString("O"));
            insert.ExecuteNonQuery();
        }

        var updated = service.UpdateReview(
            commentId,
            "관리자가 정리한 내용",
            "후속 검토가 필요한 분석 내용",
            "ASSIGNED",
            "검토 관리자",
            "담당자를 지정함",
            assignedTo: "품질 관리자",
            conflictFlag: true,
            conflictBasis: "현장 기록과 작업표준이 다름");

        Assert.Equal("ASSIGNED", updated.Status);
        Assert.Equal("관리자가 정리한 내용", updated.NormalizedContent);
        Assert.Equal("후속 검토가 필요한 분석 내용", updated.AnalysisContent);
        Assert.Equal("품질 관리자", updated.AssignedTo);
        Assert.Equal("담당자를 지정함", updated.LastTransitionReason);
        Assert.True(updated.ConflictFlag);
        Assert.Equal("현장 기록과 작업표준이 다름", updated.ConflictBasis);

        using var verifyConnection = database.OpenConnection();
        using var history = verifyConnection.CreateCommand();
        history.CommandText = """
            SELECT COUNT(*)
            FROM activity_history
            WHERE event_type = 'field_comment.review_updated'
              AND target_id = $comment_id;
            """;
        history.Parameters.AddWithValue("$comment_id", commentId);
        Assert.Equal(1L, Convert.ToInt64(history.ExecuteScalar()));
    }

    [Fact]
    public void BulkResultRequiresSuccessAndFailureCountsToEqualRequestCount()
    {
        var requestItems = new[]
        {
            new ServerFieldCommentBulkReviewItemRequest { CommentId = "comment-1", BaseReviewRevision = 1, MutationKey = "m1" },
            new ServerFieldCommentBulkReviewItemRequest { CommentId = "comment-2", BaseReviewRevision = 1, MutationKey = "m2" }
        };
        var response = new ServerFieldCommentBulkReviewResponse
        {
            RequestedCount = 2,
            SuccessCount = 1,
            FailureCount = 1,
            Items =
            [
                new ServerFieldCommentBulkReviewItemResponse { CommentId = "comment-1", Success = true },
                new ServerFieldCommentBulkReviewItemResponse { CommentId = "comment-2", Success = false }
            ]
        };

        FieldCommentBulkReviewResultValidator.Validate(response, requestItems);
    }

    [Fact]
    public void BulkResultRejectsMissingOrHiddenPartialFailureRows()
    {
        var requestItems = new[]
        {
            new ServerFieldCommentBulkReviewItemRequest { CommentId = "comment-1", BaseReviewRevision = 1, MutationKey = "m1" },
            new ServerFieldCommentBulkReviewItemRequest { CommentId = "comment-2", BaseReviewRevision = 1, MutationKey = "m2" }
        };
        var response = new ServerFieldCommentBulkReviewResponse
        {
            RequestedCount = 2,
            SuccessCount = 1,
            FailureCount = 0,
            Items =
            [
                new ServerFieldCommentBulkReviewItemResponse { CommentId = "comment-1", Success = true }
            ]
        };

        Assert.Throws<InvalidOperationException>(
            () => FieldCommentBulkReviewResultValidator.Validate(response, requestItems));
    }

    [Fact]
    public void BulkPreviewCountsOnlyDeniedRowsAsFailures()
    {
        var requestItems = new[]
        {
            new ServerFieldCommentBulkReviewItemRequest { CommentId = "comment-1", BaseReviewRevision = 1, MutationKey = "m1" },
            new ServerFieldCommentBulkReviewItemRequest { CommentId = "comment-2", BaseReviewRevision = 1, MutationKey = "m2" }
        };
        var response = new ServerFieldCommentBulkReviewResponse
        {
            RequestedCount = 2,
            SuccessCount = 0,
            FailureCount = 1,
            Items =
            [
                new ServerFieldCommentBulkReviewItemResponse { CommentId = "comment-1", Allowed = true },
                new ServerFieldCommentBulkReviewItemResponse { CommentId = "comment-2", Allowed = false }
            ]
        };

        FieldCommentBulkReviewResultValidator.ValidatePreview(response, requestItems);
    }

    [Fact]
    public void BulkFailureGuidanceUsesFourPartOrderAndDoesNotOfferOverwrite()
    {
        var stale = new ServerFieldCommentBulkReviewItemResponse
        {
            CommentId = "comment-stale",
            Success = false,
            FailureCode = "FIELD_COMMENT_STALE_REVIEW_REVISION"
        };

        Assert.Contains("무엇이 실패했는지:", stale.RecoveryGuidance);
        Assert.Contains("무엇이 보존됐는지:", stale.RecoveryGuidance);
        Assert.Contains("누가 처리해야 하는지:", stale.RecoveryGuidance);
        Assert.Contains("사용자가 지금 할 수 있는 일:", stale.RecoveryGuidance);
        Assert.Contains("원문을 비교", stale.RecoveryGuidance);
        Assert.DoesNotContain("자동 덮어쓰기", stale.RecoveryGuidance);
    }
}
