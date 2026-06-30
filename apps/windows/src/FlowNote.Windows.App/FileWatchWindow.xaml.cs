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
            Title = "Select watch folder"
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
            UpdateWatchStatus("File watch started.");
        }
        catch (Exception exception) when (exception is ArgumentException or DirectoryNotFoundException or UnauthorizedAccessException)
        {
            UpdateWatchStatus(exception.Message);
        }
    }

    private void StopWatchButton_Click(object sender, RoutedEventArgs e)
    {
        fileWatch.StopWatching(actorName);
        UpdateWatchStatus("File watch stopped.");
    }

    private void RefreshButton_Click(object sender, RoutedEventArgs e)
    {
        RefreshDocuments();
        RefreshCandidates();
        UpdateWatchStatus("Candidate list refreshed.");
    }

    private void ConfirmButton_Click(object sender, RoutedEventArgs e)
    {
        if (CandidateGrid.SelectedItem is not FileWatchCandidateRecord candidate)
        {
            UpdateWatchStatus("Select a watch candidate.");
            return;
        }

        if (DocumentComboBox.SelectedItem is not DocumentOption document)
        {
            UpdateWatchStatus("Select the target document.");
            return;
        }

        if (string.IsNullOrWhiteSpace(VersionLabelTextBox.Text))
        {
            UpdateWatchStatus("Version label is required.");
            return;
        }

        if (string.IsNullOrWhiteSpace(ChangeReasonTextBox.Text))
        {
            UpdateWatchStatus("Change reason is required.");
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
            UpdateWatchStatus($"Confirmed {candidate.FileName} as {updated.Title} v{updated.VersionNo}.");
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
            UpdateWatchStatus("Select a watch candidate.");
            return;
        }

        try
        {
            fileWatch.IgnoreCandidate(candidate.CandidateId, actorName);
            RefreshCandidates();
            UpdateWatchStatus($"Ignored {candidate.FileName}.");
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
            ? $"Watching: {fileWatch.WatchedFolderPath}"
            : "File watch is stopped.";
        StatusTextBlock.Text = string.IsNullOrWhiteSpace(message)
            ? watchState
            : $"{message} {watchState}";
    }

    private sealed record DocumentOption(string DocumentId, string DisplayText, int VersionNo);
}
