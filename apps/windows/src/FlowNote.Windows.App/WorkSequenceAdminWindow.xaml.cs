using System.Collections.ObjectModel;
using System.Windows;
using System.Windows.Controls;
using FlowNote.Windows.Core.WorkSequences;

namespace FlowNote.Windows.App;

public partial class WorkSequenceAdminWindow : Window
{
    private readonly WorkSequenceService workSequences;
    private readonly string actorName;
    private readonly WorkSequenceWorkspace workspace = new();

    public WorkSequenceAdminWindow(WorkSequenceService workSequences, string actorName)
    {
        InitializeComponent();
        this.workSequences = workSequences;
        this.actorName = actorName;
        DataContext = workspace;
        Loaded += WorkSequenceAdminWindow_Loaded;
    }

    private void WorkSequenceAdminWindow_Loaded(object sender, RoutedEventArgs e)
    {
        RefreshBoards();
    }

    private void CreateBoardButton_Click(object sender, RoutedEventArgs e)
    {
        var board = workSequences.CreateBoard(
            BoardTitleTextBox.Text,
            actorName,
            lineCode: LineCodeTextBox.Text,
            boardDate: DateTime.Today);
        RefreshBoards(board.BoardId);
        StatusTextBlock.Text = $"Board created: {board.Title}";
    }

    private void BoardListBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (BoardListBox.SelectedItem is WorkSequenceBoardRecord board)
        {
            RefreshItems(board.BoardId);
        }
    }

    private void AddItemButton_Click(object sender, RoutedEventArgs e)
    {
        if (CurrentBoard() is not { } board)
        {
            StatusTextBlock.Text = "Select a board before adding an item.";
            return;
        }

        var item = workSequences.AddItem(
            board.BoardId,
            ItemTitleTextBox.Text,
            actorName,
            assignedTo: AssignedToTextBox.Text);
        ItemTitleTextBox.Clear();
        RefreshItems(board.BoardId);
        RefreshBoards(board.BoardId);
        StatusTextBlock.Text = $"Item added: {item.Title}";
    }

    private void MoveUpButton_Click(object sender, RoutedEventArgs e)
    {
        MoveSelectedItem(-1);
    }

    private void MoveDownButton_Click(object sender, RoutedEventArgs e)
    {
        MoveSelectedItem(1);
    }

    private void SetStatusButton_Click(object sender, RoutedEventArgs e)
    {
        if (CurrentBoard() is not { } board || ItemGrid.SelectedItem is not WorkSequenceItemRecord item)
        {
            StatusTextBlock.Text = "Select an item before changing status.";
            return;
        }

        var status = (StatusComboBox.SelectedItem as ComboBoxItem)?.Content?.ToString() ?? "WAITING";
        workSequences.UpdateItemStatus(
            board.BoardId,
            item.ItemId,
            status,
            actorName,
            ReasonTextBox.Text,
            status == "HOLD" ? ReasonTextBox.Text : null);
        RefreshItems(board.BoardId);
        RefreshBoards(board.BoardId);
        StatusTextBlock.Text = $"Status changed: {item.Title} -> {status}";
    }

    private void OpenTvViewButton_Click(object sender, RoutedEventArgs e)
    {
        if (CurrentBoard() is not { } board)
        {
            StatusTextBlock.Text = "Select a board before opening TV view.";
            return;
        }

        var window = new WorkSequenceTvWindow(workSequences, board.BoardId)
        {
            Owner = this
        };
        window.Show();
    }

    private void MoveSelectedItem(int direction)
    {
        if (CurrentBoard() is not { } board || ItemGrid.SelectedItem is not WorkSequenceItemRecord item)
        {
            StatusTextBlock.Text = "Select an item before changing order.";
            return;
        }

        var ids = workspace.Items.Select(candidate => candidate.ItemId).ToList();
        var index = ids.IndexOf(item.ItemId);
        var targetIndex = index + direction;
        if (index < 0 || targetIndex < 0 || targetIndex >= ids.Count)
        {
            return;
        }

        (ids[index], ids[targetIndex]) = (ids[targetIndex], ids[index]);
        workSequences.ReorderItems(board.BoardId, ids, actorName, ReasonTextBox.Text);
        RefreshItems(board.BoardId);
        RefreshBoards(board.BoardId);
        ItemGrid.SelectedItem = workspace.Items.FirstOrDefault(candidate => candidate.ItemId == item.ItemId);
        StatusTextBlock.Text = "Order changed.";
    }

    private WorkSequenceBoardRecord? CurrentBoard()
    {
        return BoardListBox.SelectedItem as WorkSequenceBoardRecord;
    }

    private void RefreshBoards(string? selectBoardId = null)
    {
        var selectedId = selectBoardId ?? CurrentBoard()?.BoardId;
        workspace.Boards.Clear();
        foreach (var board in workSequences.ListBoards())
        {
            workspace.Boards.Add(board);
        }

        if (!string.IsNullOrWhiteSpace(selectedId))
        {
            BoardListBox.SelectedItem = workspace.Boards.FirstOrDefault(board => board.BoardId == selectedId);
        }
    }

    private void RefreshItems(string boardId)
    {
        var board = workSequences.GetBoard(boardId);
        SelectedBoardTextBlock.Text = board is null
            ? "Select or create a board"
            : $"{board.Title} ({board.ItemCount} items)";
        workspace.Items.Clear();
        foreach (var item in workSequences.GetItems(boardId))
        {
            workspace.Items.Add(item);
        }
    }

    private sealed class WorkSequenceWorkspace
    {
        public ObservableCollection<WorkSequenceBoardRecord> Boards { get; } = [];

        public ObservableCollection<WorkSequenceItemRecord> Items { get; } = [];
    }
}
