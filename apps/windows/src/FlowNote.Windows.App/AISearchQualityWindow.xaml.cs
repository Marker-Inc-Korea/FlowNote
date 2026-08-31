using System.Collections.ObjectModel;
using System.Net.Http;
using System.Windows;
using System.Windows.Controls;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.App;

public partial class AISearchQualityWindow : Window
{
    private static readonly string[] SourceTypes =
    [
        "PUBLISHED_DOCUMENT_VERSION",
        "FIELD_COMMENT",
        "WORK_SEQUENCE_HISTORY",
        "REPORT_SOURCE"
    ];

    private static readonly string[] FieldCommentStatuses =
    [
        "NEW",
        "NEEDS_REVIEW",
        "ANALYZED",
        "REVIEWED",
        "SELECTED",
        "EXCLUDED",
        "ARCHIVED"
    ];

    private readonly FlowNoteServerDocumentClient? serverClient;
    private readonly QualityWorkspace workspace = new();

    public AISearchQualityWindow(FlowNoteServerDocumentClient? serverClient)
    {
        InitializeComponent();
        this.serverClient = serverClient;
        DataContext = workspace;
        Loaded += AISearchQualityWindow_Loaded;
    }

    private async void AISearchQualityWindow_Loaded(object sender, RoutedEventArgs e)
    {
        SourceTypeFilterComboBox.ItemsSource = new[]
        {
            new FilterOption("ALL", "전체 원천")
        }.Concat(SourceTypes.Select(sourceType => new FilterOption(sourceType, FormatSourceType(sourceType))));
        SourceTypeFilterComboBox.SelectedValue = "ALL";
        await RefreshAsync("AI 검색 품질 점검 값을 조회했습니다.");
    }

    private async void RefreshButton_Click(object sender, RoutedEventArgs e)
    {
        await RefreshAsync("AI 검색 품질 점검 값을 다시 조회했습니다.");
    }

    private async void RebuildButton_Click(object sender, RoutedEventArgs e)
    {
        if (serverClient is null)
        {
            StatusTextBlock.Text = "서버 URL 또는 로그인 토큰이 없어 후보를 재생성할 수 없습니다.";
            return;
        }

        SetBusy(true);
        try
        {
            var rebuild = await serverClient.RebuildAISearchCandidatesAsync();
            await RefreshAsync($"후보를 재생성했습니다. 전체 후보 {rebuild.CandidateCount}건 · 재생성 시각 {rebuild.RebuiltAt:yyyy-MM-dd HH:mm:ss}");
        }
        catch (Exception exception) when (exception is InvalidOperationException or HttpRequestException or TaskCanceledException)
        {
            StatusTextBlock.Text = $"후보 재생성에 실패했습니다. {SummarizeException(exception)}";
        }
        finally
        {
            SetBusy(false);
        }
    }

    private async Task RefreshAsync(string successStatus)
    {
        if (serverClient is null)
        {
            StatusTextBlock.Text = "서버 URL 또는 로그인 토큰이 없어 AI 검색 품질 점검을 조회할 수 없습니다.";
            return;
        }

        SetBusy(true);
        try
        {
            var quality = await serverClient.GetAISearchQualityAsync();
            ApplyQuality(quality);
            var scopeReadiness = await serverClient.GetAISearchReadinessAsync();
            ApplyScopeReadiness(scopeReadiness);

            var sourceType = SourceTypeFilterComboBox.SelectedValue?.ToString();
            if (string.Equals(sourceType, "ALL", StringComparison.Ordinal))
            {
                sourceType = null;
            }

            var candidates = await serverClient.ListAISearchCandidatesAsync(
                sourceType,
                SourceIdFilterTextBox.Text,
                limit: 200);
            ApplyCandidates(candidates);
            StatusTextBlock.Text = $"{successStatus} 후보 표시 {workspace.Candidates.Count}건 / 전체 후보 {quality.CandidateCount}건";
        }
        catch (Exception exception) when (exception is InvalidOperationException or HttpRequestException or TaskCanceledException)
        {
            StatusTextBlock.Text = $"AI 검색 품질 점검 조회에 실패했습니다. {SummarizeException(exception)}";
        }
        finally
        {
            SetBusy(false);
        }
    }

