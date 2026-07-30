using System.Collections.ObjectModel;
using System.Net.Http;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Auth;

namespace FlowNote.Windows.App;

public partial class AIGroundTruthOperationsWindow : Window
{
    private readonly FlowNoteServerDocumentClient? client;
    private readonly string currentUserId;
    private readonly string currentRole;
    private readonly GroundTruthWorkspace workspace = new();
    private ServerAIGroundTruthDataset? selectedDataset;
    private ServerAISearchEvaluationResponse? selectedRun;

    public AIGroundTruthOperationsWindow(FlowNoteServerDocumentClient? client, string currentUserId, string currentRole)
    {
        InitializeComponent();
        this.client = client;
        this.currentUserId = currentUserId;
        this.currentRole = currentRole;
        DataContext = workspace;
        Loaded += async (_, _) => await RefreshAsync();
    }

    private async void RefreshButton_Click(object sender, RoutedEventArgs e) => await RefreshAsync();

    private async Task RefreshAsync()
    {
        if (client is null) { StatusTextBlock.Text = "서버 연결과 로그인이 필요합니다."; return; }
        try
        {
            var datasets = await client.ListAIGroundTruthDatasetsAsync();
            workspace.Datasets.Clear();
            foreach (var item in datasets) workspace.Datasets.Add(DatasetRow.From(item));
            var runs = await client.ListAISearchEvaluationsAsync();
            workspace.Runs.Clear();
            foreach (var item in runs) workspace.Runs.Add(RunRow.From(item));
            var readiness = await client.GetAISearchReadinessAsync();
            ApplyReadiness(readiness);
            ReadinessTextBlock.Text =
                $"AI provider 준비도: {FormatStatus(readiness.AIProviderReadinessStatus)}" +
                $" · 실제 외부 호출 {(readiness.ExternalAICallsBlocked ? "비활성" : "활성")}";
            ReadinessTextBlock.Foreground = readiness.ProviderStartReady && !readiness.ExternalAICallsBlocked
                ? System.Windows.Media.Brushes.ForestGreen : System.Windows.Media.Brushes.DarkOrange;
            StatusTextBlock.Text = "서버에 보존된 dataset version과 평가 run을 조회했습니다.";
            if (workspace.Datasets.Count > 0) DatasetGrid.SelectedIndex = 0;
            if (workspace.Runs.Count > 0) RunGrid.SelectedIndex = 0;
        }
        catch (Exception ex) when (ex is InvalidOperationException or HttpRequestException or TaskCanceledException)
        { StatusTextBlock.Text = $"ground-truth 운영 정보 조회 실패: {ex.Message}"; }
    }

