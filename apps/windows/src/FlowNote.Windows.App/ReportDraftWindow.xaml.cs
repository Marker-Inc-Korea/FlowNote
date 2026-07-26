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
            StatusTextBlock.Text = "원천 version/revision/hash를 고정하려면 서버 연결이 필요합니다.";
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
                SourceSnapshotTextBlock.Text = $"원천 검증 실패 {freeze.Verifications.Count(item => !item.Valid)}건 · 고정 근거 확인에서 원인을 확인하세요.";
                StatusTextBlock.Text = "원천 상태·version·revision·hash가 적격하지 않아 초안을 만들지 않았습니다.";
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
                "저장 직전에 같은 snapshot을 다시 검증합니다.";
            StatusTextBlock.Text = $"선택한 원천 {selected.Count}건의 version/revision/hash를 고정해 초안을 생성했습니다.";
        }
        catch (Exception exception) when (exception is InvalidOperationException or HttpRequestException or TaskCanceledException)
        {
            frozenSources = null;
            StatusTextBlock.Text = $"보고서 원천 고정에 실패했습니다. {exception.Message}";
        }
    }

    private async void SaveDocumentButton_Click(object sender, RoutedEventArgs e)
    {
        var content = DraftTextBox.Text;
        if (string.IsNullOrWhiteSpace(content))
        {
            StatusTextBlock.Text = "먼저 초안을 생성해 원천 snapshot을 고정하세요.";
            return;
        }

        var selected = SelectedSources().ToList();
        if (frozenSources is null || !SameSelection(selected, frozenSources))
        {
            StatusTextBlock.Text = "선택 원천이 바뀌었거나 고정 snapshot이 없습니다. 초안을 다시 생성하세요.";
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
                ? $"서버 보고서를 저장했습니다: {result.ReportId} / {result.GeneratedDocumentId ?? "생성 문서 없음"}"
                : $"보고서 문서를 로컬에 저장하고 서버 저장 재시도 큐에 보관했습니다. {result.SyncResult.Message}";
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
            StatusTextBlock.Text = $"보고서 저장에 실패했습니다. 로컬 데이터와 동기화 큐를 확인하세요. {exception.Message}";
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
            SourceSnapshotTextBlock.Text = "원천 선택이 변경되었습니다. 초안을 다시 생성해 snapshot을 고정하세요.";
        }
    }

    private void ShowVerificationButton_Click(object sender, RoutedEventArgs e)
    {
        if (workspace.Verifications.Count == 0)
        {
            StatusTextBlock.Text = "먼저 초안을 생성해 서버 원천을 검증하세요.";
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
