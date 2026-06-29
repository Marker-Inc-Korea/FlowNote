using System.Collections.ObjectModel;
using System.Windows;
using FlowNote.Windows.Core.WorkSequences;

namespace FlowNote.Windows.App;

public partial class WorkSequenceTvWindow : Window
{
    private readonly WorkSequenceService workSequences;
    private readonly string boardId;
    private readonly WorkSequenceTvWorkspace workspace = new();

    public WorkSequenceTvWindow(WorkSequenceService workSequences, string boardId)
    {
        InitializeComponent();
        this.workSequences = workSequences;
        this.boardId = boardId;
        DataContext = workspace;
        Loaded += WorkSequenceTvWindow_Loaded;
    }

    private void WorkSequenceTvWindow_Loaded(object sender, RoutedEventArgs e)
    {
        Refresh();
    }

    private void RefreshButton_Click(object sender, RoutedEventArgs e)
    {
        Refresh();
    }

    private void Refresh()
    {
        var board = workSequences.GetBoard(boardId);
        if (board is null)
        {
            TitleTextBlock.Text = "Work Sequence";
            MetaTextBlock.Text = "Board not found";
            StatusTextBlock.Text = string.Empty;
            return;
        }

        TitleTextBlock.Text = board.Title;
        MetaTextBlock.Text = $"{board.LineCode ?? "line"}  {board.BoardDate:yyyy-MM-dd}  {board.Status}";
        workspace.Items.Clear();
        foreach (var item in workSequences.GetItems(boardId))
        {
            workspace.Items.Add(item);
        }

        StatusTextBlock.Text = $"Read-only TV view refreshed at {DateTime.Now:yyyy-MM-dd HH:mm:ss}";
    }

    private sealed class WorkSequenceTvWorkspace
    {
        public ObservableCollection<WorkSequenceItemRecord> Items { get; } = [];
    }
}
