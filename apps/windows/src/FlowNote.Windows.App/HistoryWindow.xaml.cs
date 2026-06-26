using System.Windows;
using FlowNote.Windows.Core.History;

namespace FlowNote.Windows.App;

public partial class HistoryWindow : Window
{
    private readonly HistoryService history;

    public HistoryWindow(HistoryService history)
    {
        InitializeComponent();
        this.history = history;
        RefreshHistory();
    }

    private void RefreshHistory()
    {
        var items = history.ListHistory();
        HistoryGrid.ItemsSource = items;
        SummaryTextBlock.Text = $"전체 이력 {items.Count}건";
    }

    private void RefreshButton_Click(object sender, RoutedEventArgs e)
    {
        RefreshHistory();
    }

    private void CloseButton_Click(object sender, RoutedEventArgs e)
    {
        Close();
    }
}
