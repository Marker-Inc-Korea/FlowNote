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
            ReadinessTextBlock.Text = $"AI provider 준비도: {FormatStatus(readiness.AIProviderReadinessStatus)} · 외부 호출 {(readiness.ProviderStartReady ? "허용" : "차단")}";
            ReadinessTextBlock.Foreground = readiness.ProviderStartReady
                ? System.Windows.Media.Brushes.ForestGreen : System.Windows.Media.Brushes.DarkOrange;
            StatusTextBlock.Text = "서버에 보존된 dataset version과 평가 run을 조회했습니다.";
            if (workspace.Datasets.Count > 0) DatasetGrid.SelectedIndex = 0;
            if (workspace.Runs.Count > 0) RunGrid.SelectedIndex = 0;
        }
        catch (Exception ex) when (ex is InvalidOperationException or HttpRequestException or TaskCanceledException)
        { StatusTextBlock.Text = $"ground-truth 운영 정보 조회 실패: {ex.Message}"; }
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
    }

    private static string FormatStatus(string value) => value switch
    {
        "DRAFT" => "작성중", "IN_REVIEW" => "검토중", "PENDING_FIRST_APPROVAL" => "1차 승인대기",
        "PENDING_SECOND_APPROVAL" => "2차 승인대기", "APPROVED" => "승인", "SUPERSEDED" => "대체됨",
        "RETIRED" => "폐기", "PASSED" or "PASS" => "통과", "FAILED" or "FAIL" => "실패", "PENDING" => "대기", _ => value
    };
    private static string CategoryLabel(string value) => value.Replace('_', ' ');
    private static string ScenarioLabel(string value) => value switch { "NORMAL" => "일반", "EXCLUSION" => "제외", "CONFLICT" => "상충", _ => value };
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
