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
            TitleTextBlock.Text = "작업순서";
            MetaTextBlock.Text = "작업판을 찾을 수 없습니다";
            StatusTextBlock.Text = string.Empty;
            return;
        }

        TitleTextBlock.Text = board.Title;
        MetaTextBlock.Text = $"{board.LineCode ?? "라인"}  {board.BoardDate:yyyy-MM-dd}  {FormatStatus(board.Status)}";
        workspace.Items.Clear();
        foreach (var item in workSequences.GetItems(boardId))
        {
            workspace.Items.Add(item);
        }

        StatusTextBlock.Text = $"읽기 전용 현황판을 새로고침했습니다: {DateTime.Now:yyyy-MM-dd HH:mm:ss}";
    }

    private sealed class WorkSequenceTvWorkspace
    {
        public ObservableCollection<WorkSequenceItemRecord> Items { get; } = [];
    }

    private static string FormatStatus(string status)
    {
        return status switch
        {
            "WAITING" => "대기",
            "IN_PROGRESS" => "진행중",
            "HOLD" => "보류",
            "COMPLETED" => "완료",
            _ => status
        };
    }
}
