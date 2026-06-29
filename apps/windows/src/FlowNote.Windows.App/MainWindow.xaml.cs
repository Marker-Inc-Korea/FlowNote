using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Windows;
using System.Windows.Media;
using System.Windows.Controls;
using System.Windows.Input;
using FlowNote.Windows.Core.Auth;
using FlowNote.Windows.Core.Documents;
using FlowNote.Windows.Core.Explorer;
using FlowNote.Windows.Core.Folders;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Storage;
using Microsoft.Win32;

namespace FlowNote.Windows.App;

public partial class MainWindow : Window
{
    private readonly FlowNoteLocalServices services;
    private readonly LoginResult currentUser;
    private readonly HttpClient? serverHttpClient;
    private readonly FlowNoteServerDocumentClient? serverDocumentClient;
    private readonly bool canRegisterDocuments;
    private readonly ExplorerWorkspace workspace = new();
    private ExplorerFolder? selectedFolder;

    public MainWindow(FlowNoteLocalServices services, LoginResult currentUser)
    {
        InitializeComponent();
        this.services = services;
        this.currentUser = currentUser;
        canRegisterDocuments = RolePermissionPolicy.CanRegisterDocuments(currentUser.Role);
        (serverDocumentClient, serverHttpClient) = CreateServerDocumentClient(currentUser);
        SignedInUserTextBlock.Text = $"{currentUser.DisplayName} ({currentUser.Role})";
        DataContext = workspace;
        ApplyRolePermissions();
        Loaded += MainWindow_Loaded;
        RefreshWorkspace("로컬 작업 공간을 열었습니다.", services.Folders.GetDefaultSystemFolder(FlowNoteLocalDatabase.DocumentsFolderName).Id);
        RefreshNotificationButton();
    }

    protected override void OnClosed(EventArgs e)
    {
        Loaded -= MainWindow_Loaded;
        serverHttpClient?.Dispose();
        base.OnClosed(e);
    }

    private async void MainWindow_Loaded(object sender, RoutedEventArgs e)
    {
        if (serverDocumentClient is null)
        {
            return;
        }

        var result = await services.ServerSync.RetryPendingAsync(serverDocumentClient, currentUser.UserId);
        if (result.Attempted > 0)
        {
            workspace.StatusText = $"{workspace.StatusText}  {result.Message}";
        }
    }

    private void NewFolderButton_Click(object sender, RoutedEventArgs e)
    {
        var parent = selectedFolder is null
            ? services.Folders.GetRootFolder()
            : services.Folders.GetFolder(selectedFolder.Id);
        var folder = services.Folders.CreateFolder($"새 폴더 {DateTime.Now:HHmmss}", parent.Id, actorName: GetCurrentActorName());
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
        var plan = services.DocumentPlacement.PrepareDocumentRegistration(folder.Id, fileName, DateTime.Now, actorName);

        services.Documents.RegisterDocument(
            plan.Folder.Id,
            plan.Title,
            fileName,
            "Text",
            actorName,
            tags: BuildRegistrationTags(plan.Folder, fileName, "Text"));

        RefreshWorkspace($"문서를 등록했습니다. 위치: {plan.Folder.Path}", plan.Folder.Id);
    }

