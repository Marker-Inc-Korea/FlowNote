using System.Net.Http;
using System.Windows;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.App;

public partial class ReportDetailWindow : Window
{
    private readonly FlowNoteServerDocumentClient? serverClient;
    private ServerReportResponse report;

    public ReportDetailWindow(
        ServerReportResponse report,
        FlowNoteServerDocumentClient? serverClient)
    {
        InitializeComponent();
        this.report = report;
        this.serverClient = serverClient;
        DataContext = report;
    }

    private async void OpenSourceButton_Click(object sender, RoutedEventArgs e)
    {
        if (SourceGrid.SelectedItem is not ServerReportSourceResponse source)
        {
            StatusTextBlock.Text = "돌아갈 원천을 선택하세요.";
            return;
        }
        if (serverClient is null)
        {
            StatusTextBlock.Text = "서버 연결이 없어 원천 상세를 열 수 없습니다. 고정 ID와 version/hash는 현재 화면에 보존됩니다.";
            return;
        }

        try
        {
            if (source.SourceType == "FIELD_COMMENT")
            {
                var trace = await serverClient.GetFieldCommentTraceabilityAsync(source.SourceId);
                new FieldCommentTraceabilityWindow(trace) { Owner = this }.ShowDialog();
                return;
            }
            if (source.SourceType == "DOCUMENT")
            {
                var current = await serverClient.GetDocumentAsync(source.SourceId);
                MessageBox.Show(
                    this,
                    $"보고서가 사용한 버전: {source.SourceVersionId}\n" +
                    $"당시 hash: {source.SourceHashSha256}\n" +
                    $"현재 공개 버전: {current.PublishedVersionId ?? "없음"}\n" +
                    $"현재 문서 revision: {current.Revision}",
                    $"문서 원천 · {current.Title}",
                    MessageBoxButton.OK,
                    MessageBoxImage.Information);
                return;
            }

            MessageBox.Show(
                this,
                $"원천 유형: {source.SourceType}\n원천 ID: {source.SourceId}\n" +
                $"당시 version: {source.SourceVersionId ?? "없음"}\n" +
                $"당시 revision: {source.SourceRevision?.ToString() ?? "없음"}\n" +
                $"trace ID: {source.TraceId}\n당시 hash: {source.SourceHashSha256}",
                "고정 원천 위치",
                MessageBoxButton.OK,
                MessageBoxImage.Information);
        }
        catch (Exception exception) when (exception is InvalidOperationException or HttpRequestException or TaskCanceledException)
        {
            StatusTextBlock.Text = $"원천 상세를 열지 못했습니다. 고정 위치는 보존됩니다: {exception.Message}";
        }
    }

    private async void ArchiveButton_Click(object sender, RoutedEventArgs e)
    {
        if (serverClient is null || report.Status != "APPROVED")
        {
            StatusTextBlock.Text = "서버에 확정된 보고서만 보관할 수 있습니다.";
            return;
        }

        try
        {
            report = await serverClient.SaveReportAsync(new ServerReportSaveRequest
            {
                DraftReportId = report.ReportId,
                BaseReportRevision = report.ReportRevision,
                MutationKey = $"wpf:report-archive:{report.ReportId}:r{report.ReportRevision}",
                ReportStatus = "ARCHIVED",
                SourceSetHashSha256 = report.SourceSetHashSha256
            });
            DataContext = report;
            StatusTextBlock.Text = "보고서와 연결 문서를 보관 상태로 전환했습니다. 고정 원천과 receipt는 유지됩니다.";
        }
        catch (Exception exception) when (exception is InvalidOperationException or HttpRequestException or TaskCanceledException)
        {
            StatusTextBlock.Text = $"보고서를 보관하지 못했습니다. 기존 보고서와 원천은 유지됩니다: {exception.Message}";
        }
    }
}
