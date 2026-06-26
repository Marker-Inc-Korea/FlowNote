using System.IO;
using System.Net.Http;
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
    private readonly ExplorerWorkspace workspace = new();
    private ExplorerFolder? selectedFolder;

    public MainWindow(FlowNoteLocalServices services, LoginResult currentUser)
    {
        InitializeComponent();
        this.services = services;
        this.currentUser = currentUser;
        (serverDocumentClient, serverHttpClient) = CreateServerDocumentClient();
        SignedInUserTextBlock.Text = $"{currentUser.DisplayName} ({currentUser.Role})";
        DataContext = workspace;
        RefreshWorkspace("로컬 작업 공간을 열었습니다.", services.Folders.GetDefaultSystemFolder(FlowNoteLocalDatabase.DocumentsFolderName).Id);
        RefreshNotificationButton();
    }

    protected override void OnClosed(EventArgs e)
    {
        serverHttpClient?.Dispose();
        base.OnClosed(e);
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

    private void UploadFileButton_Click(object sender, RoutedEventArgs e)
    {
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
        RegisterUploadedFiles(dialog.FileNames, folder, "파일 업로드");
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
            record.VersionNo);
    }

    private void FileListDropZone_DragEnter(object sender, DragEventArgs e)
    {
        if (HasFileDrop(e))
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
        e.Effects = HasFileDrop(e) ? DragDropEffects.Copy : DragDropEffects.None;
        e.Handled = true;
    }

    private void FileListDropZone_Drop(object sender, DragEventArgs e)
    {
        FileListPanel.Background = (Brush)FindResource("PanelBackgroundBrush");
        if (!HasFileDrop(e))
        {
            return;
        }

        var files = (string[])e.Data.GetData(DataFormats.FileDrop);
        var folder = GetSelectedFolderOrDefault();
        RegisterUploadedFiles(files, folder, "Drag & Drop 업로드");
        e.Handled = true;
    }

    private void RegisterUploadedFiles(IEnumerable<string> files, DocumentFolder selectedTargetFolder, string sourceLabel)
    {
        var addedCount = 0;
        long? lastTargetFolderId = null;
        var actorName = currentUser.DisplayName ?? currentUser.LoginId ?? "admin";

        foreach (var file in files.Where(File.Exists))
        {
            var fileInfo = new FileInfo(file);
            var createdAt = DateTime.Now;
            var plan = services.DocumentPlacement.PrepareDocumentRegistration(selectedTargetFolder.Id, fileInfo.Name, createdAt, actorName);
            var storedRelativePath = CopyFileToAppStorage(fileInfo, createdAt);
            services.Documents.RegisterDocument(
                plan.Folder.Id,
                plan.Title,
                fileInfo.Name,
                ResolveDocumentType(fileInfo.Extension),
                actorName,
                storedRelativePath,
                BuildRegistrationTags(plan.Folder, fileInfo.Name, ResolveDocumentType(fileInfo.Extension)));

            addedCount++;
            lastTargetFolderId = plan.Folder.Id;
        }

        RefreshWorkspace(
            $"{sourceLabel}: {addedCount}개 파일을 DB에 저장했습니다.",
            lastTargetFolderId ?? selectedTargetFolder.Id);
    }

    private string CopyFileToAppStorage(FileInfo sourceFile, DateTime createdAt)
    {
        var dataDirectory = Path.GetDirectoryName(services.Database.DatabasePath)!;
        var appContentRoot = Directory.GetParent(dataDirectory)?.FullName ?? AppContext.BaseDirectory;
        var uploadRoot = Path.Combine(dataDirectory, "Files", "Uploads", createdAt.ToString("yyyy-MM-dd"));
        Directory.CreateDirectory(uploadRoot);

        var targetPath = GetUniqueTargetPath(uploadRoot, sourceFile.Name);
        File.Copy(sourceFile.FullName, targetPath);
        return Path.GetRelativePath(appContentRoot, targetPath);
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
        DocumentListHintTextBlock.Text = $"표시 {workspace.Documents.Count}개";
        workspace.StatusText = $"{status}  DB: {services.Database.DatabasePath}";
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

    private static (FlowNoteServerDocumentClient? Client, HttpClient? HttpClient) CreateServerDocumentClient()
    {
        var apiBaseUrl = Environment.GetEnvironmentVariable("FLOWNOTE_API_BASE_URL");
        if (string.IsNullOrWhiteSpace(apiBaseUrl))
        {
            return (null, null);
        }

        var normalizedBaseUrl = apiBaseUrl.EndsWith('/') ? apiBaseUrl : $"{apiBaseUrl}/";
        if (!Uri.TryCreate(normalizedBaseUrl, UriKind.Absolute, out var baseAddress))
        {
            return (null, null);
        }

        var httpClient = new HttpClient
        {
            BaseAddress = baseAddress,
            Timeout = TimeSpan.FromSeconds(10)
        };

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
