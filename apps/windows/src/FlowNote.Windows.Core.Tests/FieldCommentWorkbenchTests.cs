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
            LineText: "line-a",
            EquipmentText: "press-01",
            ProcessText: "forming",
            ErrorTypeText: "alignment",
            Overdue: true,
            Conflict: true,
            PriorityOrder: true,
            Limit: 200);

        service.SaveView(name, expected);

        var restarted = new FieldCommentService(new FlowNoteLocalDatabase(DatabasePath));
        var actual = Assert.Single(restarted.ListSavedViews(), item => item.Name == name).Filter;
        Assert.Equal(expected, actual);
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
