using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Windows;
using System.Windows.Controls;
using FlowNote.Windows.Core.Reports;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.App;

public partial class ReportCorrectionWindow : Window
{
    private readonly FlowNoteServerDocumentClient serverClient;
    private readonly ServerReportResponse baseReport;
    private readonly ReportDraftService? reports;
    private IReadOnlyList<ReportSourceCandidateRecord>? selectedSources;
    private ServerReportResponse? correction;
    private string? reviewedFingerprint;

    public ReportCorrectionWindow(
        ServerReportResponse baseReport,
        FlowNoteServerDocumentClient serverClient,
        ReportDraftService? reports = null)
    {
        InitializeComponent();
        this.baseReport = baseReport;
        this.serverClient = serverClient;
        this.reports = reports;
        TitleTextBox.Text = baseReport.Title;
        SummaryTextBox.Text = baseReport.Summary;
        AnalysisTextBox.Text = baseReport.AnalysisContent;
        ConclusionTextBox.Text = baseReport.Conclusion;
        ActionPlanTextBox.Text = baseReport.ActionPlan;
        SourceSnapshotTextBlock.Text = $"기준 source snapshot {baseReport.Sources.Count}건 · {ShortHash(baseReport.SourceSetHashSha256)}";
        SelectSourcesButton.IsEnabled = reports is not null;
        foreach (var textBox in new[] { TitleTextBox, SummaryTextBox, AnalysisTextBox, ConclusionTextBox, ActionPlanTextBox })
        {
            textBox.TextChanged += Editor_TextChanged;
        }
        Loaded += async (_, _) => await RefreshLineageAsync();
    }

    public ServerReportResponse? ApprovedCorrection { get; private set; }

    private async void CreateButton_Click(object sender, RoutedEventArgs e)
    {
        if (string.IsNullOrWhiteSpace(ReasonTextBox.Text))
        {
            StatusTextBlock.Text = "정정 사유를 입력하세요. 사유는 receipt와 감사 이력에 남습니다.";
            return;
        }
        if (MessageBox.Show(
                this,
                "기존 확정본은 변경하지 않고 독립 정정 초안을 만듭니다. 계속할까요?",
                "정정본 만들기",
                MessageBoxButton.YesNo,
                MessageBoxImage.Warning) != MessageBoxResult.Yes)
        {
            return;
        }
        try
        {
            correction = await serverClient.CreateReportCorrectionAsync(
                baseReport.ReportId,
                new ServerReportCorrectionCreateRequest
                {
                    CorrectionReason = ReasonTextBox.Text.Trim(),
                    BaseReportRevision = baseReport.ReportRevision,
                    SourceSetHashSha256 = selectedSources is null ? baseReport.SourceSetHashSha256 : null,
                    MutationKey = $"wpf:report-correction:{baseReport.ReportId}:r{baseReport.ReportRevision}:{Guid.NewGuid():N}",
                    Sources = selectedSources is null ? null : reports!.BuildServerSourceRequests(selectedSources)
                });
            CreateButton.IsEnabled = false;
            ReasonTextBox.IsReadOnly = true;
            ReviewButton.IsEnabled = true;
            StatusTextBlock.Text = "정정 초안을 만들었습니다. 기존 확정본은 계속 유효합니다. 내용을 고친 뒤 재검토를 요청하세요.";
            await RefreshLineageAsync();
        }
        catch (Exception exception) when (exception is InvalidOperationException or HttpRequestException or TaskCanceledException)
        {
            StatusTextBlock.Text =
                $"정정 초안을 만들지 못했습니다: {exception.Message} 기존 확정본과 원천은 보존됩니다. " +
                "다음: 담당 검토자에게 문의하고 현재 권한을 확인한 뒤 새 원천을 선택하세요.";
        }
    }

    private void SelectSourcesButton_Click(object sender, RoutedEventArgs e)
    {
        if (reports is null)
        {
            StatusTextBlock.Text = "현재 원천 선택 기능을 사용할 수 없습니다. 보고서 작성 화면에서 다시 여세요.";
            return;
        }
        var window = new ReportCorrectionSourceWindow(reports, serverClient, baseReport) { Owner = this };
        if (window.ShowDialog() != true || window.SelectedSources is null)
        {
            return;
        }
        selectedSources = window.SelectedSources;
        SourceSnapshotTextBlock.Text = $"정정본의 현재 source {selectedSources.Count}건 · 생성 직전에 다시 검증합니다.";
        StatusTextBlock.Text = "정정본에 사용할 현재 원천 전체를 선택했습니다. 기준 보고서의 과거 snapshot은 그대로 보존됩니다.";
    }

    private async void ReviewButton_Click(object sender, RoutedEventArgs e)
    {
        if (correction is null)
        {
            return;
        }
        try
        {
            if (correction.Status == "REVIEWED" && reviewedFingerprint is not null &&
                !string.Equals(reviewedFingerprint, EditorFingerprint(), StringComparison.Ordinal))
            {
                correction = await serverClient.SaveReportAsync(CorrectionMutation("DRAFT", includeContent: true));
            }
            correction = await serverClient.SaveReportAsync(CorrectionMutation("REVIEWED", includeContent: true));
            reviewedFingerprint = EditorFingerprint();
            ApproveButton.IsEnabled = true;
            StatusTextBlock.Text = "정정 내용을 재검토 상태로 고정했습니다. 내용을 바꾸면 다시 재검토해야 합니다.";
            await RefreshLineageAsync();
        }
        catch (Exception exception) when (exception is InvalidOperationException or HttpRequestException or TaskCanceledException)
        {
            StatusTextBlock.Text = FailureMessage("재검토 요청", exception);
        }
    }

