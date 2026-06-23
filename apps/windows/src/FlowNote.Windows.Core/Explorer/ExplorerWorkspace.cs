using System.Collections.ObjectModel;
using System.ComponentModel;

namespace FlowNote.Windows.Core.Explorer;

public sealed class ExplorerWorkspace : INotifyPropertyChanged
{
    private string statusText = "로그인이 필요합니다.";

    public event PropertyChangedEventHandler? PropertyChanged;

    public ObservableCollection<ExplorerFolder> Folders { get; } = [];

    public ObservableCollection<ExplorerDocument> Documents { get; } = [];

    public ObservableCollection<UploadCandidate> UploadCandidates { get; } = [];

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

    public void AddUploadCandidate(UploadCandidate candidate)
    {
        UploadCandidates.Add(candidate);
        StatusText = $"업로드 후보 {UploadCandidates.Count}개";
    }

    public void AddDroppedFileToList(UploadCandidate candidate, string actorName)
    {
        AddDroppedFileToList(candidate, actorName, Path.GetFileNameWithoutExtension(candidate.FileName));
    }

    public void AddDroppedFileToList(UploadCandidate candidate, string actorName, string title)
    {
        AddUploadCandidate(candidate);
        Documents.Insert(0, new ExplorerDocument(
            string.IsNullOrWhiteSpace(title) ? candidate.FileName : title,
            candidate.FileName,
            string.IsNullOrWhiteSpace(candidate.Extension) ? "File" : candidate.Extension.TrimStart('.').ToUpperInvariant(),
            "업로드 후보",
            actorName,
            candidate.AddedAt,
            "draft",
            candidate.FullPath));
    }
}
