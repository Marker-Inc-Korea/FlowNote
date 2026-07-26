using System.Windows;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.App;

public partial class FieldCommentQualityIssueWindow : Window
{
    public FieldCommentQualityIssueWindow(IReadOnlyList<ServerFieldCommentQualityItemResponse> items)
    {
        InitializeComponent();
        DataContext = items;
        SummaryTextBlock.Text =
            $"전체 {items.Count}건 · " +
            string.Join(" · ", items.GroupBy(item => item.IssueType).Select(group => $"{group.Key} {group.Count()}건"));
    }
}