    private void ApplyReadiness(ServerAISearchReadinessResponse readiness)
    {
        var sourceSummary = string.Join(", ", readiness.SourceMinimums.Select(item =>
            $"{SourceTypeLabel(item.Key)} {Count(readiness.SourceCounts, item.Key)}/{item.Value}건"));
        ReadinessBoundaryTextBlock.Text =
            $"고객 승인 ANONYMOUS_FIELD {readiness.FieldReadiness.GroundTruthCount}/{readiness.GroundTruthMinimum}건" +
            $" · 부족 {readiness.FieldReadiness.GroundTruthGap}건\n" +
            $"합성·시험 SMOKE_REGRESSION {readiness.SmokeRegressionReadiness.GroundTruthCount}건(착수 판정 제외)" +
            $" · 실제 원천 {sourceSummary}";

        var approval = readiness.ApprovalActorSeparation;
        ReadinessApprovalTextBlock.Text = readiness.LatestApprovedDataset is null
            ? "승인자 분리: 승인된 FIELD_READINESS dataset 없음"
            : $"승인자 분리: {approval.DistinctActorCount}/{approval.RequiredActorCount}명 " +
              $"{(approval.Complete ? "완료" : "미완료")}\n" +
              $"작성 {approval.AuthorId ?? "-"} / 검토 {approval.ReviewerId ?? "-"} / " +
              $"1차 승인 {approval.FirstApprovedBy ?? "-"} / 2차 승인 {approval.SecondApprovedBy ?? "-"}";

        var evaluation = readiness.LatestEvaluation;
        ReadinessEvaluationTextBlock.Text = evaluation is null
            ? "최근 평가 run: 승인된 실제 현장 snapshot에 결합된 평가 없음"
            : $"최근 평가 run: {evaluation.RunId} · {FormatStatus(evaluation.Status)}" +
              $" · {evaluation.PassedCount}/{evaluation.CaseCount}건\n" +
              $"후보 ID {(evaluation.CandidateIdentityStable ? "안정" : "변경")} / " +
              $"순위 {(evaluation.RankingStable ? "안정" : "변경")} / " +
              $"top-k {evaluation.TopKInclusionRate:P0} / 인용 trace {evaluation.CitationTraceSuccessRate:P0} / " +
              $"의미 {evaluation.CitationSemanticMatchRate:P0} / 상충 {evaluation.ConflictDisclosureRate:P0}" +
              $" · {evaluation.CreatedAt.LocalDateTime:G}";

        var review = readiness.HumanSampleReview;
        ReadinessReviewTextBlock.Text =
            $"24칸 검토: {ReviewStatusLabel(review.Status)} · 표본 {review.SampleCaseCount}/24칸" +
            $" · 독립 검토자 {review.IndependentReviewerCount}/2명" +
            $" · 불일치 {review.DisagreementCaseKeys.Count}건" +
            (review.ConsensusReviewerId is null ? "" : $" · 제3 합의 {review.ConsensusReviewerId}");

        var config = readiness.ExternalCallConfiguration;
        ReadinessExternalTextBlock.Text =
            $"provider_start_ready={(readiness.ProviderStartReady ? "true" : "false")} · " +
            $"실제 외부 호출 {(readiness.ExternalAICallsBlocked ? "비활성" : "활성")}\n" +
            $"기능 플래그 {(config.FeatureEnabled ? "켜짐" : "꺼짐")} / 준비도 게이트 {(config.ReadinessGateEnabled ? "켜짐" : "꺼짐")} / " +
            $"어댑터 {config.ProviderAdapterMode} / provider {(config.ProviderConfigured ? "설정됨" : "미설정")} / " +
            $"model {(config.ModelConfigured ? "설정됨" : "미설정")}";

        ReadinessGapGrid.ItemsSource = readiness.CategoryScenarioGaps
            .Select(CoverageRow.From)
            .ToList();
        ReadinessActionGrid.ItemsSource = readiness.OperatorActions;
    }

