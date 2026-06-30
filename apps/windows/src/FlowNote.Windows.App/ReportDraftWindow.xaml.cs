using System.Collections.ObjectModel;
using System.Windows;
using FlowNote.Windows.Core.Reports;

namespace FlowNote.Windows.App;

public partial class ReportDraftWindow : Window
{
    private readonly ReportDraftService reports;
    private readonly long targetFolderId;
    private readonly string actorName;
    private readonly ReportDraftWorkspace workspace = new();

    public ReportDraftWindow(ReportDraftService reports, long targetFolderId, string actorName)
    {
        InitializeComponent();
        this.reports = reports;
        this.targetFolderId = targetFolderId;
        this.actorName = actorName;
        DataContext = workspace;
        Loaded += ReportDraftWindow_Loaded;
    }

    public bool DocumentSaved { get; private set; }

    private void ReportDraftWindow_Loaded(object sender, RoutedEventArgs e)
    {
        RefreshSources();
        StatusTextBlock.Text = "현장 코멘트 원천을 하나 이상 선택한 뒤 초안을 생성하세요.";
    }

    private void BuildDraftButton_Click(object sender, RoutedEventArgs e)
    {
        var selected = SelectedSources().ToList();
        if (!selected.Any(source => source.SourceType == "FIELD_COMMENT"))
        {
            StatusTextBlock.Text = "현장 코멘트 원천을 하나 이상 선택하세요.";
            return;
        }

        DraftTextBox.Text = reports.BuildDraftContent(
            TitleTextBox.Text,
            SummaryTextBox.Text,
            selected,
            actorName);
        StatusTextBlock.Text = $"선택한 원천 {selected.Count}건으로 초안을 생성했습니다.";
    }

    private void SaveDocumentButton_Click(object sender, RoutedEventArgs e)
    {
        var content = DraftTextBox.Text;
        if (string.IsNullOrWhiteSpace(content))
        {
            BuildDraftButton_Click(sender, e);
            content = DraftTextBox.Text;
        }

        if (string.IsNullOrWhiteSpace(content))
        {
            return;
        }

        var document = reports.SaveDraftAsDocument(
            targetFolderId,
            TitleTextBox.Text,
            content,
            actorName);
        DocumentSaved = true;
        StatusTextBlock.Text = $"보고서 문서를 저장했습니다: {document.Title} ({document.Status})";
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
    }
}
