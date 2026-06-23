using System.Collections.ObjectModel;
using System.ComponentModel;

namespace FlowNote.Windows.Core.Explorer;

public sealed class ExplorerWorkspace : INotifyPropertyChanged
{
    private string statusText = "Login required.";

    public event PropertyChangedEventHandler? PropertyChanged;

    public ObservableCollection<ExplorerFolder> Folders { get; } = [];

    public ObservableCollection<ExplorerDocument> Documents { get; } = [];

    public string StatusText
    {
        get => statusText;
        set
        {
            if (statusText == value)
            {
                return;
            }

            statusText = value;
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(StatusText)));
        }
    }
}