    private async void DatasetGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (client is null || DatasetGrid.SelectedItem is not DatasetRow row) return;
        try
        {
            selectedDataset = await client.GetAIGroundTruthDatasetAsync(row.DatasetVersionId);
            workspace.Cases.Clear();
            foreach (var item in selectedDataset.Cases) workspace.Cases.Add(CaseRow.From(item));
            workspace.Coverage.Clear();
            foreach (var item in selectedDataset.Coverage) workspace.Coverage.Add(CoverageRow.From(item));
            DatasetSummaryTextBlock.Text =
                $"{selectedDataset.Title} · {selectedDataset.DatasetKey} v{selectedDataset.Version} · {FormatStatus(selectedDataset.Status)}\n" +
                $"작성 {selectedDataset.AuthorId} / 검토 {selectedDataset.ReviewerId ?? "-"} / 승인 {selectedDataset.FirstApprovedBy ?? "-"}, {selectedDataset.SecondApprovedBy ?? "-"}\n" +
                $"snapshot {selectedDataset.SnapshotHash ?? "승인 전"} · 48건 coverage {(selectedDataset.CoverageComplete ? "충족" : "미충족")} · 대체 원본 {selectedDataset.ReplacesDatasetVersionId ?? "없음"}";
            UpdateActionButtons();
        }
        catch (Exception ex) { StatusTextBlock.Text = $"dataset 상세 조회 실패: {ex.Message}"; }
    }

    private async void CreateDatasetButton_Click(object sender, RoutedEventArgs e) => await CreateDatasetAsync(null);
    private async void CreateReplacementButton_Click(object sender, RoutedEventArgs e) => await CreateDatasetAsync(selectedDataset);
    private void OpenCaseEditorButton_Click(object sender, RoutedEventArgs e)
    {
        new AIGroundTruthCaseEditorWindow(client, currentUserId) { Owner = this }.ShowDialog();
    }

    private async Task CreateDatasetAsync(ServerAIGroundTruthDataset? replacement)
    {
        if (client is null) return;
        try
        {
            var cases = replacement?.Cases ?? await client.ListAIGroundTruthCasesAsync();
            if (cases.Count == 0) { StatusTextBlock.Text = "구성할 승인 사례가 없습니다."; return; }
            var key = string.IsNullOrWhiteSpace(DatasetKeyTextBox.Text)
                ? replacement?.DatasetKey ?? "ground-truth-48" : DatasetKeyTextBox.Text.Trim();
            var title = string.IsNullOrWhiteSpace(DatasetTitleTextBox.Text)
                ? replacement?.Title ?? "AI ground-truth 48건" : DatasetTitleTextBox.Text.Trim();
            var track = (TrackComboBox.SelectedItem as ComboBoxItem)?.Content?.ToString() ?? "SMOKE_REGRESSION";
            if (replacement is not null) track = replacement.ReadinessTrack;
            await client.CreateAIGroundTruthDatasetAsync(new ServerAIGroundTruthDatasetCreateRequest
            {
                DatasetKey = key, Title = title, ReadinessTrack = track,
                GroundTruthCaseIds = cases.Select(item => item.GroundTruthCaseId).ToArray(),
                ChangeReason = ChangeReasonTextBox.Text.Trim(),
                ReplacesDatasetVersionId = replacement?.DatasetVersionId,
            });
            await RefreshAsync();
            StatusTextBlock.Text = replacement is null ? "새 draft를 생성했습니다." : "승인 snapshot을 보존하고 대체 draft를 생성했습니다.";
        }
        catch (Exception ex) { StatusTextBlock.Text = $"dataset 생성 실패: {ex.Message}"; }
    }

    private async void TransitionButton_Click(object sender, RoutedEventArgs e)
    {
        if (client is null || selectedDataset is null || sender is not Button button) return;
        try
        {
            await client.TransitionAIGroundTruthDatasetAsync(
                selectedDataset.DatasetVersionId, button.Tag?.ToString() ?? "", ChangeReasonTextBox.Text.Trim());
            await RefreshAsync();
            StatusTextBlock.Text = $"{button.Content} 상태를 서버 감사 이력과 함께 저장했습니다.";
        }
        catch (Exception ex) { StatusTextBlock.Text = $"상태 변경 거부: {ex.Message}"; }
    }

    private async void EvaluateButton_Click(object sender, RoutedEventArgs e)
    {
        if (client is null || selectedDataset is null) return;
        try
        {
            var result = await client.RunAISearchEvaluationAsync(new ServerAISearchEvaluationRequest
            {
                RunLabel = $"WPF {selectedDataset.DatasetKey} v{selectedDataset.Version} {DateTime.Now:yyyyMMdd-HHmmss}",
                DatasetVersionId = selectedDataset.DatasetVersionId,
            });
            await RefreshAsync();
            StatusTextBlock.Text = $"평가 {result.RunId}: {FormatStatus(result.Status)}. dataset version과 run_id가 고정 저장되었습니다.";
        }
        catch (Exception ex) { StatusTextBlock.Text = $"평가 실행 실패: {ex.Message}"; }
    }

    private async void RunGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (client is null || RunGrid.SelectedItem is not RunRow row) return;
        try
        {
            selectedRun = await client.GetAISearchEvaluationAsync(row.RunId);
            ApplyRun(selectedRun);
            UpdateActionButtons();
        }
        catch (Exception ex) { StatusTextBlock.Text = $"run 상세 조회 실패: {ex.Message}"; }
    }

    private void ApplyRun(ServerAISearchEvaluationResponse run)
    {
        workspace.EvaluationCases.Clear();
        foreach (var item in run.Cases) workspace.EvaluationCases.Add(EvaluationCaseRow.From(item));
        RunSummaryTextBlock.Text = $"run {run.RunId} · {FormatStatus(run.Status)} · dataset {run.DatasetVersionId ?? "AD_HOC"}\n후보 identity {(run.CandidateIdentityStable ? "안정" : "변경")} · 순위 {(run.RankingStable ? "안정" : "변경")}";
        FailureGrid.SelectedItem = workspace.EvaluationCases.FirstOrDefault(item => !item.Passed) ?? workspace.EvaluationCases.FirstOrDefault();
    }

    private async void ComparePreviousButton_Click(object sender, RoutedEventArgs e)
    {
        if (client is null || selectedRun is null) return;
        var currentIndex = workspace.Runs.ToList().FindIndex(item => item.RunId == selectedRun.RunId);
        var previous = workspace.Runs.Skip(currentIndex + 1).FirstOrDefault(item => item.DatasetVersionId == selectedRun.DatasetVersionId);
        if (previous is null) { StatusTextBlock.Text = "같은 dataset version의 이전 run이 없습니다."; return; }
        var previousDetail = await client.GetAISearchEvaluationAsync(previous.RunId);
        var oldCases = previousDetail.Cases.ToDictionary(item => item.CaseKey);
        var changed = selectedRun.Cases.Count(item => !oldCases.TryGetValue(item.CaseKey, out var old) || old.Passed != item.Passed || old.RankingHash != item.RankingHash);
        StatusTextBlock.Text = $"이전 run {previous.RunId} 비교: 상태 {FormatStatus(previousDetail.Status)} → {FormatStatus(selectedRun.Status)}, 사례 변화 {changed}건.";
    }

    private void FailureGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        SourceTraceTextBox.Text = FailureGrid.SelectedItem is EvaluationCaseRow row
            ? row.TraceText : "실패 사례를 선택하면 기대·실제·제외 원천 식별자와 hash를 표시합니다.";
    }

    private void SampleReviewButton_Click(object sender, RoutedEventArgs e)
    {
        if (client is null || selectedDataset is null || selectedRun is null) return;
        if (selectedDataset.ReadinessTrack != "FIELD_READINESS"
            || selectedDataset.Status != "APPROVED"
            || selectedRun.Status != "PASSED"
            || selectedRun.DatasetVersionId != selectedDataset.DatasetVersionId)
        {
            StatusTextBlock.Text = "승인된 실제 현장 dataset과 그 dataset을 통과한 평가 run을 함께 선택하세요.";
            return;
        }
        new AIFieldReadinessSampleReviewWindow(
            client, selectedDataset, selectedRun, currentUserId)
        {
            Owner = this
        }.ShowDialog();
    }

    private void UpdateActionButtons()
    {
        var status = selectedDataset?.Status;
        SubmitButton.IsEnabled = status == "DRAFT" && selectedDataset?.AuthorId == currentUserId;
        ReviewButton.IsEnabled = status == "IN_REVIEW" && selectedDataset?.AuthorId != currentUserId;
        FirstApproveButton.IsEnabled = RolePermissionPolicy.CanApproveGroundTruth(currentRole) && status == "PENDING_FIRST_APPROVAL" &&
            currentUserId != selectedDataset?.AuthorId && currentUserId != selectedDataset?.ReviewerId;
        SecondApproveButton.IsEnabled = RolePermissionPolicy.CanApproveGroundTruth(currentRole) && status == "PENDING_SECOND_APPROVAL" &&
            currentUserId != selectedDataset?.AuthorId && currentUserId != selectedDataset?.ReviewerId && currentUserId != selectedDataset?.FirstApprovedBy;
        RetireButton.IsEnabled = RolePermissionPolicy.CanApproveGroundTruth(currentRole) && status == "APPROVED";
        EvaluateButton.IsEnabled = status == "APPROVED";
        SampleReviewButton.IsEnabled = client is not null
            && selectedDataset?.ReadinessTrack == "FIELD_READINESS"
            && status == "APPROVED"
            && selectedRun?.Status == "PASSED"
            && selectedRun.DatasetVersionId == selectedDataset.DatasetVersionId;
    }

    private static string FormatStatus(string value) => value switch
    {
        "DRAFT" => "작성중", "IN_REVIEW" => "검토중", "PENDING_FIRST_APPROVAL" => "1차 승인대기",
        "PENDING_SECOND_APPROVAL" => "2차 승인대기", "APPROVED" => "승인", "SUPERSEDED" => "대체됨",
        "RETIRED" => "폐기", "PASSED" or "PASS" => "통과", "FAILED" or "FAIL" => "실패", "PENDING" => "대기", _ => value
    };
    private static string CategoryLabel(string value) => value switch
    {
        "SAFETY" => "안전",
        "QUALITY" => "품질",
        "EQUIPMENT_ANOMALY" => "설비 이상",
        "WORK_HOLD" => "작업 보류",
        "REWORK" => "재작업",
        "HANDOVER" => "인수인계",
        "LATEST_PUBLISHED_DOCUMENT" => "최신 공개 문서",
        "CONFLICTING_RECORDS" => "상충 기록",
        _ => value.Replace('_', ' '),
    };
    private static string ScenarioLabel(string value) => value switch { "NORMAL" => "일반", "EXCLUSION" => "제외", "CONFLICT" => "상충", _ => value };
    private static string ReviewStatusLabel(string value) => value switch
    {
        "NOT_STARTED" => "시작 전",
        "PENDING_SECOND_REVIEW" => "두 번째 독립 검토 대기",
        "PENDING_CONSENSUS" => "제3 합의 대기",
        "COMPLETED" => "완료",
        "INVALID_EVALUATION_PAIR" => "동일 snapshot 2회 평가 불일치",
        "INVALID_SAMPLE_MISMATCH" => "표본 불일치",
        "INVALID_CONSENSUS_SCOPE" => "합의 범위 불일치",
        _ => value,
    };
    private static string SourceTypeLabel(string value) => value switch
    {
        "PUBLISHED_DOCUMENT_VERSION" => "공개 문서",
        "FIELD_COMMENT" => "현장 코멘트",
        "WORK_SEQUENCE_HISTORY" => "작업순서 이력",
        "REPORT_SOURCE" => "보고서 근거",
        _ => value,
    };
    private static int Count(IReadOnlyDictionary<string, int> values, string key) =>
        values.TryGetValue(key, out var value) ? value : 0;
    private static string EvidenceText(IEnumerable<Dictionary<string, object>> values) => string.Join("\n", values.Select(value =>
        string.Join(" / ", new[] { Value(value, "source_type"), Value(value, "source_id"), Value(value, "source_version_id"), Value(value, "content_hash") }.Where(text => !string.IsNullOrWhiteSpace(text)))));
    private static string Value(Dictionary<string, object> value, string key) => value.TryGetValue(key, out var item)
        ? item is JsonElement json ? json.ToString() : item?.ToString() ?? "" : "";

    private sealed class GroundTruthWorkspace
    {
        public ObservableCollection<DatasetRow> Datasets { get; } = [];
        public ObservableCollection<CaseRow> Cases { get; } = [];
        public ObservableCollection<CoverageRow> Coverage { get; } = [];
        public ObservableCollection<RunRow> Runs { get; } = [];
        public ObservableCollection<EvaluationCaseRow> EvaluationCases { get; } = [];
    }
    private sealed record DatasetRow(string DatasetVersionId, string DatasetKey, int Version, string StatusLabel, int CaseCount, bool CoverageComplete)
    { public static DatasetRow From(ServerAIGroundTruthDatasetSummary x) => new(x.DatasetVersionId, x.DatasetKey, x.Version, FormatStatus(x.Status), x.CaseCount, x.CoverageComplete); }
    private sealed record CaseRow(string CaseKey, string CategoryLabel, string ScenarioLabel, string Question, string AsOfText, string RankRange, string SourceCounts)
    { public static CaseRow From(ServerAIGroundTruthCase x) => new(x.CaseKey, AIGroundTruthOperationsWindow.CategoryLabel(x.Category), AIGroundTruthOperationsWindow.ScenarioLabel(x.ScenarioType), x.Question, x.AsOf.LocalDateTime.ToString("yyyy-MM-dd HH:mm"), $"{x.AllowedRankMin}-{x.AllowedRankMax}", $"{x.ExpectedEvidence.Count}/{x.ExpectedExcluded.Count}"); }
    private sealed record CoverageRow(string CategoryLabel, string ScenarioLabel, int Count, int Required, int Missing)
    { public static CoverageRow From(ServerAIGroundTruthCoverage x) => new(AIGroundTruthOperationsWindow.CategoryLabel(x.Category), AIGroundTruthOperationsWindow.ScenarioLabel(x.ScenarioType), x.Count, x.Required, x.Missing); }
    private sealed record RunRow(string RunId, string StatusLabel, string? DatasetVersionId)
    { public static RunRow From(ServerAISearchEvaluationResponse x) => new(x.RunId, FormatStatus(x.Status), x.DatasetVersionId); }
    private sealed record EvaluationCaseRow(string CaseKey, bool Passed, string FailureText, string RankingHash, string TraceText)
    {
        public static EvaluationCaseRow From(ServerAISearchEvaluationCaseResponse x) => new(
            x.CaseKey, x.Passed, x.Passed ? "없음" : string.Join(", ", x.FailureReasons), x.RankingHash,
            $"기대 원천\n{EvidenceText(x.ExpectedEvidence)}\n\n실제 원천\n{EvidenceText(x.ActualEvidence)}\n\n제외 원천\n{EvidenceText(x.ExcludedEvidence)}");
    }
}
