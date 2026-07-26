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
}
