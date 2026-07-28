using System.Collections.ObjectModel;
using System.Net.Http;
using System.Windows;
using System.Windows.Controls;
using FlowNote.Windows.Core.Reports;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.App;

public partial class ReportDraftWindow : Window
{
    private readonly ReportDraftService reports;
    private readonly FlowNoteServerDocumentClient? serverReports;
    private readonly long targetFolderId;
    private readonly string actorName;
    private readonly ReportDraftWorkspace workspace = new();
    private IReadOnlyList<ReportSourceCandidateRecord>? frozenSources;

    public ReportDraftWindow(
        ReportDraftService reports,
        long targetFolderId,
        string actorName,
        FlowNoteServerDocumentClient? serverReports = null)
    {
        InitializeComponent();
        this.reports = reports;
        this.serverReports = serverReports;
        this.targetFolderId = targetFolderId;
        this.actorName = actorName;
        DataContext = workspace;
        Loaded += ReportDraftWindow_Loaded;
    }

    public bool DocumentSaved { get; private set; }

    private void ReportDraftWindow_Loaded(object sender, RoutedEventArgs e)
    {
        RefreshSources();
        StatusTextBlock.Text = "보고서 선정 FieldComment를 포함해 서로 다른 근거 유형을 최소 2종 선택하세요.";
    }

    private async void BuildDraftButton_Click(object sender, RoutedEventArgs e)
    {
        var selected = SelectedSources().ToList();
        if (!selected.Any(source => source.SourceType == "FIELD_COMMENT"))
        {
            StatusTextBlock.Text = "현장 코멘트 원천을 하나 이상 선택하세요.";
            return;
        }
        if (selected.Select(source => source.SourceType).Distinct(StringComparer.OrdinalIgnoreCase).Count() < 2)
        {
            StatusTextBlock.Text = "서로 다른 근거 유형을 최소 2종 선택하세요.";
            return;
        }

        if (serverReports is null)
        {
            StatusTextBlock.Text = "선택 근거를 고정하려면 서버 연결이 필요합니다. 원천과 선택 항목은 바뀌지 않았습니다. 다음: 서버 연결을 확인한 뒤 초안을 다시 만드세요.";
            return;
        }

        try
        {
            var freeze = await reports.FreezeServerSourcesAsync(serverReports, selected);
            workspace.Verifications.Clear();
            foreach (var item in freeze.Verifications)
            {
                workspace.Verifications.Add(item);
            }
            if (!freeze.Valid)
            {
                frozenSources = null;
                SourceSnapshotTextBlock.Text = $"변경된 근거 {freeze.Verifications.Count(item => !item.Valid)}건 · '고정 근거 확인'에서 원인을 확인하세요.";
                StatusTextBlock.Text = "선택한 근거가 바뀌어 초안을 만들지 않았습니다. 원천 기록은 그대로 보존됩니다. 다음: 코멘트 검토에서 최신 상태를 확인한 뒤 근거를 다시 선택하세요.";
                return;
            }

            frozenSources = freeze.Sources;
            DraftTextBox.Text = reports.BuildDraftContent(
                TitleTextBox.Text,
                SummaryTextBox.Text,
                frozenSources,
                actorName);
            SourceSnapshotTextBlock.Text =
                $"고정 원천 {frozenSources.Count}건 · 유형 {frozenSources.Select(item => item.SourceType).Distinct().Count()}종 · " +
                "저장 직전에 같은 근거를 다시 확인합니다.";
            StatusTextBlock.Text = $"선택 근거 {selected.Count}건을 고정해 초안을 만들었습니다. 원천 기록은 바뀌지 않습니다. 다음: 내용을 확인한 뒤 '보고서 저장'을 선택하세요.";
        }
        catch (Exception exception) when (exception is InvalidOperationException or HttpRequestException or TaskCanceledException)
        {
            frozenSources = null;
            StatusTextBlock.Text = "선택 근거를 고정하지 못해 초안을 만들지 않았습니다. 원천과 선택 항목은 바뀌지 않았습니다. 다음: 서버 연결과 최신 원천 상태를 확인한 뒤 다시 시도하세요.";
        }
    }