    private void ApplyDocumentStatusButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureDocumentRegistrationAllowed())
        {
            return;
        }

        if (DocumentGrid.SelectedItem is not ExplorerDocument document)
        {
            workspace.StatusText = "Select a document before changing status.";
            return;
        }

        var selectedStatus = (DocumentStatusComboBox.SelectedItem as ComboBoxItem)?.Content?.ToString();
        if (string.IsNullOrWhiteSpace(selectedStatus))
        {
            workspace.StatusText = "Select a document status.";
            return;
        }

        try
        {
            services.Documents.UpdateDocumentStatus(document.DocumentId, selectedStatus, GetCurrentActorName());
            RefreshDocuments(selectedFolder?.Id, $"Document status changed: {selectedStatus}");
        }
        catch (InvalidOperationException exception)
        {
            workspace.StatusText = exception.Message;
        }
    }

    private void PublishDocumentButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureDocumentRegistrationAllowed())
        {
            return;
        }

        if (DocumentGrid.SelectedItem is not ExplorerDocument document)
        {
            workspace.StatusText = "Select a document before publishing.";
            return;
        }

        try
        {
            services.Documents.PublishVersion(document.DocumentId, document.VersionNo, GetCurrentActorName());
            RefreshDocuments(selectedFolder?.Id, $"Published document version: {document.FileName} v{document.VersionNo}");
        }
        catch (InvalidOperationException exception)
        {
            workspace.StatusText = exception.Message;
        }
    }

    private void NotificationButton_Click(object sender, RoutedEventArgs e)
    {
        var window = new NotificationWindow(services.Notifications, GetCurrentActorName())
        {
            Owner = this
        };
        window.ShowDialog();
        RefreshNotificationButton();
    }

    private void HistoryButton_Click(object sender, RoutedEventArgs e)
    {
        var window = new HistoryWindow(services.History)
        {
            Owner = this
        };
        window.ShowDialog();
    }

    private void WorkSequenceAdminButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureDocumentRegistrationAllowed())
        {
            return;
        }

        var window = new WorkSequenceAdminWindow(services.WorkSequences, GetCurrentActorName())
        {
            Owner = this
        };
        window.ShowDialog();
    }

    private void WorkSequenceTvButton_Click(object sender, RoutedEventArgs e)
    {
        var board = services.WorkSequences.ListBoards().FirstOrDefault();
        if (board is null)
        {
            workspace.StatusText = "Create a work sequence board before opening TV view.";
            return;
        }

        var window = new WorkSequenceTvWindow(services.WorkSequences, board.BoardId)
        {
            Owner = this
        };
        window.Show();
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

    private void RefreshWorkspace(string status, long? selectedFolderId = null)
    {
        RefreshFolders();
        RefreshDocuments(selectedFolderId, status);
    }

    private void RefreshDocuments(long? folderId, string status)
    {
        workspace.Documents.Clear();
        foreach (var document in services.Documents.ListDocuments(folderId).Select(ToExplorerDocument))
        {
            workspace.Documents.Add(document);
        }

        UpdateDocumentListHeader(folderId, status);
    }

    private void RefreshFolders()
    {
        workspace.Folders.Clear();
        foreach (var folder in BuildFolderTree())
        {
            workspace.Folders.Add(folder);
        }
    }

    private IReadOnlyList<ExplorerFolder> BuildFolderTree()
    {
        var folders = services.Folders.ListFolders();
        return folders
            .Where(folder => folder.ParentId is null)
            .Select(folder => ToExplorerFolder(folder, folders))
            .ToList();
    }

    private static ExplorerFolder ToExplorerFolder(DocumentFolder folder, IReadOnlyList<DocumentFolder> folders)
    {
        var children = folders
            .Where(child => child.ParentId == folder.Id)
            .Select(child => ToExplorerFolder(child, folders))
            .ToList();

        return new ExplorerFolder(folder.Id, folder.Name, folder.Path, folder.IsSystem, children, folder.ParentId is null);
    }

    private static ExplorerDocument ToExplorerDocument(DocumentRecord record)
    {
        return new ExplorerDocument(
            record.DocumentId,
            record.Title,
            record.FileName,
            record.DocumentType,
            record.Status,
            record.CreatedBy,
            record.UpdatedAt,
            $"v{record.VersionNo}",
            record.LocalPath,
            record.LatestComment,
            record.TagText,
            record.VersionNo,
            record.PublishedVersionNo);
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
        e.Effects = canRegisterDocuments && HasFileDrop(e) ? DragDropEffects.Copy : DragDropEffects.None;
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

    private async Task RegisterUploadedFilesAsync(IEnumerable<string> files, DocumentFolder selectedTargetFolder, string sourceLabel)
    {
        if (!EnsureDocumentRegistrationAllowed())
        {
            return;
        }

        var addedCount = 0;
        var serverRegisteredCount = 0;
        var serverSyncFailures = new List<string>();
        long? lastTargetFolderId = null;
        var actorName = currentUser.DisplayName ?? currentUser.LoginId ?? "admin";

        foreach (var file in files.Where(File.Exists))
        {
            var fileInfo = new FileInfo(file);
            var createdAt = DateTime.Now;
            var plan = services.DocumentPlacement.PrepareDocumentRegistration(selectedTargetFolder.Id, fileInfo.Name, createdAt, actorName);
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
        var uploadRoot = Path.Combine(dataDirectory, "Files", "Uploads", createdAt.ToString("yyyy-MM-dd"));
        Directory.CreateDirectory(uploadRoot);

        var targetPath = GetUniqueTargetPath(uploadRoot, sourceFile.Name);
        File.Copy(sourceFile.FullName, targetPath);
        return Path.GetRelativePath(dataDirectory, targetPath);
    }

    private static string GetAppContentPath(string storedRelativePath)
    {
        return FlowNoteLocalDatabase.ResolveLocalContentPath(storedRelativePath);
    }

    private static string SummarizeServerSyncFailure(Exception exception)
    {
        var message = exception switch
        {
            TaskCanceledException => "서버 응답 시간 초과",
            HttpRequestException => "서버 연결 실패",
            _ => exception.Message
        };

        if (string.IsNullOrWhiteSpace(message))
        {
            message = exception.GetType().Name;
        }

        message = message.Replace(Environment.NewLine, " ");
        const int maxLength = 120;
        return message.Length <= maxLength ? message : $"{message[..maxLength]}...";
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
            _ => string.IsNullOrWhiteSpace(extension) ? "File" : extension.TrimStart('.').ToUpperInvariant()
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

        if (tags.Any(existing => string.Equals(existing, tag.Trim(), StringComparison.OrdinalIgnoreCase)))
        {
            return;
        }

        tags.Add(tag.Trim());
    }

    private void UpdateDocumentListHeader(long? folderId, string status)
    {
        var folder = folderId is null ? null : services.Folders.GetFolder(folderId.Value);
        DocumentListTitleTextBlock.Text = folder is null ? "문서 목록" : $"{folder.Name} 파일 목록";
        DocumentListHintTextBlock.Text = canRegisterDocuments
            ? $"표시 {workspace.Documents.Count}개"
            : $"표시 {workspace.Documents.Count}개 · 문서 등록 권한 없음";
        workspace.StatusText = canRegisterDocuments
            ? $"{status}  DB: {services.Database.DatabasePath}"
            : $"{status}  문서 등록은 관리자/반장/조장 이상만 가능합니다.  DB: {services.Database.DatabasePath}";
    }

    private void ApplyRolePermissions()
    {
        const string noDocumentWritePermission = "문서 등록은 관리자/반장/조장 이상만 가능합니다. 조원은 현장 코멘트 등록을 사용합니다.";
        RegisterDocumentButton.IsEnabled = canRegisterDocuments;
        UploadFileButton.IsEnabled = canRegisterDocuments;
        WorkSequenceAdminButton.IsEnabled = canRegisterDocuments;
        ApplyDocumentStatusButton.IsEnabled = canRegisterDocuments;
        PublishDocumentButton.IsEnabled = canRegisterDocuments;
        DocumentStatusComboBox.IsEnabled = canRegisterDocuments;
        FileListDropZone.AllowDrop = canRegisterDocuments;

        if (!canRegisterDocuments)
        {
            RegisterDocumentButton.ToolTip = noDocumentWritePermission;
            UploadFileButton.ToolTip = noDocumentWritePermission;
            WorkSequenceAdminButton.ToolTip = noDocumentWritePermission;
            ApplyDocumentStatusButton.ToolTip = noDocumentWritePermission;
            PublishDocumentButton.ToolTip = noDocumentWritePermission;
            DocumentStatusComboBox.ToolTip = noDocumentWritePermission;
            FileListDropZone.ToolTip = noDocumentWritePermission;
        }
    }

    private bool EnsureDocumentRegistrationAllowed()
    {
        if (canRegisterDocuments)
        {
            return true;
        }

        workspace.StatusText = "문서 등록 권한이 없습니다. 현장 코멘트 등록만 사용할 수 있습니다.";
        return false;
    }

    private static bool HasFileDrop(DragEventArgs e)
    {
        return e.Data.GetDataPresent(DataFormats.FileDrop);
    }

    private void DocumentGrid_MouseDoubleClick(object sender, System.Windows.Input.MouseButtonEventArgs e)
    {
        if (sender is not DataGrid { SelectedItem: ExplorerDocument document })
        {
            return;
        }

        var viewWindow = string.IsNullOrWhiteSpace(document.DocumentId)
            ? new DocumentViewWindow(document)
            : new DocumentViewWindow(
                services.FieldNotes,
                serverDocumentClient,
                services.ServerSync,
                services.DocumentViewLogs,
                document,
                currentUser.DisplayName ?? currentUser.LoginId ?? "admin");
        viewWindow.Owner = this;

        viewWindow.ShowDialog();
        if (viewWindow.CommentSaved && selectedFolder is not null)
        {
            RefreshDocuments(selectedFolder.Id, $"코멘트를 저장했습니다. 위치: {selectedFolder.Path}");
            RefreshNotificationButton();
        }
    }

    private void FolderTree_SelectedItemChanged(object sender, RoutedPropertyChangedEventArgs<object> e)
    {
        selectedFolder = e.NewValue as ExplorerFolder;
        if (selectedFolder is null)
        {
            return;
        }

        RefreshDocuments(selectedFolder.Id, $"선택한 폴더: {selectedFolder.Path}");
    }

    private void FolderTree_PreviewMouseDoubleClick(object sender, MouseButtonEventArgs e)
    {
        if (FindVisualParent<TreeViewItem>(e.OriginalSource as DependencyObject) is not { } item)
        {
            return;
        }

        if (item.DataContext is ExplorerFolder folder)
        {
            selectedFolder = folder;
            item.IsExpanded = !item.IsExpanded;
            RefreshDocuments(folder.Id, $"열어본 폴더: {folder.Path}");
            e.Handled = true;
        }
    }

    private DocumentFolder GetSelectedFolderOrDefault()
    {
        if (selectedFolder is not null && selectedFolder.Path != "/")
        {
            return services.Folders.GetFolder(selectedFolder.Id);
        }

        return services.Folders.GetDefaultSystemFolder(FlowNoteLocalDatabase.DocumentsFolderName);
    }

    private static (FlowNoteServerDocumentClient? Client, HttpClient? HttpClient) CreateServerDocumentClient(LoginResult currentUser)
    {
        var httpClient = FlowNoteServerApiEnvironment.CreateHttpClientFromEnvironment();
        if (httpClient is null || string.IsNullOrWhiteSpace(currentUser.AccessToken))
        {
            httpClient?.Dispose();
            return (null, null);
        }

        httpClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", currentUser.AccessToken);
        return (new FlowNoteServerDocumentClient(httpClient), httpClient);
    }

    private string GetCurrentActorName()
    {
        return currentUser.DisplayName ?? currentUser.LoginId ?? "admin";
    }

    private void RefreshNotificationButton()
    {
        var unreadCount = services.Notifications.CountUnread(GetCurrentActorName());
        NotificationButton.Content = unreadCount == 0 ? "알림함" : $"알림함 ({unreadCount})";
    }

    private static T? FindVisualParent<T>(DependencyObject? child)
        where T : DependencyObject
    {
        while (child is not null)
        {
            if (child is T parent)
            {
                return parent;
            }

            child = VisualTreeHelper.GetParent(child);
        }

        return null;
    }
}
