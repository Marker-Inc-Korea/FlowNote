using System.IO;
using System.Windows;
using System.Windows.Media;
using System.Windows.Controls;
using System.Windows.Input;
using FlowNote.Windows.Core.Auth;
using FlowNote.Windows.Core.Documents;
using FlowNote.Windows.Core.Explorer;
using FlowNote.Windows.Core.Folders;
using FlowNote.Windows.Core.Storage;

namespace FlowNote.Windows.App;

public partial class MainWindow : Window
{
    private readonly FlowNoteLocalServices services;
    private readonly LoginResult currentUser;
    private readonly ExplorerWorkspace workspace = new();
    private ExplorerFolder? selectedFolder;

    public MainWindow(FlowNoteLocalServices services, LoginResult currentUser)
    {
        InitializeComponent();
        this.services = services;
        this.currentUser = currentUser;
        SignedInUserTextBlock.Text = $"{currentUser.DisplayName} ({currentUser.Role})";
        DataContext = workspace;
        RefreshWorkspace("로컬 작업 공간을 열었습니다.", services.Folders.GetDefaultSystemFolder(FlowNoteLocalDatabase.DocumentsFolderName).Id);
    }

    private void NewFolderButton_Click(object sender, RoutedEventArgs e)
    {
        var parent = selectedFolder is null
            ? services.Folders.GetRootFolder()
            : services.Folders.GetFolder(selectedFolder.Id);
        var folder = services.Folders.CreateFolder($"새 폴더 {DateTime.Now:HHmmss}", parent.Id);
        RefreshWorkspace("폴더를 생성했습니다.", folder.Id);
    }

    private void RegisterDocumentButton_Click(object sender, RoutedEventArgs e)
    {
        var folder = GetSelectedFolderOrDefault();
        var fileName = $"sample-{DateTime.Now:HHmmss}.txt";
        var plan = services.DocumentPlacement.PrepareDocumentRegistration(folder.Id, fileName, DateTime.Now);

        services.Documents.RegisterDocument(
            plan.Folder.Id,
            plan.Title,
            fileName,
            "Text",
            currentUser.DisplayName ?? currentUser.LoginId ?? "admin");

        RefreshWorkspace($"문서를 등록했습니다. 위치: {plan.Folder.Path}", plan.Folder.Id);
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

        var folder = folderId is null ? null : services.Folders.GetFolder(folderId.Value);
        DocumentListTitleTextBlock.Text = folder is null ? "문서 목록" : $"{folder.Name} 파일 목록";
        DocumentListHintTextBlock.Text = $"표시 {workspace.Documents.Count}개";
        workspace.StatusText = $"{status}  DB: {services.Database.DatabasePath}";
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
            record.LatestComment);
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
        foreach (var file in files.Where(File.Exists))
        {
            var fileInfo = new FileInfo(file);
            var plan = services.DocumentPlacement.PrepareDocumentRegistration(folder.Id, fileInfo.Name, DateTime.Now);
            workspace.AddDroppedFileToList(new UploadCandidate(
                fileInfo.Name,
                fileInfo.FullName,
                fileInfo.Extension,
                fileInfo.Length,
                DateTime.Now),
                currentUser.DisplayName ?? currentUser.LoginId ?? "admin",
                plan.Title);
        }

        RefreshFolders();
        e.Handled = true;
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
                services.Documents,
                document,
                currentUser.DisplayName ?? currentUser.LoginId ?? "admin");
        viewWindow.Owner = this;

        viewWindow.ShowDialog();
        if (viewWindow.CommentSaved && selectedFolder is not null)
        {
            RefreshDocuments(selectedFolder.Id, $"코멘트를 저장했습니다. 위치: {selectedFolder.Path}");
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