    private async void SaveDocumentButton_Click(object sender, RoutedEventArgs e)
    {
        var content = DraftTextBox.Text;
        if (string.IsNullOrWhiteSpace(content))
        {
            StatusTextBlock.Text = "먼저 초안을 만들어 선택 근거를 고정하세요.";
            return;
        }

        var selected = SelectedSources().ToList();
        if (frozenSources is null || !SameSelection(selected, frozenSources))
        {
            StatusTextBlock.Text = "선택 근거가 바뀌었거나 고정되지 않았습니다. 원천 기록은 바뀌지 않았습니다. 다음: 현재 근거로 초안을 다시 만드세요.";
            return;
        }
        try
        {
            var result = await reports.SaveDraftToServerAsync(
                serverReports,
                targetFolderId,
                TitleTextBox.Text,
                SummaryTextBox.Text,
                content,
                frozenSources,
                actorName);
            DocumentSaved = true;
            StatusTextBlock.Text = result.SyncResult.Success && !string.IsNullOrWhiteSpace(result.ReportId)
                ? $"보고서를 서버에 저장했습니다. 선택 근거 {result.Saved?.Sources.Count ?? selected.Count}건과 원천 연결을 보존했습니다. 다음: '고정 근거 확인'에서 연결 상태를 확인하세요."
                : "보고서 원본은 이 PC에 저장했고 서버 전송은 대기 중입니다. 선택 근거와 재전송 항목은 보존됩니다. 다음: 이력의 동기화 큐에서 사유를 확인하고 다시 시도하세요.";
            if (result.Saved is not null)
            {
                var traceLines = string.Join(Environment.NewLine, result.Saved.Sources.Select(source =>
                    $"- {source.SourceType} · {source.SourceId} · 버전 {source.SourceVersionId} · " +
                    $"revision {source.SourceRevision?.ToString() ?? "없음"} · trace {source.TraceId} · hash {source.SourceHashSha256}"));
                MessageBox.Show(
                    this,
                    $"보고서 {result.Saved.ReportId} → 생성 문서 {result.Saved.GeneratedDocumentId ?? "없음"}{Environment.NewLine}" +
                    $"고정 근거 {result.Saved.Sources.Count}건{Environment.NewLine}{traceLines}",
                    "보고서 → 원천/버전 역추적",
                    MessageBoxButton.OK,
                    MessageBoxImage.Information);
            }
            return;
        }
        catch (Exception exception) when (exception is InvalidOperationException or HttpRequestException or TaskCanceledException)
        {
            frozenSources = null;
            SourceSnapshotTextBlock.Text = "저장 직전 선택 근거가 바뀌었거나 서버 확인이 끝나지 않았습니다.";
            StatusTextBlock.Text = "보고서를 서버에 저장하지 않았습니다. 원천 기록과 기존 보고서는 그대로 보존됩니다. 다음: 코멘트 검토에서 최신 상태를 확인하고 근거를 다시 선택한 뒤 초안을 새로 만드세요.";
        }
    }

    private void SourceGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!IsLoaded || frozenSources is null)
        {
            return;
        }
        if (!SameSelection(SelectedSources().ToList(), frozenSources))
        {
            frozenSources = null;
            workspace.Verifications.Clear();
            SourceSnapshotTextBlock.Text = "선택 근거가 변경되었습니다. 초안을 다시 만들어 현재 근거를 고정하세요.";
        }
    }

    private void ShowVerificationButton_Click(object sender, RoutedEventArgs e)
    {
        if (workspace.Verifications.Count == 0)
        {
            StatusTextBlock.Text = "먼저 초안을 만들어 서버의 선택 근거를 확인하세요.";
            return;
        }
        new ReportSourceVerificationWindow(workspace.Verifications) { Owner = this }.ShowDialog();
    }

    private static bool SameSelection(
        IReadOnlyCollection<ReportSourceCandidateRecord> selected,
        IReadOnlyCollection<ReportSourceCandidateRecord> frozen)
    {
        var selectedKeys = selected
            .Select(item => $"{item.SourceType}|{item.SourceId}")
            .ToHashSet(StringComparer.Ordinal);
        var frozenKeys = frozen
            .Select(item => $"{item.SourceType}|{item.SourceId}")
            .ToHashSet(StringComparer.Ordinal);
        return selected.Count == frozen.Count && selectedKeys.SetEquals(frozenKeys);
    }

    private void RefreshSources()
    {
        workspace.FieldComments.Clear();
        foreach (var source in reports.ListFieldCommentSources())
        {
            workspace.FieldComments.Add(source);
        }

        workspace.Documents.Clear();
        foreach (var source in reports.ListDocumentSources())
        {
            workspace.Documents.Add(source);
        }

        workspace.WorkHistory.Clear();
        foreach (var source in reports.ListWorkSequenceSources())
        {
            workspace.WorkHistory.Add(source);
        }
    }

    private IEnumerable<ReportSourceCandidateRecord> SelectedSources()
    {
        foreach (ReportSourceCandidateRecord source in FieldCommentGrid.SelectedItems)
        {
            yield return source;
        }

        foreach (ReportSourceCandidateRecord source in DocumentGrid.SelectedItems)
        {
            yield return source;
        }

        foreach (ReportSourceCandidateRecord source in WorkHistoryGrid.SelectedItems)
        {
            yield return source;
        }
    }

    private sealed class ReportDraftWorkspace
    {
        public ObservableCollection<ReportSourceCandidateRecord> FieldComments { get; } = [];

        public ObservableCollection<ReportSourceCandidateRecord> Documents { get; } = [];

        public ObservableCollection<ReportSourceCandidateRecord> WorkHistory { get; } = [];

        public ObservableCollection<ReportSourceVerificationRecord> Verifications { get; } = [];
    }
}
