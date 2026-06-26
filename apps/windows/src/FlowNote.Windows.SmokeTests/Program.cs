using FlowNote.Windows.Core.Storage;
using FlowNote.Windows.Core.Explorer;
using FlowNote.Windows.Core.ServerApi;
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
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

    foreach (var seededUser in FlowNoteLocalDatabase.DefaultUserSeeds)
    {
        var seededLogin = services.Auth.Login(seededUser.LoginId, "1234");
        Require(seededLogin.Success, $"{seededUser.LoginId} / 1234 login should succeed");
        Require(seededLogin.UserId == seededUser.UserId, $"{seededUser.LoginId} should keep the seeded user id");
        Require(seededLogin.DisplayName == seededUser.DisplayName, $"{seededUser.LoginId} should keep the seeded display name");
        Require(seededLogin.Role == seededUser.Role, $"{seededUser.LoginId} should keep the seeded role");
    }

    using (var seedConnection = services.Database.OpenConnection())
    {
        var workGroups = FlowNoteLocalDatabase.DefaultGroupSeeds
            .Where(group => group.GroupType == "work_team")
            .ToList();
        Require(workGroups.Count == 3, "three foreman-centered work groups should be defined");
        Require(ScalarLong(seedConnection, "SELECT COUNT(*) FROM user_groups WHERE group_type = 'work_team';") == 3,
            "three foreman-centered work groups should be seeded");

        foreach (var group in workGroups)
        {
            var memberCount = ScalarLong(
                seedConnection,
                "SELECT COUNT(*) FROM user_accounts WHERE group_id = $group_id;",
                ("$group_id", group.GroupId));
            Require(memberCount is >= 4 and <= 8, $"{group.GroupId} should contain 4 to 8 users");

            var foremanCount = ScalarLong(
                seedConnection,
                "SELECT COUNT(*) FROM user_accounts WHERE group_id = $group_id AND role = 'line-foreman';",
                ("$group_id", group.GroupId));
            Require(foremanCount == 1, $"{group.GroupId} should contain one foreman");

            var linkedCrewCount = ScalarLong(
                seedConnection,
                """
                SELECT COUNT(*)
                FROM user_accounts
                WHERE group_id = $group_id
                  AND user_id <> $leader_user_id
                  AND supervisor_user_id = $leader_user_id;
                """,
                ("$group_id", group.GroupId),
                ("$leader_user_id", group.LeaderUserId ?? string.Empty));
            Require(linkedCrewCount == memberCount - 1, $"{group.GroupId} crew should be linked to its foreman");
        }
    }

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

    var viewLogId = services.DocumentViewLogs.StartDocumentView(
        document.DocumentId,
        document.VersionNo,
        login.DisplayName ?? "Administrator");
    var openedViewLog = services.DocumentViewLogs.GetLog(viewLogId);
    Require(openedViewLog is not null, "document view log should be created when viewing starts");
    Require(openedViewLog!.DocumentId == document.DocumentId, "document view log should keep the document id");
    Require(openedViewLog.VersionNo == document.VersionNo, "document view log should keep the document version number");
    Require(openedViewLog.UserName == (login.DisplayName ?? "Administrator"), "document view log should keep the user name");
    Require(openedViewLog.ClosedAt is null, "document view log should start without a closed time");

    services.DocumentViewLogs.CloseDocumentView(viewLogId, "window_closed");
    var closedViewLog = services.DocumentViewLogs.GetLog(viewLogId);
    Require(closedViewLog is not null, "document view log should remain readable after close");
    Require(closedViewLog!.ClosedAt is not null, "document view log should record the closed time");
    Require(closedViewLog.CloseReason == "window_closed", "document view log should record the close reason");
    using (var viewLogConnection = services.Database.OpenConnection())
    {
        Require(
            ScalarLong(
                viewLogConnection,
                "SELECT COUNT(*) FROM document_view_logs WHERE document_id = $document_id;",
                ("$document_id", document.DocumentId)) == 1,
            "document view should create one log row for one open/close cycle");
    }

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

    var foremanLogin = services.Auth.Login("foreman-a", "1234");
    var leadLogin = services.Auth.Login("lead-a1", "1234");
    var memberLogin = services.Auth.Login("member-a1", "1234");
    Require(foremanLogin.Success, "foreman-a / 1234 login should succeed for document registration");
    Require(leadLogin.Success, "lead-a1 / 1234 login should succeed for field note registration");
    Require(memberLogin.Success, "member-a1 / 1234 login should succeed for field note registration");

    var koreanPdfPath = Path.Combine(testDirectory, "flownote-korean-functional-test.pdf");
    CreateKoreanPdfOnStaThread(koreanPdfPath);
    Require(new FileInfo(koreanPdfPath).Length > 0, "Korean PDF test file should exist");

    var koreanPdfDocument = services.Documents.RegisterDocument(
        documentsFolder.Id,
        "한글 PDF 작업표준서 테스트",
        "flownote-korean-functional-test.pdf",
        "PDF",
        foremanLogin.DisplayName ?? "반장 A",
        koreanPdfPath);
    Require(koreanPdfDocument.DocumentType == "PDF", "Korean PDF document should be registered as PDF");
    Require(koreanPdfDocument.CreatedBy == "반장 A", "Korean PDF document should be created by foreman-a");
    Require(koreanPdfDocument.LocalPath == koreanPdfPath, "Korean PDF document should keep the local PDF path");

    var leadFieldNote = services.FieldNotes.AddDocumentNote(
        koreanPdfDocument.DocumentId,
        "조장 A-1 확인: PDF 한글 표시 정상, 혼합 공정 온도 기준 확인 완료.",
        leadLogin.DisplayName ?? "조장 A-1",
        noteType: "experience",
        inputMode: "template_with_text",
        signalLevel: "green",
        reportedBy: leadLogin.DisplayName,
        operatorName: "반장 A 작업조",
        deviceId: "device-line-a-01",
        locationCode: "line-a");
    Require(leadFieldNote.DocumentVersionNo == 1, "lead field note should point to Korean PDF version 1");
    Require(leadFieldNote.RawContent.Contains("PDF 한글 표시 정상", StringComparison.Ordinal),
        "lead field note should preserve Korean content");

    var memberFieldNote = services.FieldNotes.AddDocumentNote(
        koreanPdfDocument.DocumentId,
        "조원 A-1 확인: 설비 점검 항목을 작업 전에 읽을 수 있었음.",
        memberLogin.DisplayName ?? "조원 A-1",
        noteType: "work_evaluation",
        inputMode: "free_text",
        signalLevel: "green",
        reportedBy: memberLogin.DisplayName,
        operatorName: "반장 A 작업조",
        deviceId: "device-line-a-02",
        locationCode: "line-a");
    Require(memberFieldNote.DocumentVersionNo == 1, "member field note should point to Korean PDF version 1");

    var koreanPdfNotes = services.FieldNotes.ListDocumentNotes(koreanPdfDocument.DocumentId);
    Require(koreanPdfNotes.Count == 2, "Korean PDF document should list both field notes");
    Require(koreanPdfNotes.Any(note => note.AuthorName == "조장 A-1"), "Korean PDF notes should include lead comment");
    Require(koreanPdfNotes.Any(note => note.AuthorName == "조원 A-1"), "Korean PDF notes should include member comment");
    Require(
        services.Documents.ListVersions(koreanPdfDocument.DocumentId).Count == 1,
        "Korean PDF field notes should not create document versions");
    Require(
        services.Documents.ListDocuments(documentsFolder.Id).Any(item =>
            item.DocumentId == koreanPdfDocument.DocumentId &&
            item.LatestComment == "조원 A-1 확인: 설비 점검 항목을 작업 전에 읽을 수 있었음."),
        "Korean PDF document latest comment should reflect the newest field note");
    Require(
        services.Notifications.ListNotifications("반장 A").Count >= 2,
        "Korean PDF field notes should notify the foreman document creator");

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
    Console.WriteLine($"Smoke test SQLite DB kept at: {databasePath}");
    Console.WriteLine($"Smoke test Korean PDF kept at: {koreanPdfPath}");
}
finally
{
    SqliteConnection.ClearAllPools();
}

