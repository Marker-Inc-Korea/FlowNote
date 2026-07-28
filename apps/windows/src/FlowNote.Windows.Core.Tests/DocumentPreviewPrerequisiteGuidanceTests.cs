using FlowNote.Windows.Core.Documents;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class DocumentPreviewPrerequisiteGuidanceTests
{
    [Fact]
    public void WebView2FailureShowsActionableKoreanGuidance()
    {
        var message = DocumentPreviewPolicy.WebView2RuntimeUnavailableMessage;

        Assert.Contains("Microsoft Edge WebView2 Runtime", message);
        Assert.Contains("누락 항목:", message);
        Assert.Contains("보존된 데이터:", message);
        Assert.Contains("담당자:", message);
        Assert.Contains("다음 조치:", message);
        Assert.Contains("다시 실행", message);
    }
}
