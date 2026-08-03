using System.Windows;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.App;

public partial class FieldCommentTraceabilityWindow : Window
{
    public FieldCommentTraceabilityWindow(ServerFieldCommentTraceResponse trace)
    {
        InitializeComponent();
        DataContext = trace;
    }
}
