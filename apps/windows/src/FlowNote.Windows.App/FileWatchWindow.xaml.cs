using System.IO;
using System.Windows;
using System.Windows.Controls;
using FlowNote.Windows.Core.Documents;
using FlowNote.Windows.Core.FileWatching;
using Microsoft.Win32;

namespace FlowNote.Windows.App;

public partial class FileWatchWindow : Window
{
    private readonly FileWatchService fileWatch;
    private readonly DocumentService documents;
    private readonly string actorName;
    private IReadOnlyList<DocumentOption> documentOptions = [];

    public FileWatchWindow(FileWatchService fileWatch, DocumentService documents, string actorName)
    {
        InitializeComponent();
        this.fileWatch = fileWatch;
        this.documents = documents;
        this.actorName = actorName;
        WatchFolderTextBox.Text = fileWatch.WatchedFolderPath ?? string.Empty;
        fileWatch.CandidateDetected += FileWatch_CandidateDetected;
        RefreshDocuments();
        RefreshCandidates();
        UpdateWatchStatus();
    }

    protected override void OnClosed(EventArgs e)
    {
        fileWatch.CandidateDetected -= FileWatch_CandidateDetected;
        base.OnClosed(e);
    }

    private void BrowseButton_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFolderDialog
        {
            Title = "감시 폴더 선택"
        };

        if (dialog.ShowDialog(this) == true)
        {
            WatchFolderTextBox.Text = dialog.FolderName;
        }
    }

    private void StartWatchButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            fileWatch.StartWatching(WatchFolderTextBox.Text, actorName);
            UpdateWatchStatus("파일 감시를 시작했습니다.");
        }
        catch (Exception exception) when (exception is ArgumentException or DirectoryNotFoundException or UnauthorizedAccessException)
        {
            UpdateWatchStatus(exception.Message);
        }
    }

    private void StopWatchButton_Click(object sender, RoutedEventArgs e)
    {
        fileWatch.StopWatching(actorName);
        UpdateWatchStatus("파일 감시를 중지했습니다.");
    }

    private void RefreshButton_Click(object sender, RoutedEventArgs e)
    {
        RefreshDocuments();
        RefreshCandidates();
        UpdateWatchStatus("후보 목록을 새로고침했습니다.");
    }

    private void ConfirmButton_Click(object sender, RoutedEventArgs e)
    {
        if (CandidateGrid.SelectedItem is not FileWatchCandidateRecord candidate)
        {
            UpdateWatchStatus("감시 후보를 선택하세요.");
            return;
        }

        if (DocumentComboBox.SelectedItem is not DocumentOption document)
        {
            UpdateWatchStatus("대상 문서를 선택하세요.");
            return;
        }

        if (string.IsNullOrWhiteSpace(VersionLabelTextBox.Text))
        {
            UpdateWatchStatus("버전 라벨을 입력하세요.");
            return;
        }

        if (string.IsNullOrWhiteSpace(ChangeReasonTextBox.Text))
        {
            UpdateWatchStatus("변경 사유를 입력하세요.");
            return;
        }

        try
        {
            var updated = fileWatch.ConfirmCandidate(
                candidate.CandidateId,
                document.DocumentId,
                VersionLabelTextBox.Text,
                ChangeReasonTextBox.Text,
                actorName);
            RefreshDocuments();
            RefreshCandidates();
            UpdateWatchStatus($"{candidate.FileName}을 {updated.Title} v{updated.VersionNo}로 확정했습니다.");
        }
        catch (Exception exception) when (exception is ArgumentException or InvalidOperationException or IOException or UnauthorizedAccessException)
        {
            UpdateWatchStatus(exception.Message);
        }
    }

    private void IgnoreButton_Click(object sender, RoutedEventArgs e)
    {
        if (CandidateGrid.SelectedItem is not FileWatchCandidateRecord candidate)
        {
            UpdateWatchStatus("감시 후보를 선택하세요.");
            return;
        }

        try
        {
            fileWatch.IgnoreCandidate(candidate.CandidateId, actorName);
            RefreshCandidates();
            UpdateWatchStatus($"{candidate.FileName} 후보를 무시했습니다.");
        }
        catch (InvalidOperationException exception)
        {
            UpdateWatchStatus(exception.Message);
        }
    }

    private void CloseButton_Click(object sender, RoutedEventArgs e)
    {
        Close();
    }

    private void CandidateGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (CandidateGrid.SelectedItem is not FileWatchCandidateRecord candidate)
        {
            return;
        }

        if (!string.IsNullOrWhiteSpace(candidate.DocumentId))
        {
            DocumentComboBox.SelectedValue = candidate.DocumentId;
        }

        if (string.IsNullOrWhiteSpace(VersionLabelTextBox.Text))
        {
            var selectedDocument = documentOptions.FirstOrDefault(item => item.DocumentId == candidate.DocumentId);
            int? nextVersion = selectedDocument is null ? null : selectedDocument.VersionNo + 1;
            VersionLabelTextBox.Text = nextVersion is null ? string.Empty : $"v{nextVersion}";
        }
    }

    private void FileWatch_CandidateDetected(object? sender, FileWatchCandidateRecord e)
    {
        Dispatcher.Invoke(RefreshCandidates);
    }

    private void RefreshDocuments()
    {
        documentOptions = documents.ListDocuments()
            .Select(item => new DocumentOption(
                item.DocumentId,
                $"{item.Title} ({item.FileName}) v{item.VersionNo}",
                item.VersionNo))
            .ToList();
        DocumentComboBox.ItemsSource = documentOptions;
    }

    private void RefreshCandidates()
    {
        CandidateGrid.ItemsSource = fileWatch.ListCandidates();
    }

    private void UpdateWatchStatus(string? message = null)
    {
        var watchState = fileWatch.IsRunning
            ? $"감시 중: {fileWatch.WatchedFolderPath}"
            : "파일 감시가 중지되어 있습니다.";
        StatusTextBlock.Text = string.IsNullOrWhiteSpace(message)
            ? watchState
            : $"{message} {watchState}";
    }

    private sealed record DocumentOption(string DocumentId, string DisplayText, int VersionNo);
}
