using System.Text.Json;
using FlowNote.Windows.Core.ServerApi;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class ServerFieldCommentContractTests
{
    [Fact]
    public void DirectReviewRequestLeavesBaseRevisionUnspecified()
    {
        var request = new ServerFieldCommentReviewRequest
        {
            Status = "ANALYZED",
            AnalysisContent = "현장 기록을 분석함",
            TransitionReason = "분석 근거를 남김"
        };

        using var json = JsonDocument.Parse(JsonSerializer.Serialize(request));

        Assert.Equal(
            JsonValueKind.Null,
            json.RootElement.GetProperty("baseReviewRevision").ValueKind);
    }

    [Fact]
    public void SynchronizedReviewRequestKeepsKnownBaseRevision()
    {
        var request = new ServerFieldCommentReviewRequest
        {
            Status = "REVIEWED",
            BaseReviewRevision = 4,
            TransitionReason = "동기화 검토를 반영함"
        };

        using var json = JsonDocument.Parse(JsonSerializer.Serialize(request));

        Assert.Equal(
            4,
            json.RootElement.GetProperty("baseReviewRevision").GetInt32());
    }
}
