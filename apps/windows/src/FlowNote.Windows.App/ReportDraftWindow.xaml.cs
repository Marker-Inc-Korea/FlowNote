using System.Collections.ObjectModel;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
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
    private readonly IReadOnlySet<string> initialFieldCommentIds;
    private readonly ReportDraftWorkspace workspace = new();
    private IReadOnlyList<ReportSourceCandidateRecord>? frozenSources;
    private ServerReportResponse? serverWorkflowReport;
    private string? reviewedEditorFingerprint;

    public ReportDraftWindow(
        ReportDraftService reports,
        long targetFolderId,
        string actorName,
        FlowNoteServerDocumentClient? serverReports = null,
        IEnumerable<string>? initialFieldCommentIds = null)
    {
        InitializeComponent();
        this.reports = reports;
        this.serverReports = serverReports;
        this.targetFolderId = targetFolderId;
        this.actorName = actorName;
        this.initialFieldCommentIds = (initialFieldCommentIds ?? [])
            .ToHashSet(StringComparer.Ordinal);
        DataContext = workspace;
        Loaded += ReportDraftWindow_Loaded;
    }

    public bool DocumentSaved { get; private set; }

    private async void ReportDraftWindow_Loaded(object sender, RoutedEventArgs e)
    {
        StatusTextBlock.Text = "보고서 선정 FieldComment를 포함해 서로 다른 근거 유형을 최소 2종 선택하세요.";
        RefreshSources();
        SelectInitialFieldComments();
        await RefreshExistingReportSourcesAsync();
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
            StatusTextBlock.Text = WorkflowFailureGuidance.Format(
                "서버 연결이 없어 선택 근거를 고정하지 못했습니다.",
                "원천 기록과 현재 선택 항목",
                "현재 사용자",
                "서버 주소와 로그인을 확인한 뒤 초안을 다시 만드세요.");
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
            var draftContent = reports.BuildDraftContent(
                TitleTextBox.Text,
                SummaryTextBox.Text,
                frozenSources,
                actorName);
            serverWorkflowReport = await reports.CreateServerDraftAsync(
                serverReports,
                TitleTextBox.Text,
                SummaryTextBox.Text,
                draftContent,
                frozenSources);
            reviewedEditorFingerprint = null;
            DraftTextBox.Text = draftContent;
            SourceSnapshotTextBlock.Text =
                $"고정 원천 {frozenSources.Count}건 · 유형 {frozenSources.Select(item => item.SourceType).Distinct().Count()}종 · " +
                "저장 직전에 같은 근거를 다시 확인합니다.";
            WorkflowStateTextBlock.Text =
                $"작성 단계: 초안 · revision {serverWorkflowReport.ReportRevision} · 내용 hash {ShortHash(serverWorkflowReport.ContentHashSha256)}";
            StatusTextBlock.Text = $"선택 근거 {selected.Count}건을 고정해 서버 초안을 만들었습니다. 다음: 내용을 확인한 뒤 '검토중 전환'을 선택하세요.";
        }
        catch (Exception exception) when (exception is InvalidOperationException or HttpRequestException or TaskCanceledException)
        {
            frozenSources = null;
            serverWorkflowReport = null;
            StatusTextBlock.Text = WorkflowFailureGuidance.FromServerException(
                exception,
                "선택 근거를 고정하지 못해 초안을 만들지 않았습니다.",
                "원천 기록과 현재 선택 항목",
                "서버 연결과 최신 원천 상태를 확인한 뒤 다시 시도하세요.");
        }
    }

    private async void MoveToReviewButton_Click(object sender, RoutedEventArgs e)
    {
        if (serverReports is null || serverWorkflowReport is null || frozenSources is null)
        {
            StatusTextBlock.Text = "먼저 현재 근거로 서버 초안을 만드세요.";
            return;
        }
        if (!SameSelection(SelectedSources().ToList(), frozenSources))
        {
            StatusTextBlock.Text = "선택 근거가 바뀌었습니다. 현재 근거로 초안을 다시 만드세요.";
            return;
        }

        try
        {
            serverWorkflowReport = await reports.MoveServerDraftToReviewAsync(
                serverReports,
                serverWorkflowReport,
                TitleTextBox.Text,
                SummaryTextBox.Text,
                DraftTextBox.Text);
            reviewedEditorFingerprint = EditorFingerprint();
            WorkflowStateTextBlock.Text =
                $"작성 단계: 검토중 · revision {serverWorkflowReport.ReportRevision} · source 집합 hash {ShortHash(serverWorkflowReport.SourceSetHashSha256)}";
            StatusTextBlock.Text = "보고서와 고정 근거를 검토중 상태로 저장했습니다. 다음: 최종 내용을 확인한 뒤 '보고서 저장'을 선택하세요.";
            await RefreshExistingReportSourcesAsync();
        }
        catch (Exception exception) when (exception is InvalidOperationException or HttpRequestException or TaskCanceledException)
        {
            StatusTextBlock.Text = WorkflowFailureGuidance.FromServerException(
                exception,
                "보고서를 검토중 상태로 전환하지 못했습니다.",
                "서버 초안과 고정 원천",
                "서버 상태와 원천 변경 여부를 확인한 뒤 다시 시도하세요.");
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
        if (serverWorkflowReport?.Status != "REVIEWED")
        {
            StatusTextBlock.Text = "보고서를 먼저 검토중 상태로 전환하세요. 초안은 서버와 현재 화면에 보존됩니다.";
            return;
        }
        if (!string.Equals(reviewedEditorFingerprint, EditorFingerprint(), StringComparison.Ordinal))
        {
            StatusTextBlock.Text = "검토중 전환 뒤 제목·요약·본문이 바뀌었습니다. 변경 내용을 포함해 새 초안을 만들고 다시 검토하세요.";
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
                actorName,
                serverWorkflowReport);
            DocumentSaved = true;
            StatusTextBlock.Text = result.SyncResult.Success && !string.IsNullOrWhiteSpace(result.ReportId)
                ? $"보고서를 서버에 저장했습니다. 선택 근거 {result.Saved?.Sources.Count ?? selected.Count}건과 원천 연결을 보존했습니다. 다음: '고정 근거 확인'에서 연결 상태를 확인하세요."
                : "보고서 원본은 이 PC에 저장했고 서버 전송은 대기 중입니다. 선택 근거와 재전송 항목은 보존됩니다. 다음: 이력의 동기화 큐에서 사유를 확인하고 다시 시도하세요.";
            if (result.Saved is not null)
            {
                serverWorkflowReport = result.Saved;
                WorkflowStateTextBlock.Text =
                    $"작성 단계: 확정 · revision {result.Saved.ReportRevision} · 내용/source hash 일치 확인";
                new ReportDetailWindow(result.Saved, serverReports) { Owner = this }.ShowDialog();
            }
            return;
        }
        catch (Exception exception) when (exception is InvalidOperationException or HttpRequestException or TaskCanceledException)
        {
            frozenSources = null;
            serverWorkflowReport = null;
            reviewedEditorFingerprint = null;
            SourceSnapshotTextBlock.Text = "저장 직전 선택 근거가 바뀌었거나 서버 확인이 끝나지 않았습니다.";
            StatusTextBlock.Text = WorkflowFailureGuidance.FromServerException(
                exception,
                "보고서를 서버에 저장하지 못했습니다.",
                "원천 기록, 기존 보고서와 현재 초안",
                "코멘트 검토에서 최신 원문을 확인하고 근거를 다시 선택한 뒤 초안을 새로 만드세요.");
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
            serverWorkflowReport = null;
            reviewedEditorFingerprint = null;
            workspace.Verifications.Clear();
            SourceSnapshotTextBlock.Text = "선택 근거가 변경되었습니다. 초안을 다시 만들어 현재 근거를 고정하세요.";
            WorkflowStateTextBlock.Text = "작성 단계: 근거 변경 · 새 초안 필요";
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

    private void SelectInitialFieldComments()
    {
        if (initialFieldCommentIds.Count == 0)
        {
            return;
        }
        foreach (var source in workspace.FieldComments.Where(item => initialFieldCommentIds.Contains(item.SourceId)))
        {
            FieldCommentGrid.SelectedItems.Add(source);
        }
        StatusTextBlock.Text = $"FieldComment 작업함에서 전달한 근거 {FieldCommentGrid.SelectedItems.Count}건을 선택했습니다.";
    }

    private async Task RefreshExistingReportSourcesAsync()
    {
        workspace.ExistingReportSources.Clear();
        if (serverReports is null)
        {
            return;
        }
        try
        {
            var existingReports = await serverReports.ListReportsAsync();
            foreach (var report in existingReports)
            {
                foreach (var source in report.Sources)
                {
                    workspace.ExistingReportSources.Add(new ExistingReportSourceRow(
                        report.ReportId,
                        report.Title,
                        report.Status,
                        FormatSourceType(source.SourceType),
                        source.SourceVersionId,
                        source.SourceRevision,
                        source.SourceHashSha256,
                        source.TraceId));
                }
            }
        }
        catch (Exception exception) when (exception is InvalidOperationException or HttpRequestException or TaskCanceledException)
        {
            StatusTextBlock.Text = WorkflowFailureGuidance.FromServerException(
                exception,
                "기존 보고서 원천을 불러오지 못했습니다.",
                "현재 선택 근거와 작성 중인 초안",
                "서버 연결을 확인한 뒤 보고서 화면을 다시 여세요.");
        }
    }

    private async void OpenExistingReportButton_Click(object sender, RoutedEventArgs e)
    {
        if (serverReports is null || ExistingReportSourceGrid.SelectedItem is not ExistingReportSourceRow selected)
        {
            StatusTextBlock.Text = "상세에서 역추적할 기존 보고서 원천을 선택하세요.";
            return;
        }
        try
        {
            var report = await serverReports.GetReportAsync(selected.ReportId);
            new ReportDetailWindow(report, serverReports) { Owner = this }.ShowDialog();
        }
        catch (Exception exception) when (exception is InvalidOperationException or HttpRequestException or TaskCanceledException)
        {
            StatusTextBlock.Text = WorkflowFailureGuidance.FromServerException(
                exception,
                "기존 보고서 상세를 열지 못했습니다.",
                "기존 보고서와 고정 source",
                "현재 채널 권한과 서버 연결을 확인한 뒤 다시 시도하세요.");
        }
    }

    private static string ShortHash(string? value) =>
        string.IsNullOrWhiteSpace(value) ? "없음" : $"{value[..Math.Min(12, value.Length)]}…";

    private string EditorFingerprint()
    {
        var value = string.Join("\n", TitleTextBox.Text, SummaryTextBox.Text, DraftTextBox.Text);
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();
    }

    private static string FormatSourceType(string sourceType) => sourceType switch
    {
        "FIELD_COMMENT" => "FieldComment",
        "DOCUMENT" => "공개 문서",
        "WORK_SEQUENCE_ITEM" => "작업순서",
        "WORK_SEQUENCE_HISTORY" => "작업순서 이력",
        "WORK_RECORD" => "작업내역",
        "WORK_RECORD_VERSION" => "작업내역 버전",
        _ => sourceType
    };

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

        public ObservableCollection<ExistingReportSourceRow> ExistingReportSources { get; } = [];
    }

    private sealed record ExistingReportSourceRow(
        string ReportId,
        string ReportTitle,
        string ReportStatus,
        string SourceTypeLabel,
        string? SourceVersionId,
        int? SourceRevision,
        string SourceHashSha256,
        string TraceId);
}