static void Require(bool condition, string message)
{
    if (!condition)
    {
        throw new InvalidOperationException(message);
    }
}

static long ScalarLong(SqliteConnection connection, string sql, params (string Name, object Value)[] parameters)
{
    using var command = connection.CreateCommand();
    command.CommandText = sql;
    foreach (var parameter in parameters)
    {
        command.Parameters.AddWithValue(parameter.Name, parameter.Value);
    }

    return Convert.ToInt64(command.ExecuteScalar());
}

static void CreateKoreanPdfOnStaThread(string pdfPath)
{
    Exception? error = null;
    var thread = new Thread(() =>
    {
        try
        {
            CreateKoreanPdf(pdfPath);
        }
        catch (Exception exception)
        {
            error = exception;
        }
    });

    thread.SetApartmentState(ApartmentState.STA);
    thread.Start();
    thread.Join();

    if (error is not null)
    {
        throw error;
    }
}

static void CreateKoreanPdf(string pdfPath)
{
    const int width = 1240;
    const int height = 1754;
    var visual = new DrawingVisual();
    using (var context = visual.RenderOpen())
    {
        context.DrawRectangle(Brushes.White, null, new Rect(0, 0, width, height));
        DrawText(context, "FlowNote 한글 PDF 기능 테스트", 72, 84, 42);
        DrawText(context, "반장 A가 등록한 작업 표준서 PDF입니다.", 72, 190, 28);
        DrawText(context, "조장 A-1과 조원 A-1의 현장 코멘트를 남기는 흐름을 검증합니다.", 72, 248, 28);
        DrawText(context, "혼합 공정 온도 확인, 설비 점검, 이상 발생 시 즉시 공유합니다.", 72, 306, 28);
        DrawText(context, "이 문장은 한글 깨짐 여부를 확인하기 위한 실제 표시 문장입니다.", 72, 364, 28);
    }

    var bitmap = new RenderTargetBitmap(width, height, 96, 96, PixelFormats.Pbgra32);
    bitmap.Render(visual);

    var pixels = new byte[width * height * 4];
    bitmap.CopyPixels(pixels, width * 4, 0);
    var rgb = new byte[width * height * 3];
    for (var source = 0; source < pixels.Length; source += 4)
    {
        var target = source / 4 * 3;
        rgb[target] = pixels[source + 2];
        rgb[target + 1] = pixels[source + 1];
        rgb[target + 2] = pixels[source];
    }

    var compressedRgb = Compress(rgb);
    var content = Encoding.ASCII.GetBytes("q\n595 0 0 842 0 0 cm\n/Im1 Do\nQ\n");
    var compressedContent = Compress(content);
    var objects = new List<byte[]>
    {
        PdfAscii("<< /Type /Catalog /Pages 2 0 R >>"),
        PdfAscii("<< /Type /Pages /Kids [3 0 R] /Count 1 >>"),
        PdfAscii("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /XObject << /Im1 4 0 R >> >> /Contents 5 0 R >>"),
        PdfStream(
            $"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {compressedRgb.Length} >>",
            compressedRgb),
        PdfStream(
            $"<< /Length {compressedContent.Length} /Filter /FlateDecode >>",
            compressedContent)
    };

    File.WriteAllBytes(pdfPath, BuildPdf(objects));
}

