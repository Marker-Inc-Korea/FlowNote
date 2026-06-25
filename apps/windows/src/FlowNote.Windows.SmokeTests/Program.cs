using FlowNote.Windows.Core.Storage;
using FlowNote.Windows.Core.Explorer;
using FlowNote.Windows.Core.ServerApi;
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

    var documentsFolder = services.Folders.GetDefaultSystemFolder(FlowNoteLocalDatabase.DocumentsFolderName);
    var documentCategoryFolders = services.Folders.ListFolders()
        .Where(item => item.ParentId == documentsFolder.Id && FlowNoteLocalDatabase.DocumentCategoryFolderNames.Contains(item.Name))
        .ToList();
    Require(
        documentCategoryFolders.Count == FlowNoteLocalDatabase.DocumentCategoryFolderNames.Count,
        "document category folders should exist below the documents folder");
    foreach (var categoryFolder in documentCategoryFolders)
    {
        Require(categoryFolder.IsSystem, $"{categoryFolder.Name} should be a system folder");
        Require(!services.Folders.DeleteFolder(categoryFolder.Id), $"{categoryFolder.Name} should not be deletable");
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

    var fieldNote = services.FieldNotes.AddDocumentNote(
        document.DocumentId,
        "Smoke field note stored separately from document versions.",
        login.DisplayName ?? "Administrator");
    Require(!string.IsNullOrWhiteSpace(fieldNote.NoteId), "field note should receive an id");
    Require(fieldNote.DocumentVersionNo == 1, "field note should keep the current document version number");
    var fieldNotes = services.FieldNotes.ListDocumentNotes(document.DocumentId);
    Require(fieldNotes.Count == 1, "document should list the saved field note");
    Require(fieldNotes[0].RawContent == "Smoke field note stored separately from document versions.", "field note should preserve raw content");
    Require(
        services.Documents.ListVersions(document.DocumentId).Count == 1,
        "field note should not create a new document version");
    Require(
        services.Documents.ListDocuments(folder.Id).Any(item =>
            item.DocumentId == document.DocumentId &&
            item.LatestComment == "Smoke field note stored separately from document versions."),
        "field note should update the document latest comment summary");

    var commentedDocument = services.Documents.AddCommentVersion(
        document.DocumentId,
        "Smoke comment for version history.",
        login.DisplayName ?? "Administrator");
    Require(commentedDocument.VersionNo == 2, "comment should create the next document version");
    Require(commentedDocument.LatestComment == "Smoke comment for version history.", "latest comment should be stored on the document");

    var versions = services.Documents.ListVersions(document.DocumentId);
    Require(versions.Count == 2, "document should have original version and comment version");
    Require(versions[0].VersionNo == 2, "latest version should be first");
    Require(versions[0].Comment == "Smoke comment for version history.", "version should store the comment");

    var notificationDocument = services.Documents.RegisterDocument(
        folder.Id,
        "Notification Document",
        "notification-document.txt",
        "Text",
        "작성자1");
    services.Documents.AddCommentVersion(
        notificationDocument.DocumentId,
        "v2 comment should notify original author.",
        "작성자2");
    services.Documents.AddCommentVersion(
        notificationDocument.DocumentId,
        "v3 comment should notify previous version author.",
        "작성자3");
    var originalAuthorNotifications = services.Notifications.ListNotifications("작성자1");
    Require(originalAuthorNotifications.Count == 1, "v2 comment should notify the original document author once");
    Require(originalAuthorNotifications[0].ActorName == "작성자2", "v2 notification actor should be the v2 author");
    Require(originalAuthorNotifications[0].Message.Contains("v2", StringComparison.Ordinal), "v2 notification should mention version 2");

    var previousVersionAuthorNotifications = services.Notifications.ListNotifications("작성자2");
    Require(previousVersionAuthorNotifications.Count == 1, "v3 comment should notify the previous version author");
    Require(previousVersionAuthorNotifications[0].ActorName == "작성자3", "v3 notification actor should be the v3 author");
    Require(previousVersionAuthorNotifications[0].Message.Contains("v3", StringComparison.Ordinal), "v3 notification should mention version 3");
    Require(services.Notifications.CountUnread("작성자2") == 1, "previous version author should have one unread notification");
    services.Notifications.MarkAllAsRead("작성자2");
    Require(services.Notifications.CountUnread("작성자2") == 0, "mark all as read should clear unread notifications");

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

    var drawingPlan = services.DocumentPlacement.PrepareDocumentRegistration(
        documentsFolder.Id,
        "도면-프레스A-금형배치.pdf",
        ruleDate);
    Require(drawingPlan.Folder.Name == FlowNoteLocalDatabase.DrawingFolderName, "drawing files should be placed in the drawing folder");
    Require(drawingPlan.Folder.ParentId == documentsFolder.Id, "drawing folder should be below the documents folder");

    var safetyPlan = services.DocumentPlacement.PrepareDocumentRegistration(
        documentsFolder.Id,
        "문서-안전수칙-용접작업.txt",
        ruleDate);
    Require(safetyPlan.Folder.Name == FlowNoteLocalDatabase.SafetyFolderName, "safety files should be placed in the safety folder");
    Require(safetyPlan.Folder.ParentId == documentsFolder.Id, "safety folder should be below the documents folder");

    var sampleFile = Path.Combine(testDirectory, "sample-upload.txt");
    File.WriteAllText(sampleFile, "FlowNote upload smoke test.");
    var uploadedDocument = services.Documents.RegisterDocument(
        documentsFolder.Id,
        "sample-upload",
        "sample-upload.txt",
        "Text",
        login.DisplayName ?? "Administrator",
        sampleFile);
    Require(uploadedDocument.LocalPath == sampleFile, "uploaded document should store the local file path");
    Require(
        services.Documents.ListDocuments(documentsFolder.Id).Any(item => item.DocumentId == uploadedDocument.DocumentId && item.LocalPath == sampleFile),
        "uploaded document should be saved in the database document list");
    Require(
        services.Documents.ListVersions(uploadedDocument.DocumentId).Any(item => item.VersionNo == 1 && item.LocalPath == sampleFile),
        "uploaded document original version should store the local file path");

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

    var apiBaseUrl = Environment.GetEnvironmentVariable("FLOWNOTE_API_BASE_URL");
    if (!string.IsNullOrWhiteSpace(apiBaseUrl))
    {
        using var httpClient = new HttpClient
        {
            BaseAddress = new Uri(apiBaseUrl.EndsWith('/') ? apiBaseUrl : $"{apiBaseUrl}/"),
            Timeout = TimeSpan.FromSeconds(20)
        };
        var serverDocuments = new FlowNoteServerDocumentClient(httpClient);
        var serverDocument = await serverDocuments.RegisterDocumentAsync(
            sampleFile,
            "Windows smoke upload",
            "client_smoke_test",
            "Windows smoke test registered this file through FastAPI.",
            description: "Registered by FlowNote.Windows.SmokeTests.");
        Require(!string.IsNullOrWhiteSpace(serverDocument.DocumentId), "server document should receive an id");
        var latestServerVersion = serverDocument.LatestVersion;
        Require(latestServerVersion is not null, "server document should include its latest version");
        Require(latestServerVersion!.VersionNo == 1, "server document should receive version 1");
        Require(latestServerVersion.File.SizeBytes == new FileInfo(sampleFile).Length, "server file size should match the uploaded file");

        var serverList = await serverDocuments.ListDocumentsAsync();
        Require(
            serverList.Any(item => item.DocumentId == serverDocument.DocumentId),
            "server document list should include the uploaded smoke document");

        var serverVersions = await serverDocuments.ListVersionsAsync(serverDocument.DocumentId);
        Require(serverVersions.Count == 1, "server document should have one version after initial upload");
        Require(serverVersions[0].ChangeReason.Contains("FastAPI", StringComparison.Ordinal), "server version should preserve the change reason");

        var serverFieldNote = await serverDocuments.RegisterFieldNoteAsync(
            fieldNote,
            documentId: serverDocument.DocumentId,
            documentVersionId: latestServerVersion.VersionId);
        Require(!string.IsNullOrWhiteSpace(serverFieldNote.NoteId), "server field note should receive an id");
        Require(serverFieldNote.DocumentId == serverDocument.DocumentId, "server field note should reference the uploaded document");
        Require(
            serverFieldNote.DocumentVersionId == latestServerVersion.VersionId,
            "server field note should reference the uploaded document version");
        Require(
            serverFieldNote.RawContent == "Smoke field note stored separately from document versions.",
            "server field note should preserve raw content");
        Require(serverFieldNote.Status == "NEW", "server field note should start in NEW status");
    }

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
