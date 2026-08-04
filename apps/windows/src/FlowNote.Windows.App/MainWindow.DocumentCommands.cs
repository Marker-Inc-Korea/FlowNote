using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using FlowNote.Windows.Core.Explorer;
using FlowNote.Windows.Core.Folders;
using FlowNote.Windows.Core.ServerApi;
using Microsoft.Win32;

namespace FlowNote.Windows.App;

public partial class MainWindow
{
    private void NewFolderButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureDocumentRegistrationAllowed())
        {
            return;
        }

        var parent = selectedFolder is null
            ? services.Folders.GetRootFolder()
            : services.Folders.GetFolder(selectedFolder.Id);
        var folder = services.Folders.CreateFolder(
            $"새 폴더 {DateTime.Now:HHmmss}",
            parent.Id,
            actorName: GetCurrentActorName());
        RefreshWorkspace("폴더를 생성했습니다.", folder.Id);
    }

    private void RegisterDocumentButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureDocumentRegistrationAllowed())
        {
            return;
        }

        var folder = GetSelectedFolderOrDefault();
        var fileName = $"sample-{DateTime.Now:HHmmss}.txt";
        var actorName = GetCurrentActorName();
        var plan = services.DocumentPlacement.PrepareDocumentRegistration(
            folder.Id,
            fileName,
            DateTime.Now,
            actorName);

        services.Documents.RegisterDocument(
            plan.Folder.Id,
            plan.Title,
            fileName,
            "Text",
            actorName,
            tags: BuildRegistrationTags(plan.Folder, fileName, "Text"));

        RefreshWorkspace($"문서를 등록했습니다. 위치: {plan.Folder.Path}", plan.Folder.Id);
    }

    private async void ApplyDocumentStatusButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureDocumentGovernanceAllowed())
        {
            return;
        }

        if (DocumentGrid.SelectedItem is not ExplorerDocument document)
        {
            workspace.StatusText = "상태를 변경할 문서를 선택하세요.";
            return;
        }

        var selectedStatus = (sender as MenuItem)?.Tag?.ToString()
            ?? (DocumentStatusComboBox.SelectedItem as ComboBoxItem)?.Tag?.ToString();
        if (string.IsNullOrWhiteSpace(selectedStatus))
        {
            workspace.StatusText = "문서 상태를 선택하세요.";
            return;
        }

        try
        {
            var updated = services.Documents.UpdateDocumentStatus(
                document.DocumentId,
                selectedStatus,
                GetCurrentActorName());
            var syncResult = await services.ServerSync.QueueAndTrySyncDocumentStatusAsync(
                updated,
                serverDocumentClient,
                currentUser.UserId);
            var statusText = syncResult.Success
                ? $"문서 상태를 변경하고 서버에 반영했습니다: {FormatDocumentStatus(selectedStatus)}"
                : $"문서 상태를 변경했습니다: {FormatDocumentStatus(selectedStatus)}. 서버 동기화는 큐에 남겼습니다. {syncResult.Message}";
            RefreshDocuments(selectedFolder?.Id, statusText);
        }
        catch (InvalidOperationException exception)
        {
            workspace.StatusText = exception.Message;
            RefreshSyncState();
        }
    }

    private void PublishDocumentButton_Click(object sender, RoutedEventArgs e)
    {
        if (!canRegisterDocuments)
        {
            workspace.StatusText = "검토 요청에는 문서 작성 권한이 필요합니다. 시스템 관리자에게 문의하세요.";
            return;
        }
        if (serverHttpClient is null)
        {
            workspace.StatusText = "승인 작업함은 서버 로그인 연결이 필요합니다.";
            return;
        }
        var initialDocumentId = DocumentGrid.SelectedItem is ExplorerDocument selected
            ? services.ServerSync.GetControlledCopyServerMapping(selected.DocumentId, selected.VersionNo)?.ServerDocumentId
            : null;
        var window = new DocumentApprovalWindow(
            new FlowNoteServerApprovalClient(serverHttpClient),
            canRegisterDocuments,
            canGovernDocuments,
            initialDocumentId)
        {
            Owner = this
        };
        window.ShowDialog();
        RefreshDocuments(selectedFolder?.Id, "서버 승인 작업함을 닫았습니다. 공개 상태는 서버 승인 이력을 기준으로 확인하세요.");
    }

    private async void UploadFileButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureDocumentRegistrationAllowed())
        {
            return;
        }

        var dialog = new OpenFileDialog
        {
            Title = "업로드할 파일 선택",
            Multiselect = true,
            Filter = "문서 파일|*.pdf;*.txt;*.xlsx;*.jpg;*.jpeg;*.png;*.bmp;*.gif|PDF 파일|*.pdf|모든 파일|*.*"
        };

        if (dialog.ShowDialog(this) != true)
        {
            return;
        }

        var folder = GetSelectedFolderOrDefault();
        await RegisterUploadedFilesAsync(dialog.FileNames, folder, "파일 업로드");
    }

    private void FileListDropZone_DragEnter(object sender, DragEventArgs e)
    {
        if (canRegisterDocuments && HasFileDrop(e))
        {
            FileListPanel.Background = new SolidColorBrush(Color.FromRgb(232, 246, 240));
            e.Effects = DragDropEffects.Copy;
        }
        else
        {
            e.Effects = DragDropEffects.None;
        }

        e.Handled = true;
    }

    private void FileListDropZone_DragLeave(object sender, DragEventArgs e)
    {
        FileListPanel.Background = (Brush)FindResource("PanelBackgroundBrush");
        e.Handled = true;
    }

    private void FileListDropZone_DragOver(object sender, DragEventArgs e)
    {
        e.Effects = canRegisterDocuments && HasFileDrop(e)
            ? DragDropEffects.Copy
            : DragDropEffects.None;
        e.Handled = true;
    }

    private async void FileListDropZone_Drop(object sender, DragEventArgs e)
    {
        FileListPanel.Background = (Brush)FindResource("PanelBackgroundBrush");
        if (!EnsureDocumentRegistrationAllowed())
        {
            e.Handled = true;
            return;
        }

        if (!HasFileDrop(e))
        {
            return;
        }

        var files = (string[])e.Data.GetData(DataFormats.FileDrop);
        var folder = GetSelectedFolderOrDefault();
        e.Handled = true;
        await RegisterUploadedFilesAsync(files, folder, "Drag & Drop 업로드");
    }

    private async Task RegisterUploadedFilesAsync(
        IEnumerable<string> files,
        DocumentFolder selectedTargetFolder,
        string sourceLabel)
    {
        if (!EnsureDocumentRegistrationAllowed())
        {
            return;
        }

        var addedCount = 0;
        var serverRegisteredCount = 0;
        var serverSyncFailures = new List<string>();
        long? lastTargetFolderId = null;
        var actorName = GetCurrentActorName();

        foreach (var file in files.Where(File.Exists))
        {
            var fileInfo = new FileInfo(file);
            var createdAt = DateTime.Now;
            var plan = services.DocumentPlacement.PrepareDocumentRegistration(
                selectedTargetFolder.Id,
                fileInfo.Name,
                createdAt,
                actorName);
            var storedRelativePath = CopyFileToAppStorage(fileInfo, createdAt);
            var documentType = ResolveDocumentType(fileInfo.Extension);
            var tags = BuildRegistrationTags(plan.Folder, fileInfo.Name, documentType);
            var document = services.Documents.RegisterDocument(
                plan.Folder.Id,
                plan.Title,
                fileInfo.Name,
                documentType,
                actorName,
                storedRelativePath,
                tags);

            addedCount++;
            lastTargetFolderId = plan.Folder.Id;

            var syncResult = await services.ServerSync.QueueAndTrySyncDocumentAsync(
                document,
                serverDocumentClient,
                currentUser.UserId);
            serverRegisteredCount += syncResult.Synced;
            if (!syncResult.Success)
            {
                serverSyncFailures.Add(syncResult.Message);
            }
        }

        var status = $"{sourceLabel}: {addedCount}개 파일을 DB에 저장했습니다.";
        if (serverDocumentClient is not null)
        {
            status = serverSyncFailures.Count == 0
                ? $"{status} 서버 {serverRegisteredCount}개 등록 완료."
                : $"{status} 서버 등록 실패: {serverSyncFailures[0]}";
        }

        RefreshWorkspace(
            status,
            lastTargetFolderId ?? selectedTargetFolder.Id);
    }

    private string CopyFileToAppStorage(FileInfo sourceFile, DateTime createdAt)
    {
        var dataDirectory = Path.GetDirectoryName(services.Database.DatabasePath)!;
        var uploadRoot = Path.Combine(
            dataDirectory,
            "Files",
            "Uploads",
            createdAt.ToString("yyyy-MM-dd"));
        Directory.CreateDirectory(uploadRoot);

        var targetPath = GetUniqueTargetPath(uploadRoot, sourceFile.Name);
        File.Copy(sourceFile.FullName, targetPath);
        return Path.GetRelativePath(dataDirectory, targetPath);
    }

    private static string GetUniqueTargetPath(string directory, string fileName)
    {
        var candidate = Path.Combine(directory, fileName);
        if (!File.Exists(candidate))
        {
            return candidate;
        }

        var name = Path.GetFileNameWithoutExtension(fileName);
        var extension = Path.GetExtension(fileName);
        var index = 1;
        do
        {
            candidate = Path.Combine(directory, $"{name}-{index:00}{extension}");
            index++;
        }
        while (File.Exists(candidate));

        return candidate;
    }

    private static string ResolveDocumentType(string extension)
    {
        return extension.ToLowerInvariant() switch
        {
            ".pdf" => "PDF",
            ".txt" => "Text",
            ".xlsx" => "Spreadsheet",
            ".jpg" or ".jpeg" or ".png" or ".bmp" or ".gif" => "Image",
            _ => string.IsNullOrWhiteSpace(extension)
                ? "File"
                : extension.TrimStart('.').ToUpperInvariant()
        };
    }

    private IReadOnlyList<string> BuildRegistrationTags(
        DocumentFolder folder,
        string fileName,
        string documentType)
    {
        var tags = new List<string>();
        AddTag(tags, folder.Name);
        AddTag(tags, documentType);

        var extension = Path.GetExtension(fileName).TrimStart('.');
        if (!string.IsNullOrWhiteSpace(extension))
        {
            AddTag(tags, extension.ToUpperInvariant());
        }

        foreach (var manualTag in TagInputTextBox.Text.Split(
            ',',
            StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            AddTag(tags, manualTag);
        }

        return tags;
    }

    private static void AddTag(List<string> tags, string? tag)
    {
        if (string.IsNullOrWhiteSpace(tag))
        {
            return;
        }

        if (tags.Any(existing =>
            string.Equals(existing, tag.Trim(), StringComparison.OrdinalIgnoreCase)))
        {
            return;
        }

        tags.Add(tag.Trim());
    }

    private static bool HasFileDrop(DragEventArgs e)
    {
        return e.Data.GetDataPresent(DataFormats.FileDrop);
    }

    private void DocumentGrid_MouseDoubleClick(object sender, MouseButtonEventArgs e)
    {
        OpenSelectedDocument();
    }

    private void OpenSelectedDocument()
    {
        if (DocumentGrid.SelectedItem is not ExplorerDocument document)
        {
            workspace.StatusText = "열람할 문서를 선택하거나 검색어를 입력한 뒤 Enter를 누르세요.";
            return;
        }

        var viewWindow = string.IsNullOrWhiteSpace(document.DocumentId)
            ? new DocumentViewWindow(document)
            : new DocumentViewWindow(
                services.FieldComments,
                serverDocumentClient,
                services.ServerSync,
                services.DocumentViewLogs,
                services.History,
                document,
                currentUser.DisplayName ?? currentUser.LoginId ?? "admin",
                currentUser.Role);
        viewWindow.Owner = this;

        viewWindow.ShowDialog();
        if (viewWindow.CommentSaved)
        {
            RefreshDocuments(
                selectedFolder?.Id,
                selectedFolder is null
                    ? "FieldComment를 저장했습니다."
                    : $"FieldComment를 저장했습니다. 위치: {selectedFolder.Path}");
            RefreshNotificationButton();
        }
    }
}
