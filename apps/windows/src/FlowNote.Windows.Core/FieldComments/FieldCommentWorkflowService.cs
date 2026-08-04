namespace FlowNote.Windows.Core.FieldComments;

internal static class FieldCommentWorkflowService
{
internal static readonly IReadOnlyList<string> ReviewStatuses =
    [
        "NEW",
        "ASSIGNED",
        "NEEDS_REVIEW",
        "ANALYZED",
        "REVIEWED",
        "SELECTED",
        "EXCLUDED",
        "ARCHIVED"
    ];
    internal static void ValidateReviewStatus(string status)
    {
        if (!ReviewStatuses.Contains(status, StringComparer.Ordinal))
        {
            throw new ArgumentOutOfRangeException(nameof(status), "Unsupported FieldComment status.");
        }
    }

    internal static void ValidateTransition(
        string currentStatus,
        string targetStatus,
        string? normalizedContent,
        string? analysisContent,
        string? reason)
    {
        if (string.Equals(currentStatus, targetStatus, StringComparison.Ordinal))
        {
            return;
        }

        var allowed = currentStatus switch
        {
            "NEW" => new[] { "ASSIGNED", "ANALYZED", "NEEDS_REVIEW", "EXCLUDED" },
            "ASSIGNED" => new[] { "NEW", "ANALYZED", "NEEDS_REVIEW", "EXCLUDED" },
            "NEEDS_REVIEW" => new[] { "NEW", "ASSIGNED", "ANALYZED", "EXCLUDED" },
            "ANALYZED" => new[] { "NEW", "NEEDS_REVIEW", "REVIEWED", "EXCLUDED" },
            "REVIEWED" => new[] { "ANALYZED", "SELECTED", "EXCLUDED" },
            "SELECTED" => new[] { "REVIEWED", "EXCLUDED", "ARCHIVED" },
            "EXCLUDED" => new[] { "NEW", "ARCHIVED" },
            "ARCHIVED" => new[] { "EXCLUDED" },
            _ => []
        };
        if (!allowed.Contains(targetStatus, StringComparer.Ordinal))
        {
            throw new InvalidOperationException($"허용되지 않은 상태 전이입니다: {currentStatus} → {targetStatus}");
        }
        if (string.IsNullOrWhiteSpace(reason) || reason.Length < 3)
        {
            throw new InvalidOperationException("상태 변경 사유를 3자 이상 입력하세요.");
        }
        if (targetStatus is "ANALYZED" or "REVIEWED" or "SELECTED" && string.IsNullOrWhiteSpace(analysisContent))
        {
            throw new InvalidOperationException("분석완료 이후 상태에는 분석 내용이 필요합니다.");
        }
        if (targetStatus is "REVIEWED" or "SELECTED" && string.IsNullOrWhiteSpace(normalizedContent))
        {
            throw new InvalidOperationException("검토완료 이후 상태에는 정리 내용이 필요합니다.");
        }
    }


}
