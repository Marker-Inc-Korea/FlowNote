using System.Windows;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.App;

public partial class FieldCommentBulkPreviewWindow : Window
{
    public FieldCommentBulkPreviewWindow(ServerFieldCommentBulkReviewResponse preview)
    {
        InitializeComponent();
        DataContext = preview.Items;
        var allowed = preview.Items.Count(item => item.Allowed);
        SummaryTextBlock.Text = $"요청 {preview.RequestedCount}건 · 실행 가능 {allowed}건 · 실행 불가 {preview.FailureCount}건. 실패 항목은 실행하지 않으며 결과 행을 보존합니다.";
    }

    private void ExecuteButton_Click(object sender, RoutedEventArgs e)
    {
        DialogResult = true;
    }
}
