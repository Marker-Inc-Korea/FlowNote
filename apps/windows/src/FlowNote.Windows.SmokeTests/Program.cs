using FlowNote.Windows.Core.Storage;
using Microsoft.Data.Sqlite;

var testDirectory = Path.Combine(Path.GetTempPath(), "flownote-windows-smoke-tests");
Directory.CreateDirectory(testDirectory);

var databasePath = Path.Combine(testDirectory, $"flownote-{Guid.NewGuid():N}.sqlite");

try
{
    var services = new FlowNoteLocalServices(databasePath);

    var login = services.Auth.Login("admin", "1234");
    Require(login.Success, "admin / 1234 login should succeed");

    var wrongLogin = services.Auth.Login("admin", "wrong");
    Require(!wrongLogin.Success, "wrong password should fail");

    var root = services.Folders.GetRootFolder();
    Require(root.IsSystem, "root folder should be a system folder");

    var defaultFolderNames = FlowNoteLocalDatabase.DefaultSystemFolderNames;
    var defaultFolders = services.Folders.ListFolders()
        .Where(item => item.ParentId == root.Id && defaultFolderNames.Contains(item.Name))
        .ToList();
    Require(defaultFolders.Count == defaultFolderNames.Count, "all default system folders should exist below root");
    foreach (var defaultFolder in defaultFolders)
    {
        Require(defaultFolder.IsSystem, $"{defaultFolder.Name} should be a system folder");
        Require(!services.Folders.DeleteFolder(defaultFolder.Id), $"{defaultFolder.Name} should not be deletable");
    }

    var folder = services.Folders.CreateFolder("Smoke Folder", root.Id);
    var folders = services.Folders.ListFolders();
    Require(folders.Any(item => item.Id == folder.Id), "created folder should appear in folder list");

    var document = services.Documents.RegisterDocument(
        folder.Id,
        "Smoke Document",
        "smoke-document.txt",
        "Text",
        login.DisplayName ?? "Administrator");
    Require(document.Id > 0, "registered document should receive an id");

    var documents = services.Documents.ListDocuments(folder.Id);
    Require(documents.Any(item => item.DocumentId == document.DocumentId), "registered document should appear in folder document list");

    var deleted = services.Folders.DeleteFolder(folder.Id);
    Require(!deleted, "folder containing a document should not be deleted");

    Console.WriteLine("FlowNote Windows smoke tests passed.");
}
finally
{
    SqliteConnection.ClearAllPools();

    if (File.Exists(databasePath))
    {
        File.Delete(databasePath);
    }
}

static void Require(bool condition, string message)
{
    if (!condition)
    {
        throw new InvalidOperationException(message);
    }
}