    private void ApplyQuality(ServerAISearchQualityResponse quality)
    {
        workspace.SourceCounts.Clear();
        foreach (var sourceType in SourceTypes)
        {
            workspace.SourceCounts.Add(new SourceCountRow(
                sourceType,
                FormatSourceType(sourceType),
                CountOrZero(quality.CountsBySourceType, sourceType)));
        }

        workspace.ExcludedReasons.Clear();
        foreach (var reason in quality.ExcludedReasonGuidance.OrderBy(item => item.Key))
        {
            workspace.ExcludedReasons.Add(new ExcludedReasonRow(
                reason.Key,
                reason.Value.Label,
                FormatSourceType(reason.Value.SourceType),
                CountOrZero(quality.ExcludedCountsByReason, reason.Key),
                reason.Value.OperatorAction));
        }

        var readiness = quality.FieldCommentReviewReadiness;
        workspace.StatusCounts.Clear();
        foreach (var status in FieldCommentStatuses)
        {
            workspace.StatusCounts.Add(new StatusCountRow(
                status,
                FormatFieldCommentStatus(status),
                CountOrZero(readiness.CountsByStatus, status)));
        }

        ReadinessSummaryTextBlock.Text = readiness.MissingReviewedCount == 0
            ? $"검토/분석/선정 FieldComment {readiness.ReviewedStatusCount}건으로 {readiness.RequiredReviewedCount}건 기준을 충족했습니다."
            : $"검토/분석/선정 FieldComment {readiness.ReviewedStatusCount}건입니다. {readiness.RequiredReviewedCount}건 기준까지 {readiness.MissingReviewedCount}건 부족합니다.";
        ReadinessWarningTextBlock.Text = BuildReadinessWarning(readiness);
        ReadinessDetailBorder.Visibility = Visibility.Visible;
    }

    private void ApplyScopeReadiness(ServerAISearchReadinessResponse readiness)
    {
        var sourceGaps = string.Join(", ", SourceTypes
            .Where(sourceType => CountOrZero(readiness.SourceGaps, sourceType) > 0)
            .Select(sourceType => $"{FormatSourceType(sourceType)} {CountOrZero(readiness.SourceGaps, sourceType)}건"));
        if (string.IsNullOrWhiteSpace(sourceGaps))
        {
            sourceGaps = "없음";
        }

        var status = readiness.ProviderStartReady ? "운영 AI 호출 가능" : "운영 AI 호출 차단";
        ScopeReadinessTextBlock.Text =
            $"서버 scope: {readiness.Scope.CustomerScope} / {readiness.Scope.SiteScope} / {readiness.Scope.DatabaseScope}\n" +
            $"승인 질문 {readiness.GroundTruthCount}/{readiness.GroundTruthMinimum}건 · 부족 {readiness.GroundTruthGap}건 · " +
            $"원천 부족: {sourceGaps} · 범주/유형 누락 {readiness.MissingCategoryScenarios.Count}개 · {status}\n" +
            "이 수치는 서버 DB 기준이며 WPF 공통 로컬 SQLite 준비도와 합산하지 않습니다.";
    }

    private void ApplyCandidates(IReadOnlyList<ServerAISearchCandidateResponse> candidates)
    {
        workspace.Candidates.Clear();
        foreach (var candidate in candidates)
        {
            workspace.Candidates.Add(CandidateRow.FromResponse(candidate));
        }

        CandidateGrid.SelectedItem = workspace.Candidates.FirstOrDefault();
        UpdateTraceText();
    }

