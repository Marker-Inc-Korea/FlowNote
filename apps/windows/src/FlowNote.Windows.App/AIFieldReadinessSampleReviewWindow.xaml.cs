using System.Collections.ObjectModel;
using System.Net.Http;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.App;

public partial class AIFieldReadinessSampleReviewWindow : Window
{
    private readonly FlowNoteServerDocumentClient client;
    private readonly ServerAIGroundTruthDataset dataset;
    private readonly ServerAISearchEvaluationResponse evaluationRun;
    private readonly string currentUserId;
    private readonly ReviewWorkspace workspace = new();
    private ServerAIFieldReadinessSamplePlan? plan;
    private ServerAIFieldReadinessReviewListResponse? reviewState;
    private string reviewRole = "INDEPENDENT";

    public AIFieldReadinessSampleReviewWindow(
        FlowNoteServerDocumentClient client,
        ServerAIGroundTruthDataset dataset,
        ServerAISearchEvaluationResponse evaluationRun,
        string currentUserId)
    {
        InitializeComponent();
        this.client = client;
        this.dataset = dataset;
        this.evaluationRun = evaluationRun;
        this.currentUserId = currentUserId;
        DataContext = workspace;
        Loaded += async (_, _) => await RefreshAsync();
    }

    private async void RefreshButton_Click(object sender, RoutedEventArgs e) => await RefreshAsync();

    private async Task RefreshAsync()
    {
        try
        {
            plan = await client.GetAIFieldReadinessSamplePlanAsync(
                dataset.DatasetVersionId, evaluationRun.RunId);
            reviewState = await client.ListAIFieldReadinessSampleReviewsAsync(
                dataset.DatasetVersionId, evaluationRun.RunId);
            ApplyState();
            StatusTextBlock.Text = "서버에 고정된 표본 계획과 현재 검토 상태를 읽었습니다.";
        }
        catch (Exception ex) when (ex is InvalidOperationException or HttpRequestException or TaskCanceledException)
        {
            SubmitButton.IsEnabled = false;
            StatusTextBlock.Text = $"표본 검토 정보를 불러오지 못했습니다: {ex.Message}";
        }
    }

    private void ApplyState()
    {
        if (plan is null || reviewState is null) return;
        var summary = reviewState.Summary;
        var isIndependentReviewer = summary.IndependentReviewerIds.Contains(currentUserId);
        var canSubmitIndependent = summary.Status is ("NOT_STARTED" or "PENDING_SECOND_REVIEW")
            && !isIndependentReviewer;
        var canSubmitConsensus = summary.Status == "PENDING_CONSENSUS"
            && !isIndependentReviewer;
        reviewRole = canSubmitConsensus ? "CONSENSUS" : "INDEPENDENT";

        var visibleKeys = canSubmitConsensus
            ? summary.DisagreementCaseKeys.ToHashSet()
            : plan.Cases.Select(item => item.CaseKey).ToHashSet();
        var findingsByReview = reviewState.Reviews
            .Where(item => item.Findings is not null)
            .ToDictionary(
                item => item.ReviewId,
                item => item.Findings!.ToDictionary(finding => finding.CaseKey));

        workspace.Rows.Clear();
        foreach (var item in plan.Cases.Where(item => visibleKeys.Contains(item.CaseKey)))
        {
            var row = ReviewRow.From(item);
            row.Comparison = ComparisonFor(item.CaseKey, reviewState.Reviews, findingsByReview);
            workspace.Rows.Add(row);
        }

        PlanTextBlock.Text =
            $"dataset {plan.DatasetVersionId} · run {plan.EvaluationRunId}\n" +
            $"계획 {plan.SamplingPlanReference} · sample hash {plan.SampleHash}";
        ReviewStateTextBlock.Text = summary.Status switch
        {
            "NOT_STARTED" => "1차 독립 판정 대기 · 24칸을 모두 판정해야 합니다.",
            "PENDING_SECOND_REVIEW" => "2차 독립 판정 대기 · 첫 검토자의 판정은 아직 숨겨져 있습니다.",
            "PENDING_CONSENSUS" => $"불일치 {summary.DisagreementCaseKeys.Count}건 · 앞선 두 사람과 다른 제3 합의자가 판정합니다.",
            "COMPLETED" => $"독립 검토 완료 · 합의 검토자 {summary.ConsensusReviewerId ?? "불필요"}",
            _ => $"검토 상태 {summary.Status}",
        };
        BlindNoticeTextBlock.Text = summary.IndependentReviewerCount < 2
            ? "blind 보호: 표본 case 목록과 근거만 표시하며 다른 검토자의 판단·decision hash는 두 번째 제출 전까지 표시하지 않습니다."
            : "두 독립 판정이 모두 제출되어 비교가 공개되었습니다. 불일치가 있으면 제3 합의자는 해당 case만 처리합니다.";
        SubmitButton.Content = canSubmitConsensus ? "제3 합의 제출" : "독립 판정 제출";
        SubmitButton.IsEnabled = canSubmitIndependent || canSubmitConsensus;
        ReviewGrid.IsReadOnly = !SubmitButton.IsEnabled;
        ReviewGrid.SelectedIndex = workspace.Rows.Count > 0 ? 0 : -1;
    }

