using System.Windows;
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

    public MainWindow(FlowNoteLocalServices services, LoginResult currentUser)
    {
        InitializeComponent();
        this.services = services;
        this.currentUser = currentUser;
        SignedInUserTextBlock.Text = $"Signed in: {currentUser.DisplayName} ({currentUser.Role})";
        DataContext = workspace;
        RefreshWorkspace("Signed in. Local SQLite workspace loaded.");
    }

    private void NewFolderButton_Click(object sender, RoutedEventArgs e)
    {
        var root = services.Folders.GetRootFolder();
        services.Folders.CreateFolder($"Folder {DateTime.Now:HHmmss}", root.Id);
        RefreshWorkspace("Folder created.");
    }

    private void RegisterDocumentButton_Click(object sender, RoutedEventArgs e)
    {
        var folder = services.Folders.ListFolders().FirstOrDefault(item => item.Name == "문서")
            ?? services.Folders.CreateFolder("문서", services.Folders.GetRootFolder().Id, true);

        services.Documents.RegisterDocument(
            folder.Id,
            $"Document {DateTime.Now:HHmmss}",
            $"sample-{DateTime.Now:HHmmss}.txt",
            "Text",
            currentUser.DisplayName ?? currentUser.LoginId ?? "admin");

        RefreshWorkspace("Document registered.");
    }

    private void RefreshWorkspace(string status)
    {
        workspace.Folders.Clear();
        foreach (var folder in BuildFolderTree())
        {
            workspace.Folders.Add(folder);
        }

        workspace.Documents.Clear();
        foreach (var document in services.Documents.ListDocuments().Select(ToExplorerDocument))
        {
            workspace.Documents.Add(document);
        }

        workspace.StatusText = $"{status} DB: {services.Database.DatabasePath}";
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

        return new ExplorerFolder(folder.Name, folder.Path, children);
    }

    private static ExplorerDocument ToExplorerDocument(DocumentRecord record)
    {
        return new ExplorerDocument(
            record.Title,
            record.FileName,
            record.DocumentType,
            record.Status,
            record.CreatedBy,
            record.CreatedAt,
            "v1");
    }
}
