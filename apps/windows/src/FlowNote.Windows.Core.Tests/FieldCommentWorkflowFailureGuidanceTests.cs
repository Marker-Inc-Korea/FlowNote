using System.Net;
using FlowNote.Windows.Core.FieldComments;
using FlowNote.Windows.Core.ServerApi;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class FieldCommentWorkflowFailureGuidanceTests
{
    [Theory]
    [InlineData(true, null, "재전송 안 함")]
    [InlineData(false, "FIELD_COMMENT_STALE_REVIEW_REVISION", "재조회 후 다시 선택")]
    [InlineData(false, "HTTP_403", "관리자 확인 후 다시 선택")]
    [InlineData(false, "OTHER", "실패 항목만 다시 선택")]
    public void BulkRowsExposeWhetherTheyAreRetryTargets(
        bool success,
        string? failureCode,
        string expected)
    {
        var row = new ServerFieldCommentBulkReviewItemResponse
        {
            CommentId = "comment-1",
            Success = success,
            FailureCode = failureCode
        };

        Assert.Equal(expected, row.RetryTargetLabel);
    }

    [Fact]
    public void BulkRetryTargetsExcludeSuccessfulRows()
    {
        var response = new ServerFieldCommentBulkReviewResponse
        {
            RequestedCount = 3,
            SuccessCount = 1,
            FailureCount = 2,
            Items =
            [
                new() { CommentId = "comment-success", Success = true },
                new() { CommentId = "comment-stale", Success = false },
                new() { CommentId = "comment-denied", Success = false }
            ]
        };

        var retryTargets =
            FieldCommentBulkReviewResultValidator.GetRetryTargetIds(response);

        Assert.Equal(["comment-stale", "comment-denied"], retryTargets);
        Assert.DoesNotContain("comment-success", retryTargets);
    }

    [Fact]
    public void PermissionFailureUsesTheRequiredFourPartOrder()
    {
        var message = WorkflowFailureGuidance.FromServerException(
            new FlowNoteServerAccessException(
                HttpStatusCode.Forbidden,
                "PERMISSION_DENIED",
                "denied"),
            "검토 내용을 저장하지 못했습니다.",
            "원천 코멘트와 기존 검토 이력",
            "목록을 다시 조회하세요.");

        AssertFourPartOrder(message);
        Assert.Contains("현장 관리자", message);
        Assert.Contains("원천 코멘트와 기존 검토 이력", message);
    }

    [Fact]
    public void StaleRevisionPreservesOriginalAndRequiresRefreshInsteadOfOverwrite()
    {
        var message = WorkflowFailureGuidance.FromServerException(
            new FlowNoteServerConflictException(
                "FIELD_COMMENT_STALE_REVIEW_REVISION",
                "stale",
                3,
                4,
                "ANALYZED",
                null,
                null,
                "{}"),
            "검토 내용을 저장하지 못했습니다.",
            "원천 코멘트와 로컬 입력",
            "다시 시도하세요.");

        AssertFourPartOrder(message);
        Assert.Contains("서버 최신 revision", message);
        Assert.Contains("서버 원문과 로컬 입력을 비교", message);
        Assert.DoesNotContain("덮어쓰기", message);
    }

    private static void AssertFourPartOrder(string message)
    {
        var failure = message.IndexOf("무엇이 실패했는지:", StringComparison.Ordinal);
        var preserved = message.IndexOf("무엇이 보존됐는지:", StringComparison.Ordinal);
        var owner = message.IndexOf("누가 처리해야 하는지:", StringComparison.Ordinal);
        var action = message.IndexOf("사용자가 지금 할 수 있는 일:", StringComparison.Ordinal);

        Assert.True(failure >= 0);
        Assert.True(failure < preserved);
        Assert.True(preserved < owner);
        Assert.True(owner < action);
    }
}