static void DrawText(DrawingContext context, string text, double x, double y, double size)
{
    var formatted = new FormattedText(
        text,
        CultureInfo.GetCultureInfo("ko-KR"),
        FlowDirection.LeftToRight,
        new Typeface(new FontFamily("Malgun Gothic"), FontStyles.Normal, FontWeights.Normal, FontStretches.Normal),
        size,
        Brushes.Black,
        1.0);
    context.DrawText(formatted, new Point(x, y));
}

static byte[] Compress(byte[] input)
{
    using var output = new MemoryStream();
    using (var deflate = new ZLibStream(output, CompressionLevel.SmallestSize, leaveOpen: true))
    {
        deflate.Write(input, 0, input.Length);
    }

    return output.ToArray();
}

static byte[] PdfAscii(string value)
{
    return Encoding.ASCII.GetBytes(value);
}

static byte[] PdfStream(string dictionary, byte[] stream)
{
    using var output = new MemoryStream();
    output.Write(Encoding.ASCII.GetBytes($"{dictionary}\nstream\n"));
    output.Write(stream, 0, stream.Length);
    output.Write(Encoding.ASCII.GetBytes("\nendstream"));
    return output.ToArray();
}

static byte[] BuildPdf(IReadOnlyList<byte[]> objects)
{
    using var output = new MemoryStream();
    output.Write(Encoding.ASCII.GetBytes("%PDF-1.4\n%\u00e2\u00e3\u00cf\u00d3\n"));
    var offsets = new List<long> { 0 };
    for (var index = 0; index < objects.Count; index++)
    {
        offsets.Add(output.Position);
        output.Write(Encoding.ASCII.GetBytes($"{index + 1} 0 obj\n"));
        output.Write(objects[index], 0, objects[index].Length);
        output.Write(Encoding.ASCII.GetBytes("\nendobj\n"));
    }

    var xref = output.Position;
    output.Write(Encoding.ASCII.GetBytes($"xref\n0 {objects.Count + 1}\n0000000000 65535 f \n"));
    foreach (var offset in offsets.Skip(1))
    {
        output.Write(Encoding.ASCII.GetBytes($"{offset:0000000000} 00000 n \n"));
    }

    output.Write(Encoding.ASCII.GetBytes(
        $"trailer\n<< /Size {objects.Count + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"));
    return output.ToArray();
}
