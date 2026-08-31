using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using FlowNote.Windows.Core.Documents;
using FlowNote.Windows.Core.Explorer;
using FlowNote.Windows.Core.Folders;
using FlowNote.Windows.Core.Storage;

namespace FlowNote.Windows.App;

public partial class MainWindow
{
    private IReadOnlyList<ExplorerDocument> currentFolderDocuments = [];
    private long? currentFolderId;
    private string currentListStatus = string.Empty;

    private void RefreshWorkspace(string status, long? selectedFolderId = null)
    {
        RefreshFolders();
        RefreshDocuments(selectedFolderId, status);
    }

    private void RefreshDocuments(long? folderId, string status)
    {
        currentFolderId = folderId;
        currentListStatus = status;
        currentFolderDocuments = services.Documents
            .ListDocuments(folderId)
            .Select(ToExplorerDocument)
            .ToList();
        ApplyDocumentFilters();
        RefreshSyncState();
    }

    private void ApplyDocumentFilters()
    {
        var searchText = DocumentSearchTextBox.Text.Trim();
        var selectedStatus = (DocumentFilterComboBox.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "ALL";
        var statusLabel = selectedStatus == "ALL" ? null : FormatDocumentStatus(selectedStatus);

        var filtered = currentFolderDocuments.Where(document =>
            (statusLabel is null || string.Equals(document.Status, statusLabel, StringComparison.Ordinal)) &&
            (string.IsNullOrWhiteSpace(searchText) ||
             ContainsSearchText(document.FileName, searchText) ||
             ContainsSearchText(document.Title, searchText) ||
             ContainsSearchText(document.TagText, searchText) ||
             ContainsSearchText(document.UpdatedBy, searchText) ||
             ContainsSearchText(document.LatestComment, searchText)));

        workspace.Documents.Clear();
        foreach (var document in filtered)
        {
            workspace.Documents.Add(document);
        }

        UpdateDocumentListHeader(currentFolderId, currentListStatus);
    }

    private static bool ContainsSearchText(string? value, string searchText) =>
        !string.IsNullOrWhiteSpace(value) &&
        value.Contains(searchText, StringComparison.CurrentCultureIgnoreCase);

    private void DocumentSearchTextBox_TextChanged(object sender, TextChangedEventArgs e)
    {
        if (DataContext is ExplorerWorkspace)
        {
            ApplyDocumentFilters();
        }
    }

    private void DocumentFilterComboBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (DataContext is ExplorerWorkspace)
        {
            ApplyDocumentFilters();
        }
    }

    private void DocumentSearchTextBox_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key != Key.Enter)
        {
            return;
        }

        if (DocumentGrid.SelectedItem is null)
        {
            DocumentGrid.SelectedItem = workspace.Documents.FirstOrDefault();
        }

        OpenSelectedDocument();
        e.Handled = true;
    }

    private void OpenSelectedDocumentButton_Click(object sender, RoutedEventArgs e)
    {
        OpenSelectedDocument();
    }

    private void FocusDocumentSearch()
    {
        DocumentSearchTextBox.Focus();
        DocumentSearchTextBox.SelectAll();
        workspace.StatusText =
            "파일명·제목·태그·사용자·최근 코멘트를 입력하고 Enter를 누르면 첫 문서를 바로 엽니다. 검색어와 상태 필터는 폴더를 이동해도 유지됩니다.";
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

    private static ExplorerFolder ToExplorerFolder(
        DocumentFolder folder,
        IReadOnlyList<DocumentFolder> folders)
    {
        var children = folders
            .Where(child => child.ParentId == folder.Id)
            .Select(child => ToExplorerFolder(child, folders))
            .ToList();

        return new ExplorerFolder(
            folder.Id,
            folder.Name,
            folder.Path,
            folder.IsSystem,
            children,
            folder.ParentId is null);
    }

    private static ExplorerDocument ToExplorerDocument(DocumentRecord record)
    {
        return new ExplorerDocument(
            record.DocumentId,
            record.Title,
            record.FileName,
            record.DocumentType,
            FormatDocumentStatus(record.Status),
            record.CreatedBy,
            record.UpdatedAt,
            $"v{record.VersionNo}",
            record.LocalPath,
            record.LatestComment,
            record.TagText,
            record.VersionNo,
            record.PublishedVersionNo);
    }

    private void UpdateDocumentListHeader(long? folderId, string status)
    {
        var folder = folderId is null ? null : services.Folders.GetFolder(folderId.Value);
        DocumentListTitleTextBlock.Text = folder is null ? "파일 · 문서 목록" : $"{folder.Name} · 파일 목록";

        var filtered = workspace.Documents.Count != currentFolderDocuments.Count;
        var countText = filtered
            ? $"전체 {currentFolderDocuments.Count}개 중 {workspace.Documents.Count}개 표시"
            : $"표시 {workspace.Documents.Count}개";
        DocumentListHintTextBlock.Text = canRegisterDocuments
            ? countText
            : $"{countText} · 문서 등록 권한 없음";

        workspace.StatusText = canRegisterDocuments
            ? $"{status}  DB: {services.Database.DatabasePath}"
            : $"{status}  문서 등록은 관리자/반장/조장 이상만 가능합니다. 권한이 필요하면 현장 관리자에게 로그인 ID와 업무명을 전달하세요.  DB: {services.Database.DatabasePath}";
    }

    private void FolderTree_SelectedItemChanged(
        object sender,
        RoutedPropertyChangedEventArgs<object> e)
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
