using System.Windows;
using FlowNote.Windows.Core.Reports;

namespace FlowNote.Windows.App;

public partial class ReportSourceVerificationWindow : Window
{
    public ReportSourceVerificationWindow(IReadOnlyList<ReportSourceVerificationRecord> items)
    {
        InitializeComponent();
        DataContext = items;
        SummaryTextBlock.Text =
            $"원천 {items.Count}건 · 적격 {items.Count(item => item.Valid)}건 · 부적격 {items.Count(item => !item.Valid)}건";
    }
}
