using System.Windows;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.App;

public partial class FieldCommentBulkPreviewWindow : Window
{
    public FieldCommentBulkPreviewWindow(ServerFieldCommentBulkReviewResponse preview)
    {
        InitializeComponent();
        DataContext = preview.Items;
        var isExecutionResult = preview.Items.Any(item => item.Success is not null);
        if (isExecutionResult)
        {
            SummaryTextBlock.Text =
                $"요청 {preview.RequestedCount}건 · 성공 {preview.SuccessCount}건 · 실패 {preview.FailureCount}건 · " +
                "성공 항목은 재전송하지 않고 실패 항목만 재시도 대상으로 표시합니다.";
            CancelButton.Visibility = Visibility.Collapsed;
            ExecuteButton.Content = "결과 확인";
        }
        else
        {
            var allowed = preview.Items.Count(item => item.Allowed);
            SummaryTextBlock.Text =
                $"요청 {preview.RequestedCount}건 · 실행 가능 {allowed}건 · 실행 불가 {preview.FailureCount}건. " +
                "실패 항목은 실행하지 않으며 결과 행을 보존합니다.";
        }
    }

    private void ExecuteButton_Click(object sender, RoutedEventArgs e)
    {
        DialogResult = true;
    }
}
