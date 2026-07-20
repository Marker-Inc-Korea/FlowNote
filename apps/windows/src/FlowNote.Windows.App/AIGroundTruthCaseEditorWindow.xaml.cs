using System.Collections.ObjectModel;
using System.Windows;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.App;

public partial class AIGroundTruthCaseEditorWindow : Window
{
    private static readonly string[] Categories = ["SAFETY", "QUALITY", "EQUIPMENT_ANOMALY", "WORK_HOLD", "REWORK", "HANDOVER", "LATEST_PUBLISHED_DOCUMENT", "CONFLICTING_RECORDS"];
    private static readonly string[] Scenarios = ["NORMAL", "EXCLUSION", "CONFLICT"];
    private static readonly string[] SourceTypes = ["PUBLISHED_DOCUMENT_VERSION", "FIELD_COMMENT", "WORK_SEQUENCE_HISTORY", "REPORT_SOURCE"];
    private readonly FlowNoteServerDocumentClient? client;
    private readonly EditorWorkspace workspace = new();

    public AIGroundTruthCaseEditorWindow(FlowNoteServerDocumentClient? client, string currentUserId)
    {
        InitializeComponent();
        this.client = client;
        DataContext = workspace;
        CategoryComboBox.ItemsSource = Categories; CategoryComboBox.SelectedIndex = 0;
        ScenarioComboBox.ItemsSource = Scenarios; ScenarioComboBox.SelectedIndex = 0;
        ExcludedSourceTypeComboBox.ItemsSource = SourceTypes; ExcludedSourceTypeComboBox.SelectedIndex = 0;
        OutcomeComboBox.SelectedIndex = 0; ClassificationComboBox.SelectedIndex = 0; AsOfDatePicker.SelectedDate = DateTime.Today;
        Loaded += async (_, _) => await RefreshAsync();
    }

    private async void RefreshButton_Click(object sender, RoutedEventArgs e) => await RefreshAsync();
    private async Task RefreshAsync()
    {
        if (client is null) return;
        try
        {
            workspace.Candidates.Clear();
            foreach (var item in await client.ListAISearchCandidatesAsync(limit: 500)) workspace.Candidates.Add(CandidateRow.From(item));
            workspace.CasePool.Clear();
            foreach (var item in await client.ListAIGroundTruthCasesAsync(includePending: true)) workspace.CasePool.Add(CasePoolRow.From(item));
            StatusTextBlock.Text = $"후보 {workspace.Candidates.Count}건, 사례 {workspace.CasePool.Count}건을 조회했습니다.";
        }
        catch (Exception ex) { StatusTextBlock.Text = $"조회 실패: {ex.Message}"; }
    }

    private void AddIncludedButton_Click(object sender, RoutedEventArgs e)
    {
        foreach (CandidateRow item in CandidateGrid.SelectedItems)
            if (!workspace.References.Any(x => x.Kind == "포함" && x.SourceType == item.SourceType && x.SourceId == item.SourceId && x.SourceVersionId == item.SourceVersionId))
                workspace.References.Add(new ReferenceRow("포함", item.SourceType, item.SourceId, item.SourceVersionId, item.ContentHash, null, "질문의 직접 근거로 선택"));
    }

    private void AddExcludedButton_Click(object sender, RoutedEventArgs e)
    {
        if (string.IsNullOrWhiteSpace(ExcludedSourceIdTextBox.Text) || string.IsNullOrWhiteSpace(ExclusionReasonTextBox.Text))
        { StatusTextBlock.Text = "제외 원천 ID와 서버 제외 사유 코드를 입력하세요."; return; }
        workspace.References.Add(new ReferenceRow("제외", ExcludedSourceTypeComboBox.SelectedItem?.ToString() ?? "", ExcludedSourceIdTextBox.Text.Trim(), string.IsNullOrWhiteSpace(ExcludedSourceVersionIdTextBox.Text) ? null : ExcludedSourceVersionIdTextBox.Text.Trim(), null, ExclusionReasonTextBox.Text.Trim(), RationaleTextBox.Text.Trim()));
    }

