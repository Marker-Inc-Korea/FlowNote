using System.Collections.ObjectModel;
using System.Net.Http;
using System.Windows;
using System.Windows.Controls;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.WorkSequences;

namespace FlowNote.Windows.App;

public partial class WorkSequenceAdminWindow : Window
{
    private readonly WorkSequenceService localWorkSequences;
    private readonly FlowNoteServerDocumentClient? serverClient;
    private readonly FlowNoteServerChannelClient? channelClient;
    private readonly string actorId;
    private readonly WorkSequenceWorkspace workspace = new();
    private bool hasAuthoritativeSnapshot;
    private bool refreshing;

    public WorkSequenceAdminWindow(
        WorkSequenceService localWorkSequences,
        FlowNoteServerDocumentClient? serverClient,
        FlowNoteServerChannelClient? channelClient,
        string actorId)
    {
        InitializeComponent();
        this.localWorkSequences = localWorkSequences;
        this.serverClient = serverClient;
        this.channelClient = channelClient;
        this.actorId = actorId;
        DataContext = workspace;
        Loaded += WorkSequenceAdminWindow_Loaded;
    }

    private async void WorkSequenceAdminWindow_Loaded(object sender, RoutedEventArgs e) =>
        await RefreshBoardsAsync();

    private async void RefreshButton_Click(object sender, RoutedEventArgs e) =>
        await RefreshBoardsAsync(CurrentBoard()?.BoardId);

