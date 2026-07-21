using System.Collections.ObjectModel;
using System.Net.Http;
using System.Windows;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.WorkSequences;

namespace FlowNote.Windows.App;

public partial class WorkSequenceTvWindow : Window
{
    private readonly WorkSequenceService localWorkSequences;
    private readonly FlowNoteServerDocumentClient? serverClient;
    private readonly string boardId;
    private readonly WorkSequenceTvWorkspace workspace = new();

    public WorkSequenceTvWindow(
        WorkSequenceService localWorkSequences,
        FlowNoteServerDocumentClient? serverClient,
        string boardId)
    {
        InitializeComponent();
        this.localWorkSequences = localWorkSequences;
        this.serverClient = serverClient;
        this.boardId = boardId;
        DataContext = workspace;
        Loaded += WorkSequenceTvWindow_Loaded;
    }

    private async void WorkSequenceTvWindow_Loaded(object sender, RoutedEventArgs e) => await RefreshAsync();

    private async void RefreshButton_Click(object sender, RoutedEventArgs e) => await RefreshAsync();

    private async Task RefreshAsync()
    {
        if (serverClient is not null)
        {
            try
            {
                var board = await serverClient.GetWorkSequenceBoardAsync(boardId);
                TitleTextBlock.Text = board.Title;
                MetaTextBlock.Text =
                    $"{board.LineCode ?? "라인"}  {board.BoardDate:yyyy-MM-dd}  {FormatStatus(board.Status)}  서버 revision {board.BoardRevision}";
                workspace.Items.Clear();
                foreach (var item in board.Items.OrderBy(item => item.SortOrder))
                {
                    workspace.Items.Add(new WorkSequenceItemRecord(
                        0, item.ItemId, item.BoardId, item.Title, item.Description, item.WorkOrderNo,
                        item.DocumentId, item.Status, item.HoldReason, item.SortOrder, item.AssignedTo,
                        item.CreatedBy ?? "server", item.CreatedAt, item.UpdatedAt));
                }
                StatusTextBlock.Text = $"서버 권위 snapshot을 새로고침했습니다: {DateTime.Now:yyyy-MM-dd HH:mm:ss}";
                return;
            }
            catch (Exception exception) when (exception is HttpRequestException or TaskCanceledException or InvalidOperationException)
            {
                StatusTextBlock.Text = $"서버 조회 실패: 로컬 읽기 캐시/초안을 표시합니다. ({exception.Message})";
            }
        }
        else
        {
            StatusTextBlock.Text = WorkSequenceServerPolicy.OfflineReadOnlyMessage;
        }

        var localBoard = localWorkSequences.GetBoard(boardId);
        if (localBoard is null)
        {
            TitleTextBlock.Text = "작업순서";
            MetaTextBlock.Text = "읽기 캐시에서 작업판을 찾을 수 없습니다";
            workspace.Items.Clear();
            return;
        }
        TitleTextBlock.Text = $"{localBoard.Title} · 로컬 초안";
        MetaTextBlock.Text = $"{localBoard.LineCode ?? "라인"}  {localBoard.BoardDate:yyyy-MM-dd}  {FormatStatus(localBoard.Status)}";
        workspace.Items.Clear();
        foreach (var item in localWorkSequences.GetItems(boardId)) workspace.Items.Add(item);
    }

    private sealed class WorkSequenceTvWorkspace
    {
        public ObservableCollection<WorkSequenceItemRecord> Items { get; } = [];
    }

    private static string FormatStatus(string status) => status switch
    {
        "WAITING" => "대기",
        "IN_PROGRESS" => "진행중",
        "HOLD" => "보류",
        "COMPLETED" => "완료",
        _ => status
    };
}
