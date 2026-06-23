using FlowNote.Windows.Core.Storage;
using FlowNote.Windows.Core.Explorer;
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

    var ruleDate = new DateTime(2026, 6, 23, 9, 10, 0);
    var handoverFolder = services.Folders.GetDefaultSystemFolder(FlowNoteLocalDatabase.HandoverFolderName);
    var handoverPlan = services.DocumentPlacement.PrepareDocumentRegistration(
        handoverFolder.Id,
        "shift-handover.txt",
        ruleDate);
    Require(handoverPlan.Folder.Name == "2026-06-23", "handover files should be placed in a date child folder");
    Require(handoverPlan.Folder.ParentId == handoverFolder.Id, "handover date folder should be below the handover folder");

    var photosFolder = services.Folders.GetDefaultSystemFolder(FlowNoteLocalDatabase.PhotosFolderName);
    var photosPlan = services.DocumentPlacement.PrepareDocumentRegistration(
        photosFolder.Id,
        "line-photo.jpg",
        ruleDate);
    Require(photosPlan.Folder.Name == "2026-06-23", "photo files should be placed in a date child folder");
    Require(photosPlan.Folder.ParentId == photosFolder.Id, "photo date folder should be below the photos folder");

    var workOrderFolder = services.Folders.GetDefaultSystemFolder(FlowNoteLocalDatabase.WorkOrderFolderName);
    var workOrderPlan = services.DocumentPlacement.PrepareDocumentRegistration(
        workOrderFolder.Id,
        "assembly-check-sheet.xlsx",
        ruleDate);
    Require(workOrderPlan.Folder.Id == workOrderFolder.Id, "work order files should remain in the work order folder");
    Require(workOrderPlan.Title == "assembly-check-sheet", "work order title should be generated from the file name");

    var sampleFile = Path.Combine(testDirectory, "sample-upload.txt");
    File.WriteAllText(sampleFile, "FlowNote upload smoke test.");
    var fileInfo = new FileInfo(sampleFile);
    var uploadCandidate = new UploadCandidate(
        fileInfo.Name,
        fileInfo.FullName,
        fileInfo.Extension,
        fileInfo.Length,
        DateTime.Now);
    Require(uploadCandidate.FileName == "sample-upload.txt", "upload candidate should capture the file name");
    Require(uploadCandidate.SizeBytes > 0, "upload candidate should capture file size");

    var workspace = new ExplorerWorkspace();
    workspace.AddDroppedFileToList(uploadCandidate, login.DisplayName ?? "Administrator");
    Require(workspace.Documents.Count == 1, "dropped file should be added to the file list");
    Require(workspace.Documents[0].UpdatedBy == login.DisplayName, "dropped file should capture the login display name");
    Require(workspace.Documents[0].LocalPath == sampleFile, "dropped file should keep the local path for preview");

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
