using System.Collections.ObjectModel;
using System.Net.Http;
using System.Windows;
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

    private async void SaveDocumentButton_Click(object sender, RoutedEventArgs e)
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

        var selected = SelectedSources().ToList();
        if (serverReports is not null)
        {
            try
            {
                var result = await reports.SaveDraftToServerAsync(
                    serverReports,
                    targetFolderId,
                    TitleTextBox.Text,
                    SummaryTextBox.Text,
                    content,
                    selected,
                    actorName);
                DocumentSaved = result.LocalDocument is not null;
                StatusTextBlock.Text = $"서버 보고서를 저장했습니다: {result.ReportId} / {result.GeneratedDocumentId ?? "생성 문서 없음"}";
                return;
            }
            catch (Exception exception) when (exception is InvalidOperationException or HttpRequestException or TaskCanceledException)
            {
                StatusTextBlock.Text = $"서버 보고서 저장을 건너뛰고 로컬 문서로 저장합니다. {exception.Message}";
            }
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
