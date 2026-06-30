using FlowNote.Windows.Core.Storage;
using FlowNote.Windows.Core.Auth;
using FlowNote.Windows.Core.Documents;
using FlowNote.Windows.Core.Explorer;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Sync;
using FlowNote.Windows.Core.WorkSequences;
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Threading;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using Microsoft.Data.Sqlite;

var testDirectory = Path.Combine(Path.GetTempPath(), "flownote-program-test-files");
Directory.CreateDirectory(testDirectory);

var databasePath = FlowNoteLocalDatabase.DefaultDatabasePath;
Directory.CreateDirectory(Path.GetDirectoryName(databasePath)!);
var runStartedAt = DateTime.Now;
var runStamp = runStartedAt.ToString("HHmmssfff");
var runId = runStartedAt.ToString("yyyyMMddHHmmssfff");

try
{
    var services = new FlowNoteLocalServices(databasePath);

    var login = services.Auth.Login("admin", "1234");
    Require(login.Success, "admin / 1234 login should succeed");
    var smokeActorName = login.DisplayName ?? "Administrator";

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
    var currentDocumentFolder = documentCategoryFolders.Single(item => item.Name == FlowNoteLocalDatabase.GeneralDocumentFolderName);

    var document = services.Documents.RegisterDocument(
        currentDocumentFolder.Id,
        "Program Test Document",
        "program-test-document.txt",
        "Text",
        smokeActorName,
        tags: ["line-a", "program-test", "work-standard"]);
    Require(document.Id > 0, "registered document should receive an id");
    Require(
        document.TagList.SequenceEqual(["line-a", "program-test", "work-standard"]),
        "registered document should keep its tags");

    var documents = services.Documents.ListDocuments(currentDocumentFolder.Id);
    Require(documents.Any(item => item.DocumentId == document.DocumentId), "registered document should appear in folder document list");
    Require(
        documents.Any(item => item.DocumentId == document.DocumentId && item.TagText == "line-a, program-test, work-standard"),
        "document list should include document tags");

    var viewLogId = services.DocumentViewLogs.StartDocumentView(
        document.DocumentId,
        document.VersionNo,
        smokeActorName);
    var openedViewLog = services.DocumentViewLogs.GetLog(viewLogId);
    Require(openedViewLog is not null, "document view log should be created when viewing starts");
    Require(openedViewLog!.DocumentId == document.DocumentId, "document view log should keep the document id");
    Require(openedViewLog.VersionNo == document.VersionNo, "document view log should keep the document version number");
    Require(openedViewLog.UserName == smokeActorName, "document view log should keep the user name");
    Require(openedViewLog.ClosedAt is null, "document view log should start without a closed time");

    services.DocumentViewLogs.CloseDocumentView(viewLogId, "window_closed");
    var closedViewLog = services.DocumentViewLogs.GetLog(viewLogId);
    Require(closedViewLog is not null, "document view log should remain readable after close");
    Require(closedViewLog!.ClosedAt is not null, "document view log should record the closed time");
    Require(closedViewLog.CloseReason == "window_closed", "document view log should record the close reason");

    var autoClosedViewLogId = services.DocumentViewLogs.StartDocumentView(
        document.DocumentId,
        document.VersionNo,
        smokeActorName);
    services.DocumentViewLogs.CloseDocumentView(autoClosedViewLogId, "auto_closed");
    var autoClosedViewLog = services.DocumentViewLogs.GetLog(autoClosedViewLogId);
    Require(autoClosedViewLog is not null, "auto-closed document view log should remain readable");
    Require(autoClosedViewLog!.ClosedAt is not null, "auto-closed document view log should record the closed time");
    Require(autoClosedViewLog.CloseReason == "auto_closed", "document view log should record the auto-close reason");
    var configuredAutoCloseDelay = WithEnvironmentVariable(
        DocumentViewerPolicy.AutoCloseSecondsEnvironmentVariable,
        "45",
        DocumentViewerPolicy.ResolveAutoCloseDelay);
    Require(configuredAutoCloseDelay == TimeSpan.FromSeconds(45), "document viewer auto-close delay should use the configured setting");
    var invalidAutoCloseDelay = WithEnvironmentVariable(
        DocumentViewerPolicy.AutoCloseSecondsEnvironmentVariable,
        "1",
        DocumentViewerPolicy.ResolveAutoCloseDelay);
    Require(invalidAutoCloseDelay == TimeSpan.FromSeconds(DocumentViewerPolicy.DefaultAutoCloseSeconds),
        "document viewer auto-close delay should fall back when the configured setting is below the minimum");
    using (var viewLogConnection = services.Database.OpenConnection())
    {
        Require(
            ScalarLong(
                viewLogConnection,
                "SELECT COUNT(*) FROM document_view_logs WHERE document_id = $document_id;",
                ("$document_id", document.DocumentId)) == 2,
            "document view should create one log row for each open/close cycle");
    }

    var fieldNote = services.FieldNotes.AddDocumentNote(
        document.DocumentId,
        "Program test field note stored separately from document versions.",
        smokeActorName);
    Require(!string.IsNullOrWhiteSpace(fieldNote.NoteId), "field note should receive an id");
    Require(fieldNote.DocumentVersionNo == 1, "field note should keep the current document version number");
    var fieldNotes = services.FieldNotes.ListDocumentNotes(document.DocumentId);
    Require(fieldNotes.Count == 1, "document should list the saved field note");
    Require(fieldNotes[0].RawContent == "Program test field note stored separately from document versions.", "field note should preserve raw content");
    Require(
        services.Documents.ListVersions(document.DocumentId).Count == 1,
        "field note should not create a new document version");
    Require(
        services.Documents.ListDocuments(currentDocumentFolder.Id).Any(item =>
            item.DocumentId == document.DocumentId &&
            item.LatestComment == "Program test field note stored separately from document versions."),
        "field note should update the document latest comment summary");

    var commentedDocument = services.Documents.AddCommentVersion(
        document.DocumentId,
        "Program test comment for version history.",
        smokeActorName);
    Require(commentedDocument.VersionNo == 2, "comment should create the next document version");
    Require(commentedDocument.LatestComment == "Program test comment for version history.", "latest comment should be stored on the document");

    var versions = services.Documents.ListVersions(document.DocumentId);
    Require(versions.Count == 2, "document should have original version and comment version");
    Require(versions[0].VersionNo == 2, "latest version should be first");
    Require(versions[0].Comment == "Program test comment for version history.", "version should store the comment");
    Require(versions[0].VersionStatus == "WORKING", "new local document version should start as WORKING");
    Require(!versions[0].IsPublished, "new local document version should not be published automatically");
    Require(commentedDocument.PublishedVersionNo is null, "new local document version should not set the published version");

    var publishedLocalDocument = services.Documents.PublishVersion(
        document.DocumentId,
        commentedDocument.VersionNo,
        smokeActorName);
    Require(publishedLocalDocument.Status == "PUBLISHED", "publishing a local version should set the document status to PUBLISHED");
    Require(
        publishedLocalDocument.PublishedVersionNo == commentedDocument.VersionNo,
        "publishing a local version should set the published version number");
    var publishedLocalVersions = services.Documents.ListVersions(document.DocumentId);
    Require(
        publishedLocalVersions.Any(item => item.VersionNo == commentedDocument.VersionNo && item.IsPublished && item.VersionStatus == "PUBLISHED"),
        "local version list should distinguish the published version");
    Require(
        services.Documents.ListDocuments(currentDocumentFolder.Id).Any(item =>
            item.DocumentId == document.DocumentId &&
            item.VersionNo == commentedDocument.VersionNo &&
            item.PublishedVersionNo == commentedDocument.VersionNo),
        "local document list should show both latest and published versions");

    var earlyHistory = services.History.ListHistory();
    Require(
        earlyHistory.Any(item =>
            item.EventType == "document.registered" &&
            item.ActorName == smokeActorName &&
            item.TargetId == document.DocumentId),
        "history should record who registered a document");
    Require(
        earlyHistory.Any(item =>
            item.EventType == "document.view_started" &&
            item.ActorName == smokeActorName &&
            item.TargetId == document.DocumentId),
        "history should record who opened a document");
    Require(
        earlyHistory.Any(item =>
            item.EventType == "document.view_closed" &&
            item.ActorName == smokeActorName),
        "history should record who closed a document view");
    Require(
        earlyHistory.Any(item =>
            item.EventType == "field_note.created" &&
            item.ActorName == smokeActorName &&
            item.TargetId == document.DocumentId),
        "history should record who added a field note");
    Require(
        earlyHistory.Any(item =>
            item.EventType == "document.version_added" &&
            item.ActorName == smokeActorName &&
            item.TargetId == document.DocumentId),
        "history should record who added a document version");
    Require(
        earlyHistory.Any(item =>
            item.EventType == "document.version_published" &&
            item.ActorName == smokeActorName &&
            item.TargetId == document.DocumentId),
        "history should record who published a document version");

    var notificationAuthor1 = $"작성자1-{runId}";
    var notificationAuthor2 = $"작성자2-{runId}";
    var notificationAuthor3 = $"작성자3-{runId}";
    var notificationDocument = services.Documents.RegisterDocument(
        currentDocumentFolder.Id,
        $"Notification Document {runStamp}",
        $"notification-document-{runStamp}.txt",
        "Text",
        notificationAuthor1);
    services.Documents.AddCommentVersion(
        notificationDocument.DocumentId,
        "v2 comment should notify original author.",
        notificationAuthor2);
    services.Documents.AddCommentVersion(
        notificationDocument.DocumentId,
        "v3 comment should notify previous version author.",
        notificationAuthor3);
    var originalAuthorNotifications = services.Notifications.ListNotifications(notificationAuthor1);
    Require(
        originalAuthorNotifications.Any(item =>
            item.DocumentId == notificationDocument.DocumentId &&
            item.ActorName == notificationAuthor2 &&
            item.Message.Contains("v2", StringComparison.Ordinal)),
        "v2 comment should create a notification for the original document author");

    var previousVersionAuthorNotifications = services.Notifications.ListNotifications(notificationAuthor2);
    Require(
        previousVersionAuthorNotifications.Any(item =>
            item.DocumentId == notificationDocument.DocumentId &&
            item.ActorName == notificationAuthor3 &&
            item.Message.Contains("v3", StringComparison.Ordinal)),
        "v3 comment should create a notification for the previous version author");
    using (var notificationConnection = services.Database.OpenConnection())
    {
        Require(
            ScalarLong(
                notificationConnection,
                """
                SELECT COUNT(*)
                FROM notifications
                WHERE document_id = $document_id
                  AND recipient_name = $recipient_name
                  AND actor_name = $actor_name;
                """,
                ("$document_id", notificationDocument.DocumentId),
                ("$recipient_name", notificationAuthor1),
                ("$actor_name", notificationAuthor2)) == 1,
            "v2 notify event should create one notification row for this document and recipient");
        Require(
            ScalarLong(
                notificationConnection,
                """
                SELECT COUNT(*)
                FROM notifications
                WHERE document_id = $document_id
                  AND recipient_name = $recipient_name
                  AND actor_name = $actor_name;
                """,
                ("$document_id", notificationDocument.DocumentId),
                ("$recipient_name", notificationAuthor2),
                ("$actor_name", notificationAuthor3)) == 1,
            "v3 notify event should create one notification row for this document and recipient");
    }
    services.Notifications.MarkAllAsRead(notificationAuthor2);
    Require(services.Notifications.CountUnread(notificationAuthor2) == 0, "mark all as read should clear unread notifications");

    var workSequenceBoard = services.WorkSequences.CreateBoard(
        $"Smoke work sequence {runStamp}",
        smokeActorName,
        description: "Local work sequence board smoke test.",
        lineCode: "line-a",
        boardDate: DateTime.Today);
    var firstWorkSequenceItem = services.WorkSequences.AddItem(
        workSequenceBoard.BoardId,
        $"Prepare material {runStamp}",
        smokeActorName,
        assignedTo: "line-a");
    var secondWorkSequenceItem = services.WorkSequences.AddItem(
        workSequenceBoard.BoardId,
        $"Start press run {runStamp}",
        smokeActorName,
        workOrderNo: $"WO-{runStamp}");
    Require(firstWorkSequenceItem.SortOrder == 1, "first work sequence item should start at order 1");
    Require(secondWorkSequenceItem.SortOrder == 2, "second work sequence item should start at order 2");
    services.WorkSequences.ReorderItems(
        workSequenceBoard.BoardId,
        [secondWorkSequenceItem.ItemId, firstWorkSequenceItem.ItemId],
        smokeActorName,
        "Smoke test changed priority.");
    var reorderedWorkSequenceItems = services.WorkSequences.GetItems(workSequenceBoard.BoardId);
    Require(
        reorderedWorkSequenceItems[0].ItemId == secondWorkSequenceItem.ItemId &&
        reorderedWorkSequenceItems[1].ItemId == firstWorkSequenceItem.ItemId,
        "work sequence reorder should persist item order");
    var startedWorkSequenceItem = services.WorkSequences.UpdateItemStatus(
        workSequenceBoard.BoardId,
        secondWorkSequenceItem.ItemId,
        "IN_PROGRESS",
        smokeActorName,
        "Smoke test started work.");
    Require(startedWorkSequenceItem.Status == "IN_PROGRESS", "work sequence status change should persist");
    var workSequenceHistory = services.WorkSequences.ListHistory(workSequenceBoard.BoardId);
    Require(
        workSequenceHistory.Any(item => item.ChangeType == "ITEM_REORDERED"),
        "work sequence history should record reorder changes");
    Require(
        workSequenceHistory.Any(item => item.ChangeType == "STATUS_CHANGED"),
        "work sequence history should record status changes");
    using (var workSequenceConnection = services.Database.OpenConnection())
    {
        Require(
            ScalarLong(
                workSequenceConnection,
                """
                SELECT COUNT(*)
                FROM work_sequence_notification_candidates
                WHERE board_id = $board_id
                  AND status = 'SENT';
                """,
                ("$board_id", workSequenceBoard.BoardId)) >= 2,
            "work sequence reorder and status changes should send notification candidates");
        Require(
            ScalarLong(
                workSequenceConnection,
                """
                SELECT COUNT(*)
                FROM notifications
                WHERE notification_type = 'work_sequence'
                  AND target_id = $item_id
                  AND message LIKE '%status changed%';
                """,
                ("$item_id", secondWorkSequenceItem.ItemId)) == 1,
            "one work sequence status event should create one notification for the target recipient");
    }
    string workSequenceNotificationRecipient;
    using (var workSequenceNotificationConnection = services.Database.OpenConnection())
    {
        workSequenceNotificationRecipient = ScalarString(
            workSequenceNotificationConnection,
            """
            SELECT recipient_name
            FROM notifications
            WHERE notification_type = 'work_sequence'
              AND target_id = $item_id
              AND message LIKE '%status changed%'
            ORDER BY created_at DESC, id DESC
            LIMIT 1;
            """,
            ("$item_id", secondWorkSequenceItem.ItemId))
            ?? throw new InvalidOperationException("work sequence status notification recipient should be recorded");
    }
    var workSequenceStatusNotification = services.Notifications.ListNotifications(workSequenceNotificationRecipient)
        .FirstOrDefault(item =>
            item.NotificationType == "work_sequence" &&
            item.TargetId == secondWorkSequenceItem.ItemId &&
            item.Message.Contains("status changed", StringComparison.Ordinal));
    Require(workSequenceStatusNotification is not null, "work sequence status notification should appear in the notification inbox");
    services.Notifications.MarkAsRead(workSequenceStatusNotification!.NotificationId, workSequenceNotificationRecipient);
    Require(
        services.Notifications.ListNotifications(workSequenceNotificationRecipient)
            .Any(item => item.NotificationId == workSequenceStatusNotification.NotificationId && item.IsRead),
        "work sequence notification should be marked as read");
    Require(
        services.History.ListHistory()
            .Any(item =>
                item.EventType == "work_sequence.notification_read" &&
                item.TargetId == secondWorkSequenceItem.ItemId),
        "reading a work sequence notification should be recorded in activity history");

    var handoverFolder = services.Folders.GetDefaultSystemFolder(FlowNoteLocalDatabase.HandoverFolderName);
    var photosFolder = services.Folders.GetDefaultSystemFolder(FlowNoteLocalDatabase.PhotosFolderName);

    var today = DateTime.Today.AddHours(9);
    var todayText = today.ToString("yyyyMMdd");
    var todayFolderName = today.ToString("yyyy-MM-dd");

    var todayHandoverFile = Path.Combine(testDirectory, $"인수인계당일주간조{todayText}{runStamp}.txt");
    File.WriteAllText(todayHandoverFile, $"당일 인수인계 테스트 {todayText}");
    var todayHandoverPlan = services.DocumentPlacement.PrepareDocumentRegistration(
        handoverFolder.Id,
        Path.GetFileName(todayHandoverFile),
        today,
        smokeActorName);
    Require(todayHandoverPlan.Folder.Name == todayFolderName, "today handover test must use today's date folder");
    var todayHandoverDocument = services.Documents.RegisterDocument(
        todayHandoverPlan.Folder.Id,
        todayHandoverPlan.Title,
        Path.GetFileName(todayHandoverFile),
        "Text",
        smokeActorName,
        todayHandoverFile,
        tags: ["handover", todayFolderName]);
    Require(
        services.Documents.ListDocuments(todayHandoverPlan.Folder.Id).Any(item =>
            item.DocumentId == todayHandoverDocument.DocumentId &&
            item.LocalPath == todayHandoverFile),
        "today handover document must be registered and listed");

    var todayPhotoFile = Path.Combine(testDirectory, $"사진당일라인A{todayText}{runStamp}.jpg");
    File.WriteAllBytes(todayPhotoFile, [0xFF, 0xD8, 0xFF, 0xD9]);
    var todayPhotoPlan = services.DocumentPlacement.PrepareDocumentRegistration(
        photosFolder.Id,
        Path.GetFileName(todayPhotoFile),
        today,
        smokeActorName);
    Require(todayPhotoPlan.Folder.Name == todayFolderName, "today photo test must use today's date folder");
    var todayPhotoDocument = services.Documents.RegisterDocument(
        todayPhotoPlan.Folder.Id,
        todayPhotoPlan.Title,
        Path.GetFileName(todayPhotoFile),
        "Image",
        smokeActorName,
        todayPhotoFile,
        tags: ["photo", "line-a", todayFolderName]);
    Require(
        services.Documents.ListDocuments(todayPhotoPlan.Folder.Id).Any(item =>
            item.DocumentId == todayPhotoDocument.DocumentId &&
            item.LocalPath == todayPhotoFile),
        "today photo document must be registered and listed");
    Console.WriteLine(
        $"Today document test: folder={todayFolderName}, handover={todayHandoverFile}, photo={todayPhotoFile}");

    var existingPastDateDocuments = ListExistingPastDateDocuments(
        services,
        handoverFolder.Id,
        photosFolder.Id,
        DateTime.Today);
    Require(
        existingPastDateDocuments.Count > 0,
        "random past date version test requires at least one existing past dated document in handover or photo folders");
    var randomPastDocument = existingPastDateDocuments[Random.Shared.Next(existingPastDateDocuments.Count)];
    var randomPastOriginalVersion = randomPastDocument.Document.VersionNo;
    var randomPastComment = $"random past existing date version up test {randomPastDocument.FolderName} {runId}";
    var randomPastVersion = services.Documents.AddCommentVersion(
        randomPastDocument.Document.DocumentId,
        randomPastComment,
        smokeActorName);
    Require(
        randomPastVersion.VersionNo == randomPastOriginalVersion + 1,
        "random past date document must support version up without creating a new past date document");
    Require(
        services.Documents.ListVersions(randomPastDocument.Document.DocumentId).Any(item =>
            item.VersionNo == randomPastVersion.VersionNo &&
            item.Comment == randomPastComment),
        "random past existing date version up must be recorded in document versions");
    Require(
        services.History.ListHistory().Any(item =>
            item.EventType == "document.version_added" &&
            item.ActorName == smokeActorName &&
            item.TargetId == randomPastDocument.Document.DocumentId),
        "random past date version up history must keep the actor name");
    Console.WriteLine(
        $"Random past existing date version test: folder={randomPastDocument.FolderName}, type={randomPastDocument.FlowType}, document={randomPastDocument.Document.FileName}, version=v{randomPastVersion.VersionNo}");

    var workOrderFolder = services.Folders.GetDefaultSystemFolder(FlowNoteLocalDatabase.WorkOrderFolderName);
    var workOrderPlan = services.DocumentPlacement.PrepareDocumentRegistration(
        workOrderFolder.Id,
        "assembly-check-sheet.xlsx",
        today,
        smokeActorName);
    Require(workOrderPlan.Folder.Id == workOrderFolder.Id, "work order files should remain in the work order folder");
    Require(workOrderPlan.Title == "assembly-check-sheet", "work order title should be generated from the file name");

    var drawingPlan = services.DocumentPlacement.PrepareDocumentRegistration(
        documentsFolder.Id,
        "도면-프레스A-금형배치.pdf",
        today,
        smokeActorName);
    Require(drawingPlan.Folder.Name == FlowNoteLocalDatabase.DrawingFolderName, "drawing files should be placed in the drawing folder");
    Require(drawingPlan.Folder.ParentId == documentsFolder.Id, "drawing folder should be below the documents folder");

    var safetyPlan = services.DocumentPlacement.PrepareDocumentRegistration(
        documentsFolder.Id,
        "문서-안전수칙-용접작업.txt",
        today,
        smokeActorName);
    Require(safetyPlan.Folder.Name == FlowNoteLocalDatabase.SafetyFolderName, "safety files should be placed in the safety folder");
    Require(safetyPlan.Folder.ParentId == documentsFolder.Id, "safety folder should be below the documents folder");

    var sampleFile = Path.Combine(testDirectory, "sample-upload.txt");
    File.WriteAllText(sampleFile, "FlowNote upload program test.");
    var uploadedDocument = services.Documents.RegisterDocument(
        currentDocumentFolder.Id,
        "sample-upload",
        "sample-upload.txt",
        "Text",
        smokeActorName,
        sampleFile);
    Require(uploadedDocument.LocalPath == sampleFile, "uploaded document should store the local file path");
    Require(
        services.Documents.ListDocuments(currentDocumentFolder.Id).Any(item => item.DocumentId == uploadedDocument.DocumentId && item.LocalPath == sampleFile),
        "uploaded document should be saved in the database document list");
    Require(
        services.Documents.ListVersions(uploadedDocument.DocumentId).Any(item => item.VersionNo == 1 && item.LocalPath == sampleFile),
        "uploaded document original version should store the local file path");

    var offlineSyncResult = await services.ServerSync.QueueAndTrySyncDocumentAsync(uploadedDocument, null);
    Require(!offlineSyncResult.Success, "missing server URL should keep document sync queued locally");
    Require(
        services.ServerSync.CountQueuedForEntity("document", uploadedDocument.DocumentId, "FAILED") == 1,
        "missing server URL should create a failed document sync queue row");

    var offlineQueuedFieldNote = services.FieldNotes.AddDocumentNote(
        uploadedDocument.DocumentId,
        $"Offline queued field note before server reconnect {runId}.",
        smokeActorName);
    var fieldNoteAttachmentFile = Path.Combine(testDirectory, $"field-note-attachment-{runId}.txt");
    File.WriteAllText(fieldNoteAttachmentFile, $"FieldNote attachment smoke test {runId}.");
    var offlineQueuedFieldNoteAttachment = services.FieldNotes.AddAttachment(
        offlineQueuedFieldNote.NoteId,
        fieldNoteAttachmentFile,
        smokeActorName,
        "Smoke test FieldNote attachment");
    Require(
        services.FieldNotes.ListAttachments(offlineQueuedFieldNote.NoteId).Any(item =>
            item.AttachmentId == offlineQueuedFieldNoteAttachment.AttachmentId &&
            item.OriginalFileName == Path.GetFileName(fieldNoteAttachmentFile) &&
            item.SizeBytes == new FileInfo(fieldNoteAttachmentFile).Length),
        "field note attachment should be saved locally with file metadata");
    var offlineFieldNoteSyncResult = await services.ServerSync.QueueAndTrySyncFieldNoteAsync(offlineQueuedFieldNote, null);
    Require(!offlineFieldNoteSyncResult.Success, "missing server URL should keep field note sync queued locally");
    Require(
        services.ServerSync.CountQueuedForEntity("field_note", offlineQueuedFieldNote.NoteId, "FAILED") == 1,
        "missing server URL should create a failed field note sync queue row");
    var offlineFieldNoteAttachmentSyncResult = await services.ServerSync.QueueAndTrySyncFieldNoteAttachmentAsync(
        offlineQueuedFieldNoteAttachment,
        null);
    Require(!offlineFieldNoteAttachmentSyncResult.Success, "missing server URL should keep field note attachment sync queued locally");
    Require(
        services.ServerSync.CountQueuedForEntity("field_note_attachment", offlineQueuedFieldNoteAttachment.AttachmentId, "FAILED") == 1,
        "missing server URL should create a failed field note attachment sync queue row");

    var offlineAccessLogId = services.DocumentViewLogs.StartDocumentView(
        uploadedDocument.DocumentId,
        uploadedDocument.VersionNo,
        smokeActorName);
    var offlineStartedAccessLog = services.DocumentViewLogs.GetLog(offlineAccessLogId)
        ?? throw new InvalidOperationException("offline access log should be readable after start");
    var offlineAccessLogStartSyncResult = await services.ServerSync.QueueAndTrySyncAccessLogAsync(
        offlineStartedAccessLog,
        "view_started",
        null);
    Require(!offlineAccessLogStartSyncResult.Success, "missing server URL should keep access start log sync queued locally");
    services.DocumentViewLogs.CloseDocumentView(offlineAccessLogId, "window_closed");
    var offlineClosedAccessLog = services.DocumentViewLogs.GetLog(offlineAccessLogId)
        ?? throw new InvalidOperationException("offline access log should be readable after close");
    var offlineAccessLogCloseSyncResult = await services.ServerSync.QueueAndTrySyncAccessLogAsync(
        offlineClosedAccessLog,
        "view_closed",
        null);
    Require(!offlineAccessLogCloseSyncResult.Success, "missing server URL should keep access close log sync queued locally");
    Require(
        services.ServerSync.CountQueuedForEntity("document_access_log", offlineAccessLogId.ToString(), "FAILED") == 2,
        "missing server URL should create failed access log sync queue rows for start and close");

    var syncFailureHistory = services.History.ListHistory();
    Require(
        syncFailureHistory.Any(item =>
            item.EventType == "server_sync.failed" &&
            item.TargetId == uploadedDocument.DocumentId),
        "server sync failure should be recorded in full local history");

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
    workspace.AddDroppedFileToList(uploadCandidate, smokeActorName);
    Require(workspace.Documents.Count == 1, "dropped file should be added to the file list");
    Require(workspace.Documents[0].UpdatedBy == smokeActorName, "dropped file should capture the login display name");
    Require(workspace.Documents[0].LocalPath == sampleFile, "dropped file should keep the local path for preview");

    var foremanLogin = services.Auth.Login("foreman-a", "1234");
    var leadLogin = services.Auth.Login("lead-a1", "1234");
    var memberLogin = services.Auth.Login("member-a1", "1234");
    Require(foremanLogin.Success, "foreman-a / 1234 login should succeed for document registration");
    Require(leadLogin.Success, "lead-a1 / 1234 login should succeed for field note registration");
    Require(memberLogin.Success, "member-a1 / 1234 login should succeed for field note registration");
    Require(
        RolePermissionPolicy.CanRegisterDocuments(foremanLogin.Role),
        "foreman role should be allowed to use document registration UI");
    Require(
        RolePermissionPolicy.CanRegisterDocuments(leadLogin.Role),
        "team lead role should be allowed to use document registration UI");
    Require(
        !RolePermissionPolicy.CanRegisterDocuments(memberLogin.Role),
        "team member role should not be allowed to use document registration UI");
    Require(
        RolePermissionPolicy.CanDownloadDocuments("admin"),
        "admin role should be allowed to use controlled document download");
    Require(
        RolePermissionPolicy.CanDownloadDocuments("document-admin"),
        "document admin role should be allowed to use controlled document download");
    Require(
        !RolePermissionPolicy.CanDownloadDocuments(foremanLogin.Role),
        "foreman role should not be allowed to download document copies");
    Require(
        !RolePermissionPolicy.CanDownloadDocuments(leadLogin.Role),
        "team lead role should not be allowed to download document copies");
    Require(
        !RolePermissionPolicy.CanDownloadDocuments(memberLogin.Role),
        "team member role should not be allowed to download document copies");
    Require(
        RolePermissionPolicy.CanManageFileWatch(login.Role),
        "admin role should be allowed to manage file watch");
    Require(
        RolePermissionPolicy.CanManageFileWatch("document-admin"),
        "document admin role should be allowed to manage file watch");
    Require(
        !RolePermissionPolicy.CanManageFileWatch(foremanLogin.Role),
        "foreman role should not be allowed to manage file watch");
    Require(
        !RolePermissionPolicy.CanManageFileWatch(leadLogin.Role),
        "team lead role should not be allowed to manage file watch");
    Require(
        !RolePermissionPolicy.CanManageFileWatch(memberLogin.Role),
        "team member role should not be allowed to manage file watch");
    Require(
        !RolePermissionPolicy.CanManageFileWatch("viewer"),
        "viewer role should not be allowed to manage file watch");

    var watchDirectory = Path.Combine(testDirectory, $"watch-{runId}");
    Directory.CreateDirectory(watchDirectory);
    var watchedFileName = $"watched-version-{runStamp}.txt";
    var originalWatchedFile = Path.Combine(testDirectory, $"original-{watchedFileName}");
    File.WriteAllText(originalWatchedFile, $"Original watched file {runId}", Encoding.UTF8);
    var watchedDocument = services.Documents.RegisterDocument(
        currentDocumentFolder.Id,
        $"Watched Version Document {runStamp}",
        watchedFileName,
        "Text",
        smokeActorName,
        originalWatchedFile);

    services.FileWatch.StartWatching(watchDirectory, smokeActorName);
    var changedWatchedFile = Path.Combine(watchDirectory, watchedFileName);
    File.WriteAllText(changedWatchedFile, $"Changed watched file {runId}", Encoding.UTF8);

    var detectedCandidate = await WaitForAsync(
        () => services.FileWatch.ListCandidates().FirstOrDefault(item =>
            string.Equals(
                Path.GetFullPath(item.SourcePath),
                Path.GetFullPath(changedWatchedFile),
                StringComparison.OrdinalIgnoreCase)),
        TimeSpan.FromSeconds(10));
    Require(detectedCandidate is not null, "file watcher should create a pending version candidate");
    Require(
        detectedCandidate!.DocumentId == watchedDocument.DocumentId,
        "file watch candidate should match an existing document by file name");
    Require(
        services.History.ListHistory().Any(item =>
            item.EventType == "file_watch.candidate_created" &&
            item.TargetId == detectedCandidate.CandidateId),
        "file watch candidate creation should be recorded in history");

    var missingReasonRejected = false;
    try
    {
        services.FileWatch.ConfirmCandidate(
            detectedCandidate.CandidateId,
            watchedDocument.DocumentId,
            "watch-v2",
            "",
            smokeActorName);
    }
    catch (ArgumentException)
    {
        missingReasonRejected = true;
    }

    Require(missingReasonRejected, "file watch candidate confirmation should require a change reason");

    var confirmedWatchDocument = services.FileWatch.ConfirmCandidate(
        detectedCandidate.CandidateId,
        watchedDocument.DocumentId,
        "watch-v2",
        "Smoke test confirmed a watched file as a new version.",
        smokeActorName);
    Require(confirmedWatchDocument.VersionNo == watchedDocument.VersionNo + 1, "confirmed watch candidate should add the next document version");
    Require(
        confirmedWatchDocument.LatestComment == "Smoke test confirmed a watched file as a new version.",
        "confirmed watch candidate should store the required change reason");
    var watchVersions = services.Documents.ListVersions(watchedDocument.DocumentId);
    Require(watchVersions[0].VersionNo == confirmedWatchDocument.VersionNo, "confirmed watch version should become latest");
    Require(watchVersions[0].VersionLabel == "watch-v2", "confirmed watch version should store the version label");
    Require(watchVersions[0].Comment == "Smoke test confirmed a watched file as a new version.", "confirmed watch version should store the change reason");
    Require(
        !string.IsNullOrWhiteSpace(watchVersions[0].LocalPath) &&
        File.Exists(FlowNoteLocalDatabase.ResolveLocalContentPath(watchVersions[0].LocalPath!)),
        "confirmed watch version should copy the changed file into local storage");
    Require(
        services.FileWatch.ListCandidates().All(item => item.CandidateId != detectedCandidate.CandidateId),
        "confirmed watch candidate should leave the pending candidate list");
    Require(
        services.History.ListHistory().Any(item =>
            item.EventType == "file_watch.candidate_confirmed" &&
            item.TargetId == detectedCandidate.CandidateId),
        "file watch candidate confirmation should be recorded in history");

    var ignoredWatchFile = Path.Combine(watchDirectory, $"ignored-{runStamp}.txt");
    File.WriteAllText(ignoredWatchFile, $"Ignored watched file {runId}", Encoding.UTF8);
    var ignoredCandidate = services.FileWatch.CaptureCandidateForPath(ignoredWatchFile, smokeActorName);
    services.FileWatch.IgnoreCandidate(ignoredCandidate.CandidateId, smokeActorName);
    Require(
        services.FileWatch.ListCandidates().All(item => item.CandidateId != ignoredCandidate.CandidateId),
        "ignored watch candidate should leave the pending candidate list");
    Require(
        services.History.ListHistory().Any(item =>
            item.EventType == "file_watch.candidate_ignored" &&
            item.TargetId == ignoredCandidate.CandidateId),
        "file watch candidate ignore should be recorded in history");
    services.FileWatch.StopWatching(smokeActorName);

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

    var blockedDownloadLogId = services.DocumentViewLogs.RecordDownloadBlocked(
        koreanPdfDocument.DocumentId,
        koreanPdfDocument.VersionNo,
        memberLogin.DisplayName ?? "team member",
        "Smoke test role policy blocked document download.");
    var blockedDownloadLog = services.DocumentViewLogs.GetLog(blockedDownloadLogId);
    Require(blockedDownloadLog is not null, "download blocked event should be recorded as a local access log");
    Require(blockedDownloadLog!.CloseReason == "download_blocked", "download blocked event should keep the close reason");
    Require(
        services.History.ListHistory().Any(item =>
            item.EventType == "document.download_blocked" &&
            item.ActorName == (memberLogin.DisplayName ?? "team member") &&
            item.TargetId == koreanPdfDocument.DocumentId),
        "download blocked event should be recorded in full local history");
    var blockedDownloadSyncResult = await services.ServerSync.QueueAndTrySyncAccessLogAsync(
        blockedDownloadLog,
        "download_blocked",
        null);
    Require(!blockedDownloadSyncResult.Success, "missing server URL should keep download blocked access log sync queued locally");
    Require(
        services.ServerSync.CountQueuedForEntity("document_access_log", blockedDownloadLogId.ToString(), "FAILED") == 1,
        "missing server URL should create one failed download blocked access log sync row");

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

    using var serverHttpClient = FlowNoteServerApiEnvironment.CreateHttpClientFromEnvironment(TimeSpan.FromSeconds(20));
    if (serverHttpClient is null)
    {
        Console.WriteLine("FLOWNOTE_API_BASE_URL is not set or invalid; server integration smoke blocks skipped.");
    }
    else
    {
        var serverAuth = new FlowNoteServerAuthClient(serverHttpClient);
        var serverDocuments = new FlowNoteServerDocumentClient(serverHttpClient);

        ServerLoginResponse serverLogin;
        {
            serverLogin = await serverAuth.TryLoginAsync("admin", "1234")
                ?? throw new InvalidOperationException("server login API should accept seeded admin / 1234");
            Require(serverLogin.Username == "admin", "server login API should return the admin username");
            Require(serverLogin.UserId == "user-admin", "server login API should return the seeded admin user id");
            Require(serverLogin.Role == "admin", "server login API should return the admin role");
            Require(!string.IsNullOrWhiteSpace(serverLogin.AccessToken), "server login API should return an access token");
            Require(
                serverLogin.ExpiresAt > DateTimeOffset.UtcNow,
                "server login API should return a future token expiration time");

            var rejectedLogin = await serverAuth.TryLoginAsync("admin", "wrong-password");
            Require(rejectedLogin is null, "server login API should reject a wrong password");
        }

        serverHttpClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", serverLogin.AccessToken);
        var currentServerUser = await serverAuth.TryGetCurrentUserAsync()
            ?? throw new InvalidOperationException("server /auth/me should accept the login bearer token");
        Require(currentServerUser.UserId == serverLogin.UserId, "server /auth/me should return the authenticated user id");
        Require(currentServerUser.Username == serverLogin.Username, "server /auth/me should return the authenticated username");

        {
            var serverWorkSequenceBoard = await serverDocuments.CreateWorkSequenceBoardAsync(
                new ServerWorkSequenceBoardCreateRequest
                {
                    Title = $"Server smoke work sequence {runStamp}",
                    Description = "Server work sequence API smoke block.",
                    LineCode = "line-a",
                    BoardDate = DateOnly.FromDateTime(DateTime.Today),
                    CreatedBy = serverLogin.UserId
                });
            Require(!string.IsNullOrWhiteSpace(serverWorkSequenceBoard.BoardId), "server work sequence board should receive an id");
            Require(serverWorkSequenceBoard.Items.Count == 0, "new server work sequence board should start empty");

            var serverWorkSequenceWithFirstItem = await serverDocuments.AddWorkSequenceItemAsync(
                serverWorkSequenceBoard.BoardId,
                new ServerWorkSequenceItemCreateRequest
                {
                    Title = $"Server prepare material {runStamp}",
                    AssignedTo = "line-a",
                    CreatedBy = serverLogin.UserId
                });
            var serverFirstItem = serverWorkSequenceWithFirstItem.Items.Single();
            Require(serverFirstItem.Status == "WAITING", "server work sequence item should start in WAITING");

            var serverWorkSequenceWithSecondItem = await serverDocuments.AddWorkSequenceItemAsync(
                serverWorkSequenceBoard.BoardId,
                new ServerWorkSequenceItemCreateRequest
                {
                    Title = $"Server start press run {runStamp}",
                    WorkOrderNo = $"WO-{runStamp}",
                    CreatedBy = serverLogin.UserId
                });
            var serverSecondItem = serverWorkSequenceWithSecondItem.Items.Single(item => item.ItemId != serverFirstItem.ItemId);
            Require(serverSecondItem.SortOrder == 2, "server second work sequence item should be appended");

            var serverReorderedBoard = await serverDocuments.ReorderWorkSequenceItemsAsync(
                serverWorkSequenceBoard.BoardId,
                new ServerWorkSequenceReorderRequest
                {
                    ItemIds = [serverSecondItem.ItemId, serverFirstItem.ItemId],
                    ActorId = serverLogin.UserId,
                    ChangeReason = "Windows smoke changed server work priority."
                });
            Require(
                serverReorderedBoard.Items[0].ItemId == serverSecondItem.ItemId,
                "server work sequence reorder should persist order");

            var serverStatusBoard = await serverDocuments.UpdateWorkSequenceItemStatusAsync(
                serverWorkSequenceBoard.BoardId,
                serverSecondItem.ItemId,
                new ServerWorkSequenceStatusUpdateRequest
                {
                    Status = "IN_PROGRESS",
                    ActorId = serverLogin.UserId,
                    ChangeReason = "Windows smoke started server work."
                });
            Require(
                serverStatusBoard.Items[0].Status == "IN_PROGRESS",
                "server work sequence status change should persist");

            var serverWorkSequenceHistory = await serverDocuments.ListWorkSequenceHistoryAsync(serverWorkSequenceBoard.BoardId);
            Require(
                serverWorkSequenceHistory.Any(item => item.ChangeType == "ITEM_REORDERED"),
                "server work sequence history should include reorder");
            Require(
                serverWorkSequenceHistory.Any(item => item.ChangeType == "STATUS_CHANGED"),
                "server work sequence history should include status change");

            var serverNotificationCandidates =
                await serverDocuments.ListWorkSequenceNotificationCandidatesAsync(serverWorkSequenceBoard.BoardId);
            var serverStatusCandidate = serverNotificationCandidates.FirstOrDefault(item =>
                item.EventType == "work_sequence.status_changed" &&
                item.ItemId == serverSecondItem.ItemId);
            Require(serverStatusCandidate is not null, "server work sequence status change should create a notification candidate");
            var sentServerCandidate = await serverDocuments.UpdateWorkSequenceNotificationCandidateStatusAsync(
                serverWorkSequenceBoard.BoardId,
                serverStatusCandidate!.CandidateId,
                new ServerWorkSequenceNotificationCandidateStatusRequest { Status = "SENT" });
            Require(sentServerCandidate.Status == "SENT", "server work sequence notification candidate should be markable as SENT");
        }

        var queuedRetryResult = await services.ServerSync.RetryPendingAsync(serverDocuments, serverLogin.UserId);
        Console.WriteLine(queuedRetryResult.Message);
        Require(queuedRetryResult.Attempted >= 5, "queued retry should attempt all offline server sync queue rows");
        using (var syncConnection = services.Database.OpenConnection())
        {
            var syncedServerDocumentId = ScalarString(
                syncConnection,
                """
                SELECT server_document_id
                FROM documents
                WHERE document_id = $document_id
                  AND synced_at IS NOT NULL;
                """,
                ("$document_id", uploadedDocument.DocumentId));
            var syncedServerVersionId = ScalarString(
                syncConnection,
                """
                SELECT server_version_id
                FROM documents
                WHERE document_id = $document_id
                  AND synced_at IS NOT NULL;
                """,
                ("$document_id", uploadedDocument.DocumentId));
            Require(!string.IsNullOrWhiteSpace(syncedServerDocumentId), "queued document retry should store the server document id");
            Require(!string.IsNullOrWhiteSpace(syncedServerVersionId), "queued document retry should store the server version id");
            Require(
                ScalarString(
                    syncConnection,
                    """
                    SELECT server_note_id
                    FROM field_notes
                    WHERE note_id = $note_id
                      AND synced_at IS NOT NULL;
                    """,
                    ("$note_id", offlineQueuedFieldNote.NoteId)) is { Length: > 0 },
                "queued field note retry should store the server note id");
            Require(
                ScalarString(
                    syncConnection,
                    """
                    SELECT server_attachment_id
                    FROM field_note_attachments
                    WHERE attachment_id = $attachment_id
                      AND synced_at IS NOT NULL;
                    """,
                    ("$attachment_id", offlineQueuedFieldNoteAttachment.AttachmentId)) is { Length: > 0 },
                "queued field note attachment retry should store the server attachment id");
            Require(
                ScalarLong(
                    syncConnection,
                    """
                    SELECT COUNT(*)
                    FROM document_view_logs
                    WHERE id = $id
                      AND server_start_log_id IS NOT NULL
                      AND server_close_log_id IS NOT NULL
                      AND synced_at IS NOT NULL;
                    """,
                    ("$id", offlineAccessLogId)) == 1,
                "queued access log retry should store server start and close log ids");
            Require(
                ScalarLong(
                    syncConnection,
                    """
                    SELECT COUNT(*)
                    FROM server_sync_queue
                    WHERE entity_id IN ($document_id, $note_id, $attachment_id, $log_id)
                      AND status = 'SYNCED';
                    """,
                    ("$document_id", uploadedDocument.DocumentId),
                    ("$note_id", offlineQueuedFieldNote.NoteId),
                    ("$attachment_id", offlineQueuedFieldNoteAttachment.AttachmentId),
                    ("$log_id", offlineAccessLogId.ToString())) == 5,
                "queued retry should mark document, field note attachment, field note, and access log queue rows as synced");
            Require(
                ScalarLong(
                    syncConnection,
                    """
                    SELECT COUNT(*)
                    FROM activity_history
                    WHERE event_type = 'server_sync.retry_attempted'
                      AND created_at >= $run_started_at;
                    """,
                    ("$run_started_at", runStartedAt.ToUniversalTime().ToString("O"))) >= 5,
                "queued retry attempts should be preserved in local history");
            Require(
                ScalarLong(
                    syncConnection,
                    """
                    SELECT COUNT(*)
                    FROM activity_history
                    WHERE event_type = 'server_sync.succeeded'
                      AND target_id IN ($document_id, $note_id, $attachment_id, $log_id)
                      AND created_at >= $run_started_at;
                    """,
                    ("$document_id", uploadedDocument.DocumentId),
                    ("$note_id", offlineQueuedFieldNote.NoteId),
                    ("$attachment_id", offlineQueuedFieldNoteAttachment.AttachmentId),
                    ("$log_id", offlineAccessLogId.ToString()),
                    ("$run_started_at", runStartedAt.ToUniversalTime().ToString("O"))) >= 4,
                "queued retry success should be preserved in local history");
            Require(
                ScalarString(
                    syncConnection,
                    """
                    SELECT idempotency_key
                    FROM server_sync_queue
                    WHERE entity_type = 'document' AND entity_id = $document_id
                    LIMIT 1;
                    """,
                    ("$document_id", uploadedDocument.DocumentId)) == ServerSyncService.CreateDocumentIdempotencyKey(uploadedDocument.DocumentId),
                "document sync queue should use the documented idempotency key");
            Require(
                ScalarString(
                    syncConnection,
                    """
                    SELECT idempotency_key
                    FROM server_sync_queue
                    WHERE entity_type = 'field_note' AND entity_id = $note_id
                    LIMIT 1;
                    """,
                    ("$note_id", offlineQueuedFieldNote.NoteId)) == ServerSyncService.CreateFieldNoteIdempotencyKey(offlineQueuedFieldNote.NoteId),
                "field note sync queue should use the documented idempotency key");
            Require(
                ScalarString(
                    syncConnection,
                    """
                    SELECT idempotency_key
                    FROM server_sync_queue
                    WHERE entity_type = 'field_note_attachment' AND entity_id = $attachment_id
                    LIMIT 1;
                    """,
                    ("$attachment_id", offlineQueuedFieldNoteAttachment.AttachmentId)) == ServerSyncService.CreateFieldNoteAttachmentIdempotencyKey(offlineQueuedFieldNoteAttachment.AttachmentId),
                "field note attachment sync queue should use the documented idempotency key");
            Require(
                ScalarString(
                    syncConnection,
                    """
                    SELECT idempotency_key
                    FROM server_sync_queue
                    WHERE entity_type = 'document_access_log'
                      AND entity_id = $log_id
                      AND action = 'register_access_log_started'
                    LIMIT 1;
                    """,
                    ("$log_id", offlineAccessLogId.ToString())) == ServerSyncService.CreateAccessLogIdempotencyKey(offlineAccessLogId, "view_started"),
                "access start log sync queue should use the documented idempotency key");
            Require(
                ScalarString(
                    syncConnection,
                    """
                    SELECT idempotency_key
                    FROM server_sync_queue
                    WHERE entity_type = 'document_access_log'
                      AND entity_id = $log_id
                      AND action = 'register_access_log_closed'
                    LIMIT 1;
                    """,
                    ("$log_id", offlineAccessLogId.ToString())) == ServerSyncService.CreateAccessLogIdempotencyKey(offlineAccessLogId, "view_closed"),
                "access close log sync queue should use the documented idempotency key");

            var duplicateQueueCountBefore = ScalarLong(
                syncConnection,
                """
                SELECT COUNT(*)
                FROM server_sync_queue
                WHERE entity_id IN ($document_id, $note_id, $attachment_id, $log_id);
                """,
                ("$document_id", uploadedDocument.DocumentId),
                ("$note_id", offlineQueuedFieldNote.NoteId),
                ("$attachment_id", offlineQueuedFieldNoteAttachment.AttachmentId),
                ("$log_id", offlineAccessLogId.ToString()));
            var duplicateAttemptCountBefore = ScalarLong(
                syncConnection,
                """
                SELECT COALESCE(SUM(attempt_count), 0)
                FROM server_sync_queue
                WHERE entity_id IN ($document_id, $note_id, $attachment_id, $log_id);
                """,
                ("$document_id", uploadedDocument.DocumentId),
                ("$note_id", offlineQueuedFieldNote.NoteId),
                ("$attachment_id", offlineQueuedFieldNoteAttachment.AttachmentId),
                ("$log_id", offlineAccessLogId.ToString()));
            _ = await services.ServerSync.QueueAndTrySyncDocumentAsync(
                uploadedDocument,
                serverDocuments,
                serverLogin.UserId);
            _ = await services.ServerSync.QueueAndTrySyncFieldNoteAsync(
                offlineQueuedFieldNote,
                serverDocuments,
                serverLogin.UserId);
            _ = await services.ServerSync.QueueAndTrySyncFieldNoteAttachmentAsync(
                offlineQueuedFieldNoteAttachment,
                serverDocuments,
                serverLogin.UserId);
            _ = await services.ServerSync.QueueAndTrySyncAccessLogAsync(
                offlineStartedAccessLog,
                "view_started",
                serverDocuments,
                serverLogin.UserId);
            _ = await services.ServerSync.QueueAndTrySyncAccessLogAsync(
                offlineClosedAccessLog,
                "view_closed",
                serverDocuments,
                serverLogin.UserId);
            var duplicateQueueCountAfter = ScalarLong(
                syncConnection,
                """
                SELECT COUNT(*)
                FROM server_sync_queue
                WHERE entity_id IN ($document_id, $note_id, $attachment_id, $log_id);
                """,
                ("$document_id", uploadedDocument.DocumentId),
                ("$note_id", offlineQueuedFieldNote.NoteId),
                ("$attachment_id", offlineQueuedFieldNoteAttachment.AttachmentId),
                ("$log_id", offlineAccessLogId.ToString()));
            var duplicateAttemptCountAfter = ScalarLong(
                syncConnection,
                """
                SELECT COALESCE(SUM(attempt_count), 0)
                FROM server_sync_queue
                WHERE entity_id IN ($document_id, $note_id, $attachment_id, $log_id);
                """,
                ("$document_id", uploadedDocument.DocumentId),
                ("$note_id", offlineQueuedFieldNote.NoteId),
                ("$attachment_id", offlineQueuedFieldNoteAttachment.AttachmentId),
                ("$log_id", offlineAccessLogId.ToString()));
            Require(
                duplicateQueueCountAfter == duplicateQueueCountBefore,
                "already synced queue items should not create duplicate queue rows");
            Require(
                duplicateAttemptCountAfter == duplicateAttemptCountBefore,
                "already synced queue items should not increment retry attempt counts");
        }

        var serverDocument = await serverDocuments.RegisterDocumentAsync(
            sampleFile,
            "Windows smoke upload",
            "client_smoke_test",
            "Windows smoke test registered this file through FastAPI.",
            description: "Registered by FlowNote.Windows.SmokeTests.",
            createdBy: serverLogin.UserId,
            tags: ["windows-smoke", "line-a"]);
        Require(!string.IsNullOrWhiteSpace(serverDocument.DocumentId), "server document should receive an id");
        Require(serverDocument.Tags.SequenceEqual(["line-a", "windows-smoke"]), "server document should preserve tags");
        var latestServerVersion = serverDocument.LatestVersion;
        Require(latestServerVersion is not null, "server document should include its latest version");
        Require(latestServerVersion!.VersionNo == 1, "server document should receive version 1");
        Require(latestServerVersion.File.SizeBytes == new FileInfo(sampleFile).Length, "server file size should match the uploaded file");

        var serverList = await serverDocuments.ListDocumentsAsync();
        Require(
            serverList.Any(item => item.DocumentId == serverDocument.DocumentId),
            "server document list should include the uploaded smoke document");
        Require(
            serverList.Any(item => item.DocumentId == serverDocument.DocumentId && item.Tags.SequenceEqual(["line-a", "windows-smoke"])),
            "server document list should include document tags");

        var serverVersions = await serverDocuments.ListVersionsAsync(serverDocument.DocumentId);
        Require(serverVersions.Count == 1, "server document should have one version after initial upload");
        Require(serverVersions[0].ChangeReason.Contains("FastAPI", StringComparison.Ordinal), "server version should preserve the change reason");

        {
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
                serverFieldNote.RawContent == "Program test field note stored separately from document versions.",
                "server field note should preserve raw content");
            Require(serverFieldNote.Status == "NEW", "server field note should start in NEW status");
            var serverFieldNoteAttachment = await serverDocuments.RegisterFieldNoteAttachmentAsync(
                serverFieldNote.NoteId,
                fieldNoteAttachmentFile,
                caption: "Windows smoke FieldNote attachment",
                createdBy: serverLogin.UserId);
            Require(!string.IsNullOrWhiteSpace(serverFieldNoteAttachment.AttachmentId), "server field note attachment should receive an id");
            Require(serverFieldNoteAttachment.NoteId == serverFieldNote.NoteId, "server field note attachment should reference the note");
            Require(
                serverFieldNoteAttachment.File.OriginalFilename == Path.GetFileName(fieldNoteAttachmentFile),
                "server field note attachment should preserve the original filename");
            Require(
                serverFieldNoteAttachment.File.SizeBytes == new FileInfo(fieldNoteAttachmentFile).Length,
                "server field note attachment should preserve the file size");
            Require(
                !string.IsNullOrWhiteSpace(serverFieldNoteAttachment.File.HashSha256),
                "server field note attachment should store a file hash");
            var serverFieldNoteAttachments = await serverDocuments.ListFieldNoteAttachmentsAsync(serverFieldNote.NoteId);
            Require(
                serverFieldNoteAttachments.Any(item => item.AttachmentId == serverFieldNoteAttachment.AttachmentId),
                "server field note attachment list should include the uploaded attachment");
        }

        {
            var startedAccessLog = await serverDocuments.RegisterAccessLogAsync(
                serverDocument.DocumentId,
                new ServerDocumentAccessLogCreateRequest
                {
                    DocumentVersionId = latestServerVersion.VersionId,
                    Action = "view_started",
                    ActorId = serverLogin.UserId,
                    UserAgent = "FlowNote.Windows.SmokeTests"
                });
            Require(startedAccessLog.LogId > 0, "server document view start log should receive an id");
            Require(startedAccessLog.DocumentId == serverDocument.DocumentId, "server document view start log should keep the document id");
            Require(startedAccessLog.DocumentVersionId == latestServerVersion.VersionId, "server document view start log should keep the version id");
            Require(startedAccessLog.Action == "view_started", "server document view start log should keep the action");
            Require(startedAccessLog.ActorId == serverLogin.UserId, "server document view start log should keep the actor id");

            var closedAccessLog = await serverDocuments.RegisterAccessLogAsync(
                serverDocument.DocumentId,
                new ServerDocumentAccessLogCreateRequest
                {
                    DocumentVersionId = latestServerVersion.VersionId,
                    Action = "view_closed",
                    ActorId = serverLogin.UserId,
                    UserAgent = "FlowNote.Windows.SmokeTests"
                });
            Require(closedAccessLog.LogId > 0, "server document view close log should receive an id");
            Require(closedAccessLog.Action == "view_closed", "server document view close log should keep the action");

            var serverAccessLogs = await serverDocuments.ListAccessLogsAsync(serverDocument.DocumentId);
            Require(
                serverAccessLogs.Any(item => item.LogId == startedAccessLog.LogId),
                "server document access log list should include the view start log");
            Require(
                serverAccessLogs.Any(item => item.LogId == closedAccessLog.LogId),
                "server document access log list should include the view close log");
        }

        {
            var secondServerVersion = await serverDocuments.RegisterVersionAsync(
                serverDocument.DocumentId,
                sampleFile,
                "Windows smoke test registered a working v2 before publish.",
                versionLabel: "v2",
                createdBy: serverLogin.UserId);
            Require(secondServerVersion.VersionNo == 2, "server document v2 should receive version number 2");
            Require(secondServerVersion.VersionStatus == "WORKING", "server document v2 should start as WORKING");
            Require(!secondServerVersion.IsPublished, "server document v2 should not publish automatically");

            var publishedServerDocument = await serverDocuments.PublishVersionAsync(
                serverDocument.DocumentId,
                secondServerVersion.VersionId,
                "Windows smoke test publishes v2 after review.");
            Require(publishedServerDocument.Status == "PUBLISHED", "server publish should set document status to PUBLISHED");
            Require(
                publishedServerDocument.LatestVersion?.VersionId == secondServerVersion.VersionId,
                "server publish should keep v2 as latest");
            Require(
                publishedServerDocument.PublishedVersion?.VersionId == secondServerVersion.VersionId,
                "server publish should set v2 as the published version");

            var publishedServerVersion = await serverDocuments.GetPublishedVersionAsync(serverDocument.DocumentId);
            Require(
                publishedServerVersion.VersionId == secondServerVersion.VersionId,
                "server public document lookup should return the published v2");

            var refreshedServerList = await serverDocuments.ListDocumentsAsync();
            Require(
                refreshedServerList.Any(item =>
                    item.DocumentId == serverDocument.DocumentId &&
                    item.LatestVersionNo == 2 &&
                    item.PublishedVersionNo == 2),
                "server document list should distinguish latest and published version numbers after publish");
        }
    }

    var deleted = services.Folders.DeleteFolder(currentDocumentFolder.Id);
    Require(!deleted, "current system document folder should not be deleted");

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

