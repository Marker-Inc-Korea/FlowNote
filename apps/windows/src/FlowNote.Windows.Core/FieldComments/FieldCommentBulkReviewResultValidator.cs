using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.Core.FieldComments;

public static class FieldCommentBulkReviewResultValidator
{
    public static void ValidatePreview(
        ServerFieldCommentBulkReviewResponse response,
        IReadOnlyCollection<ServerFieldCommentBulkReviewItemRequest> requestedItems)
    {
        ValidateIdentity(response, requestedItems);
        var deniedCount = response.Items.Count(item => !item.Allowed);
        if (response.SuccessCount != 0 || response.FailureCount != deniedCount)
        {
            throw new InvalidOperationException("일괄 사전검증의 실행 불가 행과 실패 합계가 일치하지 않습니다.");
        }
    }

    public static void Validate(
        ServerFieldCommentBulkReviewResponse response,
        IReadOnlyCollection<ServerFieldCommentBulkReviewItemRequest> requestedItems)
    {
        ValidateIdentity(response, requestedItems);
        if (response.SuccessCount + response.FailureCount != requestedItems.Count)
        {
            throw new InvalidOperationException(
                $"일괄 처리 결과 합계가 요청과 다릅니다. 요청 {requestedItems.Count}건, " +
                $"응답 {response.RequestedCount}건, 성공 {response.SuccessCount}건, 실패 {response.FailureCount}건, " +
                $"결과 행 {response.Items.Count}건입니다.");
        }

        var successCount = response.Items.Count(item => item.Success is true);
        if (successCount != response.SuccessCount ||
            response.Items.Count - successCount != response.FailureCount)
        {
            throw new InvalidOperationException("일괄 처리 결과 행의 성공/실패 판정과 응답 합계가 일치하지 않습니다.");
        }
    }

    public static IReadOnlyList<string> GetRetryTargetIds(
        ServerFieldCommentBulkReviewResponse response) =>
        response.Items
            .Where(item => item.Success is false)
            .Select(item => item.CommentId)
            .ToList();

    private static void ValidateIdentity(
        ServerFieldCommentBulkReviewResponse response,
        IReadOnlyCollection<ServerFieldCommentBulkReviewItemRequest> requestedItems)
    {
        if (response.RequestedCount != requestedItems.Count || response.Items.Count != requestedItems.Count)
        {
            throw new InvalidOperationException(
                $"일괄 처리 결과 행 수가 요청과 다릅니다. 요청 {requestedItems.Count}건, " +
                $"응답 {response.RequestedCount}건, 결과 행 {response.Items.Count}건입니다.");
        }
        var requestedIds = requestedItems.Select(item => item.CommentId).ToHashSet(StringComparer.Ordinal);
        var resultIds = response.Items.Select(item => item.CommentId).ToList();
        if (resultIds.Distinct(StringComparer.Ordinal).Count() != resultIds.Count ||
            !requestedIds.SetEquals(resultIds))
        {
            throw new InvalidOperationException("일괄 처리 결과의 FieldComment ID가 요청과 일치하지 않습니다.");
        }
    }
}