    private static string ComparisonFor(
        string caseKey,
        IReadOnlyList<ServerAIFieldReadinessReview> reviews,
        IReadOnlyDictionary<string, Dictionary<string, ServerAIFieldReadinessFinding>> findingsByReview)
    {
        var values = reviews
            .Select(item => (
                Review: item,
                Finding: findingsByReview.TryGetValue(item.ReviewId, out var findings)
                    && findings.TryGetValue(caseKey, out var finding) ? finding : null))
            .Where(item => item.Finding is not null)
            .Select(item =>
                $"{(item.Review.ReviewRole == "CONSENSUS" ? "제3 합의" : "독립 판정")} · {item.Review.ReviewerId}: " +
                $"trace {item.Finding!.CitationTrace}, 의미 {item.Finding.CitationMeaning}, " +
                $"상충 {item.Finding.ConflictDisclosure}, 권한 {item.Finding.PermissionBoundary}\n{item.Finding.Note}")
            .ToArray();
        return values.Length == 0
            ? "두 번째 독립 판정 제출 전에는 다른 검토자의 판단을 표시하지 않습니다."
            : string.Join("\n\n", values);
    }

    private async void SubmitButton_Click(object sender, RoutedEventArgs e)
    {
        if (plan is null || reviewState is null || !SubmitButton.IsEnabled) return;
        ReviewGrid.CommitEdit(DataGridEditingUnit.Cell, true);
        ReviewGrid.CommitEdit(DataGridEditingUnit.Row, true);
        if (workspace.Rows.Any(item => string.IsNullOrWhiteSpace(item.Note)))
        {
            StatusTextBlock.Text = "각 case의 판정 메모를 입력하세요.";
            return;
        }
        try
        {
            SubmitButton.IsEnabled = false;
            var response = await client.CreateAIFieldReadinessSampleReviewAsync(
                new ServerAIFieldReadinessReviewCreateRequest
                {
                    DatasetVersionId = plan.DatasetVersionId,
                    EvaluationRunId = plan.EvaluationRunId,
                    SamplingPlanReference = plan.SamplingPlanReference,
                    ReviewRole = reviewRole,
                    ResolvesReviewIds = reviewRole == "CONSENSUS"
                        ? reviewState.Summary.IndependentReviewIds : [],
                    Findings = workspace.Rows.Select(item => item.ToRequest()).ToArray(),
                });
            StatusTextBlock.Text = response.Summary.Status == "COMPLETED"
                ? "표본 검토가 완료되었습니다. 원 판정과 합의 기록은 서버에 보존됩니다."
                : "판정을 저장했습니다. 다음 독립 검토 또는 제3 합의를 기다립니다.";
            await RefreshAsync();
        }
        catch (Exception ex)
        {
            SubmitButton.IsEnabled = true;
            StatusTextBlock.Text = $"판정 제출이 거부되었습니다: {ex.Message}";
        }
    }

    private void ReviewGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (ReviewGrid.SelectedItem is not ReviewRow row)
        {
            TraceTextBox.Text = "case를 선택하면 기대·실제·제외 근거의 trace를 표시합니다.";
            ComparisonTextBox.Text = "두 독립 판정이 모두 제출된 뒤에만 판정 비교를 표시합니다.";
            return;
        }
        TraceTextBox.Text = row.TraceText;
        ComparisonTextBox.Text = row.Comparison;
    }

    private void CloseButton_Click(object sender, RoutedEventArgs e) => Close();

    private static string EvidenceText(IEnumerable<Dictionary<string, object>> values) =>
        string.Join("\n", values.Select(value => string.Join(" / ", new[]
        {
            Value(value, "source_type", "sourceType"),
            Value(value, "source_id", "sourceId"),
            Value(value, "source_version_id", "sourceVersionId"),
            Value(value, "trace_id", "traceId"),
            Value(value, "content_hash", "contentHash"),
        }.Where(text => !string.IsNullOrWhiteSpace(text)))));

    private static string Value(Dictionary<string, object> value, params string[] keys)
    {
        foreach (var key in keys)
        {
            if (!value.TryGetValue(key, out var item)) continue;
            return item is JsonElement json ? json.ToString() : item?.ToString() ?? "";
        }
        return "";
    }

    private sealed class ReviewWorkspace
    {
        public ObservableCollection<ReviewRow> Rows { get; } = [];
    }

    private sealed class ReviewRow
    {
        public required string CaseKey { get; init; }
        public required string CategoryLabel { get; init; }
        public required string ScenarioLabel { get; init; }
        public required string ScenarioType { get; init; }
        public required string TraceText { get; init; }
        public string CitationTrace { get; set; } = "PASS";
        public string CitationMeaning { get; set; } = "PASS";
        public string ConflictDisclosure { get; set; } = "NOT_APPLICABLE";
        public string PermissionBoundary { get; set; } = "PASS";
        public string Note { get; set; } = string.Empty;
        public string Comparison { get; set; } = string.Empty;

        public static ReviewRow From(ServerAIFieldReadinessSampleCase value) => new()
        {
            CaseKey = value.CaseKey,
            CategoryLabel = value.Category.Replace('_', ' '),
            ScenarioLabel = value.ScenarioType switch
            {
                "NORMAL" => "일반",
                "EXCLUSION" => "제외",
                "CONFLICT" => "상충",
                _ => value.ScenarioType,
            },
            ScenarioType = value.ScenarioType,
            ConflictDisclosure = value.ScenarioType == "CONFLICT" ? "PASS" : "NOT_APPLICABLE",
            TraceText =
                $"질문\n{value.Question}\n\n기대 원천\n{EvidenceText(value.ExpectedEvidence)}\n\n" +
                $"실제 원천\n{EvidenceText(value.ActualEvidence)}\n\n제외 원천\n{EvidenceText(value.ExpectedExcluded)}\n\n" +
                $"ranking hash\n{value.RankingHash}",
        };

        public ServerAIFieldReadinessFinding ToRequest() => new()
        {
            CaseKey = CaseKey,
            CitationTrace = CitationTrace,
            CitationMeaning = CitationMeaning,
            ConflictDisclosure = ConflictDisclosure,
            PermissionBoundary = PermissionBoundary,
            Note = Note.Trim(),
        };
    }
}