static async Task<T?> WaitForAsync<T>(Func<T?> action, TimeSpan timeout)
    where T : class
{
    var startedAt = DateTime.UtcNow;
    while (DateTime.UtcNow - startedAt < timeout)
    {
        var result = action();
        if (result is not null)
        {
            return result;
        }

        await Task.Delay(100);
    }

    return null;
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

static string? ScalarString(SqliteConnection connection, string sql, params (string Name, object Value)[] parameters)
{
    using var command = connection.CreateCommand();
    command.CommandText = sql;
    foreach (var parameter in parameters)
    {
        command.Parameters.AddWithValue(parameter.Name, parameter.Value);
    }

    var value = command.ExecuteScalar();
    return value is null or DBNull ? null : Convert.ToString(value);
}

static IReadOnlyList<(string FlowType, string FolderName, DocumentRecord Document)> ListExistingPastDateDocuments(
    FlowNoteLocalServices services,
    long handoverFolderId,
    long photosFolderId,
    DateTime today)
{
    var folders = services.Folders.ListFolders();
    var candidates = new List<(string FlowType, string FolderName, DocumentRecord Document)>();
    foreach (var parent in new[] { (FolderId: handoverFolderId, FlowType: "handover"), (FolderId: photosFolderId, FlowType: "photo") })
    {
        foreach (var folder in folders.Where(item => item.ParentId == parent.FolderId))
        {
            if (!DateTime.TryParseExact(
                    folder.Name,
                    "yyyy-MM-dd",
                    CultureInfo.InvariantCulture,
                    DateTimeStyles.None,
                    out var folderDate))
            {
                continue;
            }

            if (folderDate.Date >= today.Date)
            {
                continue;
            }

            foreach (var document in services.Documents.ListDocuments(folder.Id))
            {
                candidates.Add((parent.FlowType, folder.Name, document));
            }
        }
    }

    return candidates;
}

static T WithEnvironmentVariable<T>(string name, string value, Func<T> action)
{
    var previousValue = Environment.GetEnvironmentVariable(name);
    try
    {
        Environment.SetEnvironmentVariable(name, value);
        return action();
    }
    finally
    {
        Environment.SetEnvironmentVariable(name, previousValue);
    }
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
