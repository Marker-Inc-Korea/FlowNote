using FlowNote.Windows.Core.Documents;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class DocumentPreviewPrerequisiteGuidanceTests
{
    [Fact]
    public void WebView2FailureShowsActionableKoreanGuidance()
    {
        var failure = DocumentPreviewFailure.Create(
            DocumentPreviewKind.Pdf,
            DocumentPreviewFailureCategory.ViewerUnavailable);

        Assert.Equal("PDF", failure.FileType);
        Assert.Contains("뷰어", failure.CategoryName);
        Assert.Contains("보존", DocumentPreviewFailure.PreservationMessage);
        Assert.Contains("Windows 설치 담당자", failure.NextAction);
        Assert.Contains("WebView2 Runtime", failure.NextAction);
    }
}
