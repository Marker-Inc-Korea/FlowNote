using System.Net.Http;
using System.Windows;
using FlowNote.Windows.Core.Reports;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.App;

public partial class ReportCorrectionSourceWindow : Window
{
    private readonly ReportDraftService reports;
    private readonly FlowNoteServerDocumentClient serverClient;

    public ReportCorrectionSourceWindow(
        ReportDraftService reports,
        FlowNoteServerDocumentClient serverClient,
        ServerReportResponse baseReport)
    {
        InitializeComponent();
        this.reports = reports;
        this.serverClient = serverClient;
        var candidates = reports.ListFieldCommentSources()
            .Concat(reports.ListDocumentSources())
            .Concat(reports.ListWorkSequenceSources())
            .ToList();
        SourceGrid.ItemsSource = candidates;
        var baseIds = baseReport.Sources.Select(item => item.SourceId).ToHashSet(StringComparer.Ordinal);
        Loaded += (_, _) =>
        {
            foreach (var candidate in candidates.Where(item =>
                         baseIds.Contains(item.ServerSourceId ?? item.SourceId)))
            {
                SourceGrid.SelectedItems.Add(candidate);
            }
        };
    }

    public IReadOnlyList<ReportSourceCandidateRecord>? SelectedSources { get; private set; }

    private async void ConfirmButton_Click(object sender, RoutedEventArgs e)
    {
        var selected = SourceGrid.SelectedItems.Cast<ReportSourceCandidateRecord>().ToList();
        if (selected.Select(item => item.SourceType).Distinct(StringComparer.OrdinalIgnoreCase).Count() < 2)
        {
            StatusTextBlock.Text = "서로 다른 원천 유형을 2종 이상 선택하세요.";
            return;
        }
        try
        {
            var frozen = await reports.FreezeServerSourcesAsync(serverClient, selected);
            if (!frozen.Valid)
            {
                StatusTextBlock.Text = "변경되었거나 권한이 없는 원천이 있습니다. 담당 검토자와 현재 원천을 확인하세요.";
                return;
            }
            SelectedSources = frozen.Sources;
            DialogResult = true;
        }
        catch (Exception exception) when (exception is InvalidOperationException or HttpRequestException or TaskCanceledException)
        {
            StatusTextBlock.Text = $"현재 원천을 확인하지 못했습니다: {exception.Message}";
        }
    }
}