    private async void CreateBoardButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureMutationAllowed()) return;
        var key = NewMutationKey("board");
        await RunMutationAsync(
            () => serverClient!.CreateWorkSequenceBoardAsync(new ServerWorkSequenceBoardCreateRequest
            {
                Title = BoardTitleTextBox.Text,
                LineCode = LineCodeTextBox.Text,
                BoardDate = DateOnly.FromDateTime(DateTime.Today),
                CreatedBy = actorId,
                IdempotencyKey = key
            }),
            result => $"작업판을 생성했습니다: {result.Title}");
    }

    private async void BoardListBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!refreshing && CurrentBoard() is { } board)
        {
            await RefreshItemsAsync(board.BoardId);
        }
    }

    private async void AddItemButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureMutationAllowed() || CurrentBoard() is not { } board)
        {
            StatusTextBlock.Text = CurrentBoard() is null
                ? "항목을 추가할 작업판을 선택하세요."
                : WorkSequenceServerPolicy.OfflineReadOnlyMessage;
            return;
        }

        var key = NewMutationKey("item");
        await RunMutationAsync(
            () => serverClient!.AddWorkSequenceItemAsync(board.BoardId, new ServerWorkSequenceItemCreateRequest
            {
                Title = ItemTitleTextBox.Text,
                AssignedTo = AssignedToTextBox.Text,
                CreatedBy = actorId,
                IdempotencyKey = key,
                BaseBoardRevision = board.BoardRevision
            }),
            result => $"항목을 추가했습니다: {result.Items.Last().Title}");
        ItemTitleTextBox.Clear();
    }

    private void MoveUpButton_Click(object sender, RoutedEventArgs e) => MoveSelectedItem(-1);

    private void MoveDownButton_Click(object sender, RoutedEventArgs e) => MoveSelectedItem(1);

    private async void SetStatusButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureMutationAllowed() || CurrentBoard() is not { } board ||
            ItemGrid.SelectedItem is not WorkSequenceItemRecord item)
        {
            StatusTextBlock.Text = hasAuthoritativeSnapshot
                ? "상태를 변경할 항목을 선택하세요."
                : WorkSequenceServerPolicy.OfflineReadOnlyMessage;
            return;
        }

        var status = (StatusComboBox.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "WAITING";
        var key = NewMutationKey("status");
        await RunMutationAsync(
            () => serverClient!.UpdateWorkSequenceItemStatusAsync(
                board.BoardId,
                item.ItemId,
                new ServerWorkSequenceStatusUpdateRequest
                {
                    Status = status,
                    ActorId = actorId,
                    ChangeReason = ReasonTextBox.Text,
                    HoldReason = status == "HOLD" ? ReasonTextBox.Text : null,
                    IdempotencyKey = key,
                    BaseBoardRevision = board.BoardRevision
                }),
            _ => $"상태를 변경했습니다: {item.Title} -> {FormatStatus(status)}");
    }

    private void OpenTvViewButton_Click(object sender, RoutedEventArgs e)
    {
        if (CurrentBoard() is not { } board)
        {
            StatusTextBlock.Text = "현황판을 열 작업판을 선택하세요.";
            return;
        }

        new WorkSequenceTvWindow(localWorkSequences, serverClient, board.BoardId) { Owner = this }.Show();
    }

    private void OpenDeliveryButton_Click(object sender, RoutedEventArgs e)
    {
        if (CurrentBoard() is not { } board || serverClient is null || channelClient is null)
        {
            StatusTextBlock.Text = "알림 후보 전달은 작업판 선택과 서버 연결이 필요합니다.";
            return;
        }

        new WorkSequenceDeliveryWindow(serverClient, channelClient, board, actorId)
        {
            Owner = this
        }.ShowDialog();
    }

    private async void MoveSelectedItem(int direction)
    {
        if (!EnsureMutationAllowed() || CurrentBoard() is not { } board ||
            ItemGrid.SelectedItem is not WorkSequenceItemRecord item)
        {
            StatusTextBlock.Text = hasAuthoritativeSnapshot
                ? "순서를 변경할 항목을 선택하세요."
                : WorkSequenceServerPolicy.OfflineReadOnlyMessage;
            return;
        }

        var ids = workspace.Items.Select(candidate => candidate.ItemId).ToList();
        var index = ids.IndexOf(item.ItemId);
        var targetIndex = index + direction;
        if (index < 0 || targetIndex < 0 || targetIndex >= ids.Count) return;
        (ids[index], ids[targetIndex]) = (ids[targetIndex], ids[index]);
        var key = NewMutationKey("order");
        await RunMutationAsync(
            () => serverClient!.ReorderWorkSequenceItemsAsync(board.BoardId, new ServerWorkSequenceReorderRequest
            {
                ItemIds = ids,
                ActorId = actorId,
                ChangeReason = ReasonTextBox.Text,
                IdempotencyKey = key,
                BaseBoardRevision = board.BoardRevision
            }),
            _ => "순서를 변경했습니다.");
        ItemGrid.SelectedItem = workspace.Items.FirstOrDefault(candidate => candidate.ItemId == item.ItemId);
    }

    private async Task RunMutationAsync(
        Func<Task<ServerWorkSequenceBoardResponse>> action,
        Func<ServerWorkSequenceBoardResponse, string> successMessage)
    {
        try
        {
            // 응답 유실 가능성이 있으므로 같은 request/key로 한 번만 직접 재시도한다.
            var result = await WorkSequenceServerPolicy.RunWithResponseLossRetryAsync(action);
            ApplyServerBoard(result);
            StatusTextBlock.Text = $"{successMessage(result)} (서버 revision {result.BoardRevision})";
        }
        catch (FlowNoteServerConflictException exception)
        {
            hasAuthoritativeSnapshot = false;
            ApplyMutationState();
            var message = WorkSequenceServerPolicy.ConflictMessage(exception);
            await RefreshBoardsAsync(CurrentBoard()?.BoardId, preserveStatus: true);
            StatusTextBlock.Text = message;
        }
        catch (Exception exception) when (exception is HttpRequestException or TaskCanceledException or InvalidOperationException)
        {
            hasAuthoritativeSnapshot = false;
            ApplyMutationState();
            StatusTextBlock.Text =
                $"서버 변경을 확정하지 못했습니다. 로컬 큐에는 넣지 않았습니다. 새로고침 후 다시 시도하세요. ({exception.Message})";
        }
    }

    private bool EnsureMutationAllowed()
    {
        if (WorkSequenceServerPolicy.CanMutate(serverClient, hasAuthoritativeSnapshot)) return true;
        StatusTextBlock.Text = WorkSequenceServerPolicy.OfflineReadOnlyMessage;
        return false;
    }

    private WorkSequenceBoardRecord? CurrentBoard() => BoardListBox.SelectedItem as WorkSequenceBoardRecord;

    private async Task RefreshBoardsAsync(string? selectBoardId = null, bool preserveStatus = false)
    {
        var selectedId = selectBoardId ?? CurrentBoard()?.BoardId;
        refreshing = true;
        try
        {
            workspace.Boards.Clear();
            if (serverClient is null)
            {
                LoadLocalBoards();
                hasAuthoritativeSnapshot = false;
                if (!preserveStatus) StatusTextBlock.Text = WorkSequenceServerPolicy.OfflineReadOnlyMessage;
            }
            else
            {
                var boards = await serverClient.ListWorkSequenceBoardsAsync();
                foreach (var board in boards)
                {
                    workspace.Boards.Add(new WorkSequenceBoardRecord(
                        0, board.BoardId, board.Title, null, board.LineCode,
                        board.BoardDate?.ToDateTime(TimeOnly.MinValue), board.Status, actorId,
                        board.UpdatedAt, board.UpdatedAt, board.ItemCount, board.BoardRevision, true));
                }
                hasAuthoritativeSnapshot = true;
                if (!preserveStatus) StatusTextBlock.Text = "서버 작업순서 snapshot을 새로고침했습니다.";
            }
            BoardListBox.SelectedItem = workspace.Boards.FirstOrDefault(board => board.BoardId == selectedId)
                ?? workspace.Boards.FirstOrDefault();
        }
        catch (Exception exception) when (exception is HttpRequestException or TaskCanceledException or InvalidOperationException)
        {
            workspace.Boards.Clear();
            LoadLocalBoards();
            hasAuthoritativeSnapshot = false;
            StatusTextBlock.Text = $"{WorkSequenceServerPolicy.OfflineReadOnlyMessage} ({exception.Message})";
        }
        finally
        {
            refreshing = false;
            ApplyMutationState();
        }
        if (CurrentBoard() is { } selected) await RefreshItemsAsync(selected.BoardId);
    }

    private async Task RefreshItemsAsync(string boardId)
    {
        if (serverClient is not null && hasAuthoritativeSnapshot)
        {
            try
            {
                ApplyServerBoard(await serverClient.GetWorkSequenceBoardAsync(boardId));
                return;
            }
            catch (Exception exception) when (exception is HttpRequestException or TaskCanceledException or InvalidOperationException)
            {
                hasAuthoritativeSnapshot = false;
                ApplyMutationState();
                StatusTextBlock.Text = $"서버 snapshot 조회에 실패했습니다. 현재 표시는 읽기 캐시입니다. ({exception.Message})";
            }
        }

        var board = localWorkSequences.GetBoard(boardId);
        SelectedBoardTextBlock.Text = board is null ? "작업판을 선택하세요" : $"{board.Title} ({board.ItemCount}개, 로컬 초안)";
        workspace.Items.Clear();
        foreach (var item in localWorkSequences.GetItems(boardId)) workspace.Items.Add(item);
    }

    private void ApplyServerBoard(ServerWorkSequenceBoardResponse board)
    {
        hasAuthoritativeSnapshot = true;
        var mappedBoard = new WorkSequenceBoardRecord(
            0, board.BoardId, board.Title, board.Description, board.LineCode,
            board.BoardDate?.ToDateTime(TimeOnly.MinValue), board.Status, board.CreatedBy ?? actorId,
            board.CreatedAt, board.UpdatedAt, board.Items.Count, board.BoardRevision, true);
        var index = workspace.Boards.ToList().FindIndex(candidate => candidate.BoardId == board.BoardId);
        if (index >= 0) workspace.Boards[index] = mappedBoard;
        else workspace.Boards.Insert(0, mappedBoard);
        BoardListBox.SelectedItem = mappedBoard;
        SelectedBoardTextBlock.Text = $"{board.Title} ({board.Items.Count}개, 서버 revision {board.BoardRevision})";
        workspace.Items.Clear();
        foreach (var item in board.Items.OrderBy(item => item.SortOrder))
        {
            workspace.Items.Add(new WorkSequenceItemRecord(
                0, item.ItemId, item.BoardId, item.Title, item.Description, item.WorkOrderNo,
                item.DocumentId, item.Status, item.HoldReason, item.SortOrder, item.AssignedTo,
                item.CreatedBy ?? actorId, item.CreatedAt, item.UpdatedAt));
        }
        ApplyMutationState();
    }

    private void LoadLocalBoards()
    {
        foreach (var board in localWorkSequences.ListBoards()) workspace.Boards.Add(board);
    }

    private void ApplyMutationState()
    {
        var enabled = WorkSequenceServerPolicy.CanMutate(serverClient, hasAuthoritativeSnapshot);
        CreateBoardButton.IsEnabled = enabled;
        AddItemButton.IsEnabled = enabled;
        MoveUpButton.IsEnabled = enabled;
        MoveDownButton.IsEnabled = enabled;
        SetStatusButton.IsEnabled = enabled;
        SourceModeTextBlock.Text = enabled
            ? "서버 권위 snapshot · 변경은 서버에 직접 저장"
            : "읽기 캐시/초안 · 서버 확정 변경 차단";
    }

    private static string NewMutationKey(string operation) => $"wpf:{operation}:{Guid.NewGuid():N}";

    private sealed class WorkSequenceWorkspace
    {
        public ObservableCollection<WorkSequenceBoardRecord> Boards { get; } = [];
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