    private void CandidateGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        UpdateTraceText();
    }

    private void CopyTraceButton_Click(object sender, RoutedEventArgs e)
    {
        if (string.IsNullOrWhiteSpace(TraceTextBox.Text))
        {
            StatusTextBlock.Text = "복사할 추적값이 없습니다.";
            return;
        }

        Clipboard.SetText(TraceTextBox.Text);
        StatusTextBlock.Text = "선택한 후보의 추적값을 클립보드에 복사했습니다.";
    }

    private void UpdateTraceText()
    {
        if (CandidateGrid.SelectedItem is not CandidateRow candidate)
        {
            TraceTextBox.Text = "후보를 선택하면 trace_table, trace_id, trace_version_id 기준의 원천 역추적 경로가 표시됩니다.";
            return;
        }

        TraceTextBox.Text = BuildTraceText(candidate);
    }

    private static string BuildTraceText(CandidateRow candidate)
    {
        var traceVersion = string.IsNullOrWhiteSpace(candidate.TraceVersionId) ? "(없음)" : candidate.TraceVersionId;
        var parent = string.IsNullOrWhiteSpace(candidate.ParentType)
            ? "(상위 원천 없음)"
            : $"{candidate.ParentType} / {candidate.ParentId}";
        var originHint = candidate.TraceTable switch
        {
            "document_versions" =>
                $"원천 조회: document_versions WHERE document_id = '{candidate.TraceId}' AND version_id = '{candidate.TraceVersionId}'",
            "field_comments" =>
                $"원천 조회: field_comments WHERE comment_id = '{candidate.TraceId}'",
            "work_sequence_change_history" =>
                $"원천 조회: work_sequence_change_history WHERE change_id = '{candidate.TraceId}'",
            "report_sources" =>
                $"원천 조회: report_sources WHERE id = {candidate.TraceId}; source_type/source_id/source_version_id로 실제 근거 row를 이어서 확인",
            _ =>
                $"원천 조회: {candidate.TraceTable} / {candidate.TraceId}"
        };

        return
            $"원천 유형: {candidate.SourceTypeLabel}\n" +
            $"source_id: {candidate.SourceId}\n" +
            $"source_version_id: {candidate.SourceVersionId ?? "(없음)"}\n" +
            $"trace_table: {candidate.TraceTable}\n" +
            $"trace_id: {candidate.TraceId}\n" +
            $"trace_version_id: {traceVersion}\n" +
            $"상위 원천: {parent}\n" +
            originHint;
    }

    private static string BuildReadinessWarning(ServerFieldCommentReviewReadinessResponse readiness)
    {
        if (readiness.TotalCount == 0)
        {
            return "서버 DB에 FieldComment가 없습니다. 현장 원천 기록 축적이 먼저 필요합니다.";
        }

        if (readiness.ReviewedStatusCount == 0)
        {
            return "품질 경고: 서버 DB의 FieldComment가 모두 신규 또는 미검토 상태입니다. 답변 자동화보다 관리자 검토/분석/선정 작업이 우선입니다.";
        }

        return readiness.MissingReviewedCount == 0
            ? "품질 기준 충족: 후보 근거로 사용할 검토 FieldComment 최소 수량을 만족합니다."
            : "품질 경고: FieldComment 검토 수량이 부족합니다. NEW/NEEDS_REVIEW 항목을 먼저 검토하세요.";
    }

    private void SetBusy(bool isBusy)
    {
        SourceTypeFilterComboBox.IsEnabled = !isBusy;
        SourceIdFilterTextBox.IsEnabled = !isBusy;
    }

    private static int CountOrZero(IReadOnlyDictionary<string, int> counts, string key)
    {
        return counts.TryGetValue(key, out var count) ? count : 0;
    }

    private static string FormatSourceType(string sourceType)
    {
        return sourceType switch
        {
            "PUBLISHED_DOCUMENT_VERSION" => "공개 문서 버전",
            "FIELD_COMMENT" => "FieldComment",
            "WORK_SEQUENCE_HISTORY" => "작업순서 이력",
            "REPORT_SOURCE" => "보고서 source",
            _ => sourceType
        };
    }

    private static string FormatFieldCommentStatus(string status)
    {
        return status switch
        {
            "NEW" => "신규",
            "NEEDS_REVIEW" => "검토필요",
            "ANALYZED" => "분석완료",
            "REVIEWED" => "검토완료",
            "SELECTED" => "보고서선정",
            "EXCLUDED" => "제외",
            "ARCHIVED" => "보관",
            _ => status
        };
    }

    private static string SummarizeException(Exception exception)
    {
        var message = exception.Message.Replace(Environment.NewLine, " ");
        const int maxLength = 180;
        return message.Length <= maxLength ? message : $"{message[..maxLength]}...";
    }

    private sealed record FilterOption(string Value, string Label);

    private sealed record SourceCountRow(string SourceType, string SourceTypeLabel, int Count);

    private sealed record ExcludedReasonRow(
        string Reason,
        string Label,
        string SourceTypeLabel,
        int Count,
        string OperatorAction);

    private sealed record StatusCountRow(string Status, string StatusLabel, int Count);

    private sealed record CandidateRow(
        string CandidateId,
        string SourceType,
        string SourceTypeLabel,
        string SourceId,
        string? SourceVersionId,
        string TraceTable,
        string TraceId,
        string? TraceVersionId,
        string? ParentType,
        string? ParentId,
        string Title,
        string? Summary,
        string? ReviewStatus,
        string ReviewStatusLabel,
        DateTime RefreshedAt)
    {
        public static CandidateRow FromResponse(ServerAISearchCandidateResponse response)
        {
            return new CandidateRow(
                response.CandidateId,
                response.SourceType,
                FormatSourceType(response.SourceType),
                response.SourceId,
                response.SourceVersionId,
                response.TraceTable,
                response.TraceId,
                response.TraceVersionId,
                response.ParentType,
                response.ParentId,
                response.Title,
                response.Summary,
                response.ReviewStatus,
                string.IsNullOrWhiteSpace(response.ReviewStatus)
                    ? string.Empty
                    : FormatFieldCommentStatus(response.ReviewStatus),
                response.RefreshedAt);
        }
    }

    private sealed class QualityWorkspace
    {
        public ObservableCollection<SourceCountRow> SourceCounts { get; } = [];

        public ObservableCollection<ExcludedReasonRow> ExcludedReasons { get; } = [];

        public ObservableCollection<StatusCountRow> StatusCounts { get; } = [];

        public ObservableCollection<CandidateRow> Candidates { get; } = [];
    }
}