    private void RemoveReferenceButton_Click(object sender, RoutedEventArgs e)
    { if (ReferenceGrid.SelectedItem is ReferenceRow row) workspace.References.Remove(row); }

    private async void CreateCaseButton_Click(object sender, RoutedEventArgs e)
    {
        if (client is null || !int.TryParse(RankMinTextBox.Text, out var min) || !int.TryParse(RankMaxTextBox.Text, out var max)) return;
        try
        {
            var references = workspace.References.Select(row => new ServerAISearchEvidenceReferenceRequest
            {
                SourceType = row.SourceType, SourceId = row.SourceId, SourceVersionId = row.SourceVersionId,
                ContentHash = row.ContentHash, ExclusionReason = row.ExclusionReason, Rationale = row.Rationale,
            }).ToArray();
            var created = await client.CreateAIGroundTruthCaseAsync(new ServerAIGroundTruthCaseCreateRequest
            {
                CaseKey = CaseKeyTextBox.Text.Trim(), Category = CategoryComboBox.SelectedItem?.ToString() ?? "",
                ScenarioType = ScenarioComboBox.SelectedItem?.ToString() ?? "", Question = QuestionTextBox.Text.Trim(),
                ExpectedOutcome = (OutcomeComboBox.SelectedItem as System.Windows.Controls.ComboBoxItem)?.Content?.ToString() ?? "SUFFICIENT",
                ExpectedEvidence = references.Where((_, i) => workspace.References[i].Kind == "포함").ToArray(),
                ExpectedExcluded = references.Where((_, i) => workspace.References[i].Kind == "제외").ToArray(),
                AllowedRankMin = min, AllowedRankMax = max,
                AsOf = new DateTimeOffset(AsOfDatePicker.SelectedDate ?? DateTime.Today),
                DataClassification = (ClassificationComboBox.SelectedItem as System.Windows.Controls.ComboBoxItem)?.Content?.ToString() ?? "ANONYMOUS_FIELD",
                ProvenanceNote = ProvenanceTextBox.Text.Trim(),
            });
            StatusTextBlock.Text = $"{created.CaseKey} 1차 등록 완료. 다른 사용자의 2차 승인이 필요합니다.";
            await RefreshAsync();
        }
        catch (Exception ex) { StatusTextBlock.Text = $"사례 등록 실패: {ex.Message}"; }
    }

    private async void SecondApproveButton_Click(object sender, RoutedEventArgs e)
    {
        if (client is null || CasePoolGrid.SelectedItem is not CasePoolRow row) return;
        try { await client.SecondApproveAIGroundTruthCaseAsync(row.GroundTruthCaseId); await RefreshAsync(); StatusTextBlock.Text = $"{row.CaseKey} 2차 승인을 완료했습니다."; }
        catch (Exception ex) { StatusTextBlock.Text = $"2차 승인 거부: {ex.Message}"; }
    }

    private sealed class EditorWorkspace
    {
        public ObservableCollection<CandidateRow> Candidates { get; } = [];
        public ObservableCollection<CasePoolRow> CasePool { get; } = [];
        public ObservableCollection<ReferenceRow> References { get; } = [];
    }
    private sealed record CandidateRow(string SourceType, string SourceId, string? SourceVersionId, string Title, string ContentHash)
    { public static CandidateRow From(ServerAISearchCandidateResponse x) => new(x.SourceType, x.SourceId, x.SourceVersionId, x.Title, x.ContentHash); }
    private sealed record CasePoolRow(string GroundTruthCaseId, string CaseKey, string ApprovalStatus)
    { public static CasePoolRow From(ServerAIGroundTruthCase x) => new(x.GroundTruthCaseId, x.CaseKey, x.Provenance?.ApprovalStatus ?? "UNKNOWN"); }
    private sealed record ReferenceRow(string Kind, string SourceType, string SourceId, string? SourceVersionId, string? ContentHash, string? ExclusionReason, string Rationale);
}