    private async void ApproveButton_Click(object sender, RoutedEventArgs e)
    {
        if (correction is null || correction.Status != "REVIEWED")
        {
            StatusTextBlock.Text = "먼저 정정 내용을 재검토 상태로 전환하세요.";
            return;
        }
        if (!string.Equals(reviewedFingerprint, EditorFingerprint(), StringComparison.Ordinal))
        {
            StatusTextBlock.Text = "재검토 뒤 내용이 바뀌었습니다. 재검토 요청을 다시 수행하세요.";
            ApproveButton.IsEnabled = false;
            return;
        }
        try
        {
            correction = await serverClient.SaveReportAsync(CorrectionMutation("APPROVED", includeContent: false));
            ApprovedCorrection = correction;
            ReviewButton.IsEnabled = false;
            ApproveButton.IsEnabled = false;
            StatusTextBlock.Text = "정정본을 확정해 현재 유효본으로 전환했습니다. 이전 보고서와 생성 문서는 대체됨·보관 이력으로 남고, 새 문서는 공개 승인을 기다립니다.";
            await RefreshLineageAsync();
        }
        catch (Exception exception) when (exception is InvalidOperationException or HttpRequestException or TaskCanceledException)
        {
            StatusTextBlock.Text = FailureMessage("정정본 확정", exception);
        }
    }

    private ServerReportSaveRequest CorrectionMutation(string targetStatus, bool includeContent) => new()
    {
        DraftReportId = correction!.ReportId,
        BaseReportRevision = correction.ReportRevision,
        MutationKey = $"wpf:report-correction-{targetStatus.ToLowerInvariant()}:{correction.ReportId}:r{correction.ReportRevision}",
        ReportStatus = targetStatus,
        ReportFamilyId = correction.ReportFamilyId,
        ReplacesReportId = correction.ReplacesReportId,
        ReplacesReportRevision = correction.ReplacesReportRevision,
        SourceSetHashSha256 = correction.SourceSetHashSha256,
        Title = includeContent ? TitleTextBox.Text : null,
        Summary = includeContent ? SummaryTextBox.Text : null,
        AnalysisContent = includeContent ? AnalysisTextBox.Text : null,
        Conclusion = includeContent ? ConclusionTextBox.Text : null,
        ActionPlan = includeContent ? ActionPlanTextBox.Text : null,
        SaveAsDocument = targetStatus == "APPROVED",
        DocumentTitle = targetStatus == "APPROVED" ? TitleTextBox.Text : null,
        DocumentStatus = "IN_REVIEW"
    };

    private async Task RefreshLineageAsync()
    {
        var lineage = await serverClient.ListReportLineageAsync(correction?.ReportId ?? baseReport.ReportId);
        LineageGrid.ItemsSource = lineage.Select(item => new ReportLineageDisplayRow(
            item,
            item.Status switch
            {
                "APPROVED" when item.IsCurrentEffective => "● 유효",
                "SUPERSEDED" => "↪ 대체됨",
                "ARCHIVED" => "▣ 보관",
                "REVIEWED" => "◐ 재검토중",
                "DRAFT" => "○ 초안",
                _ => item.Status
            }));
    }

    private void Editor_TextChanged(object sender, TextChangedEventArgs e)
    {
        if (correction?.Status == "REVIEWED" && reviewedFingerprint is not null &&
            !string.Equals(reviewedFingerprint, EditorFingerprint(), StringComparison.Ordinal))
        {
            ApproveButton.IsEnabled = false;
            ReviewButton.IsEnabled = true;
            StatusTextBlock.Text = "재검토 뒤 내용이 바뀌어 다시 재검토가 필요합니다.";
        }
    }

    private string EditorFingerprint()
    {
        var value = string.Join("\n", TitleTextBox.Text, SummaryTextBox.Text, AnalysisTextBox.Text, ConclusionTextBox.Text, ActionPlanTextBox.Text);
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();
    }

    private static string ShortHash(string? value) =>
        string.IsNullOrWhiteSpace(value) ? "없음" : $"{value[..Math.Min(12, value.Length)]}…";

    private static string FailureMessage(string action, Exception exception) =>
        $"{action}에 실패했습니다: {exception.Message} 기존 확정본은 보존됩니다. " +
        "다음: 실패 내용을 확인하고 담당 검토자에게 문의한 뒤 현재 원천을 다시 선택하세요.";

    private sealed record ReportLineageDisplayRow(
        ServerReportLineageItemResponse Item,
        string StatusLabel)
    {
        public string Title => Item.Title;
        public int ReportRevision => Item.ReportRevision;
        public string? ReplacesReportId => Item.ReplacesReportId;
        public string? GeneratedDocumentId => Item.GeneratedDocumentId;
    }
}
