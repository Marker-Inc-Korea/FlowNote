using FlowNote.Windows.Core.Storage;
using FlowNote.Windows.Core.Auth;
using FlowNote.Windows.Core.Documents;
using FlowNote.Windows.Core.Explorer;
using FlowNote.Windows.Core.Reports;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Sync;
using FlowNote.Windows.Core.WorkSequences;
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Threading;
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
    Require(login.Role == "system-admin", "local admin account should keep the system-admin role");
    var smokeActorName = login.DisplayName ?? "Administrator";

    var wrongLogin = services.Auth.Login("admin", "wrong");
    Require(!wrongLogin.Success, "wrong password should fail");

    var localFallbackAuth = new ServerAwareAuthService(services.Auth, null);
    var localFallbackLogin = await localFallbackAuth.LoginAsync("admin", "1234");
    Require(localFallbackLogin.Success, "missing server URL should allow local account login fallback");

    using (var unauthorizedServerClient = CreateStaticStatusClient(HttpStatusCode.Unauthorized))
    {
        var serverAwareAuth = new ServerAwareAuthService(services.Auth, unauthorizedServerClient);
        var unauthorizedLogin = await serverAwareAuth.LoginAsync("admin", "1234");
        Require(!unauthorizedLogin.Success, "server 401 should not fall back to local admin credentials");
        Require(
            unauthorizedLogin.FailureReason == "서버 로그인 ID 또는 비밀번호가 올바르지 않습니다.",
            "server 401 should show the Korean server login failure message");
    }

    using (var forbiddenServerClient = CreateStaticStatusClient(HttpStatusCode.Forbidden))
    {
        var serverAwareAuth = new ServerAwareAuthService(services.Auth, forbiddenServerClient);
        var forbiddenLogin = await serverAwareAuth.LoginAsync("admin", "1234");
        Require(!forbiddenLogin.Success, "server 403 should not fall back to local admin credentials");
        Require(
            forbiddenLogin.FailureReason == "서버 계정이 비활성 상태입니다. 관리자에게 문의하세요.",
            "server 403 should show the Korean inactive server account message");
    }

    using (var serverRoleClient = CreateJsonStatusClient(
        HttpStatusCode.OK,
        """
        {
          "user_id": "server-user-admin",
          "username": "admin",
          "role": "team-member",
          "display_name": "Server Admin",
          "access_token": "server-access-token",
          "token_type": "Bearer",
          "expires_at": "2030-01-01T00:00:00Z",
          "refresh_token": "server-refresh-token",
          "refresh_expires_at": "2030-01-02T00:00:00Z"
        }
        """))
    {
        var serverAwareAuth = new ServerAwareAuthService(services.Auth, serverRoleClient);
        var serverLogin = await serverAwareAuth.LoginAsync("admin", "1234");
        Require(serverLogin.Success, "server login success should use the server account result");
        Require(serverLogin.UserId == "server-user-admin", "server login should use the server user id");
        Require(serverLogin.Role == "team-member", "server login should use the server role when local role differs");
        Require(login.Role != serverLogin.Role, "server role priority smoke should compare against a different local role");
        AssertRolePolicy(
            serverLogin.Role,
            new RolePolicyExpectation("team-member", false, true, false, false, false, false, false),
            "server team-member role should drive WPF button policy instead of the local admin role");
    }

    foreach (var seededUser in FlowNoteLocalDatabase.DefaultUserSeeds)
    {
        var seededLogin = services.Auth.Login(seededUser.LoginId, "1234");
        Require(seededLogin.Success, $"{seededUser.LoginId} / 1234 login should succeed");
        Require(seededLogin.UserId == seededUser.UserId, $"{seededUser.LoginId} should keep the seeded user id");
        Require(seededLogin.DisplayName == seededUser.DisplayName, $"{seededUser.LoginId} should keep the seeded display name");
        Require(seededLogin.Role == seededUser.Role, $"{seededUser.LoginId} should keep the seeded role");
    }

    var userManagementTarget = FlowNoteLocalDatabase.DefaultUserSeeds.Single(user => user.LoginId == "member-a4");
    var temporaryDisplayName = $"사용자관리검증-{runStamp}";
    var temporaryPassword = $"pw-{runStamp}";
    var createdLoginId = $"smoke-user-{runStamp}";
    var createdPassword = $"created-{runStamp}";
    try
    {
        var createdUser = services.Users.CreateUser(
            createdLoginId,
            $"스모크 사용자 {runStamp}",
            "team-member",
            createdPassword,
            smokeActorName);
        Require(createdUser.UserId == $"user-{createdLoginId}", "created user should receive an immutable generated user id");
        Require(createdUser.LoginId == createdLoginId, "created user should keep the requested login id");
        Require(createdUser.Role == "team-member", "created user should keep the selected role");
        var createdLogin = services.Auth.Login(createdLoginId, createdPassword);
        Require(createdLogin.Success, "created user should be able to log in with the selected password");
        Require(createdLogin.UserId == createdUser.UserId, "created user login should return the generated user id");

        var updatedUser = services.Users.UpdateUserProfile(
            userManagementTarget.UserId,
            temporaryDisplayName,
            temporaryPassword,
            smokeActorName);
        Require(updatedUser.UserId == userManagementTarget.UserId, "user management should keep the immutable user id");
        Require(updatedUser.LoginId == userManagementTarget.LoginId, "user management should not change the login id");
        Require(updatedUser.DisplayName == temporaryDisplayName, "user management should update display name");

        var oldPasswordLogin = services.Auth.Login(userManagementTarget.LoginId, "1234");
        Require(!oldPasswordLogin.Success, "old password should stop working after password change");
        var temporaryPasswordLogin = services.Auth.Login(userManagementTarget.LoginId, temporaryPassword);
        Require(temporaryPasswordLogin.Success, "new password should work after password change");
        Require(temporaryPasswordLogin.UserId == userManagementTarget.UserId, "password change should keep the same user id");
    }
    finally
    {
        services.Users.UpdateUserProfile(
            userManagementTarget.UserId,
            userManagementTarget.DisplayName,
            "1234",
            smokeActorName);
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

    var fieldComment = services.FieldComments.AddDocumentComment(
        document.DocumentId,
        "Program test field comment stored separately from document versions.",
        smokeActorName);
    Require(!string.IsNullOrWhiteSpace(fieldComment.CommentId), "field comment should receive an id");
    Require(fieldComment.DocumentVersionNo == 1, "field comment should keep the current document version number");
    var fieldComments = services.FieldComments.ListDocumentComments(document.DocumentId);
    Require(fieldComments.Count == 1, "document should list the saved field comment");
    Require(fieldComments[0].RawContent == "Program test field comment stored separately from document versions.", "field comment should preserve raw content");
    Require(
        services.Documents.ListVersions(document.DocumentId).Count == 1,
        "field comment should not create a new document version");
    Require(
        services.Documents.ListDocuments(currentDocumentFolder.Id).Any(item =>
            item.DocumentId == document.DocumentId &&
            item.LatestComment == "Program test field comment stored separately from document versions."),
        "field comment should update the document latest comment summary");

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
            item.EventType == "field_comment.created" &&
            item.ActorName == smokeActorName &&
            item.TargetId == document.DocumentId),
        "history should record who added a field comment");
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
    Require(
        services.ServerSync.ListQueueItems().Any(item =>
            item.EntityType == "document" &&
            item.EntityId == uploadedDocument.DocumentId &&
            item.Status == "FAILED" &&
            item.LastError?.Contains("서버 URL이 설정되지 않아", StringComparison.Ordinal) == true),
        "sync queue list should show a Korean missing server URL reason for document failure");
    var failedDocumentQueueCountBefore = services.ServerSync.CountQueuedForEntity("document", uploadedDocument.DocumentId);
    _ = await services.ServerSync.QueueAndTrySyncDocumentAsync(uploadedDocument, null);
    Require(
        services.ServerSync.CountQueuedForEntity("document", uploadedDocument.DocumentId) == failedDocumentQueueCountBefore,
        "re-queuing a failed document should not create duplicate sync queue rows");

    var offlineQueuedFieldComment = services.FieldComments.AddDocumentComment(
        uploadedDocument.DocumentId,
        $"Offline queued field comment before server reconnect {runId}.",
        smokeActorName);
    var fieldCommentAttachmentFile = Path.Combine(testDirectory, $"field-comment-attachment-{runId}.txt");
    File.WriteAllText(fieldCommentAttachmentFile, $"FieldComment attachment smoke test {runId}.");
    var offlineQueuedFieldCommentAttachment = services.FieldComments.AddAttachment(
        offlineQueuedFieldComment.CommentId,
        fieldCommentAttachmentFile,
        smokeActorName,
        "Smoke test FieldComment attachment");
    Require(
        services.FieldComments.ListAttachments(offlineQueuedFieldComment.CommentId).Any(item =>
            item.AttachmentId == offlineQueuedFieldCommentAttachment.AttachmentId &&
            item.OriginalFileName == Path.GetFileName(fieldCommentAttachmentFile) &&
            item.SizeBytes == new FileInfo(fieldCommentAttachmentFile).Length),
        "field comment attachment should be saved locally with file metadata");
    var offlineFieldCommentSyncResult = await services.ServerSync.QueueAndTrySyncFieldCommentAsync(offlineQueuedFieldComment, null);
    Require(!offlineFieldCommentSyncResult.Success, "missing server URL should keep field comment sync queued locally");
    Require(
        services.ServerSync.CountQueuedForEntity("field_comment", offlineQueuedFieldComment.CommentId, "FAILED") == 1,
        "missing server URL should create a failed field comment sync queue row");
    Require(
        services.ServerSync.ListQueueItems().Any(item =>
            item.EntityType == "field_comment" &&
            item.EntityId == offlineQueuedFieldComment.CommentId &&
            item.Status == "FAILED" &&
            item.LastError?.Contains("서버 URL이 설정되지 않아", StringComparison.Ordinal) == true),
        "sync queue list should show a Korean missing server URL reason for field comment failure");
    var offlineFieldCommentAttachmentSyncResult = await services.ServerSync.QueueAndTrySyncFieldCommentAttachmentAsync(
        offlineQueuedFieldCommentAttachment,
        null);
    Require(!offlineFieldCommentAttachmentSyncResult.Success, "missing server URL should keep field comment attachment sync queued locally");
    Require(
        services.ServerSync.CountQueuedForEntity("field_comment_attachment", offlineQueuedFieldCommentAttachment.AttachmentId, "FAILED") == 1,
        "missing server URL should create a failed field comment attachment sync queue row");

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

    var offlineVersionFile = Path.Combine(testDirectory, $"sample-upload-v2-{runId}.txt");
    File.WriteAllText(offlineVersionFile, $"FlowNote upload program test v2 {runId}.");
    var offlineVersionDocument = services.Documents.AddFileVersion(
        uploadedDocument.DocumentId,
        Path.GetFileName(offlineVersionFile),
        offlineVersionFile,
        "v2",
        $"Offline queued file version before server reconnect {runId}.",
        smokeActorName);
    var offlineVersionSyncResult = await services.ServerSync.QueueAndTrySyncDocumentVersionAsync(
        offlineVersionDocument,
        null);
    Require(!offlineVersionSyncResult.Success, "missing server URL should keep document version sync queued locally");
    Require(
        services.ServerSync.CountQueuedForEntity("document_version", uploadedDocument.DocumentId, "FAILED") == 1,
        "missing server URL should create a failed document version sync queue row");

    var offlinePublishedDocument = services.Documents.PublishVersion(
        uploadedDocument.DocumentId,
        offlineVersionDocument.VersionNo,
        smokeActorName);
    var offlinePublishSyncResult = await services.ServerSync.QueueAndTrySyncDocumentPublishAsync(
        offlinePublishedDocument,
        null);
    Require(!offlinePublishSyncResult.Success, "missing server URL should keep document publish sync queued locally");
    Require(
        services.ServerSync.CountQueuedForEntity("document_publish", uploadedDocument.DocumentId, "FAILED") == 1,
        "missing server URL should create a failed document publish sync queue row");

    var offlineArchivedDocument = services.Documents.UpdateDocumentStatus(
        uploadedDocument.DocumentId,
        "ARCHIVED",
        smokeActorName);
    var offlineStatusSyncResult = await services.ServerSync.QueueAndTrySyncDocumentStatusAsync(
        offlineArchivedDocument,
        null);
    Require(!offlineStatusSyncResult.Success, "missing server URL should keep document status sync queued locally");
    Require(
        services.ServerSync.CountQueuedForEntity("document_status", uploadedDocument.DocumentId, "FAILED") == 1,
        "missing server URL should create a failed document status sync queue row");

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
    Require(leadLogin.Success, "lead-a1 / 1234 login should succeed for field comment registration");
    Require(memberLogin.Success, "member-a1 / 1234 login should succeed for field comment registration");
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
    Require(
        RolePermissionPolicy.CanWriteReports(login.Role),
        "admin role should be allowed to write reports");
    Require(
        RolePermissionPolicy.CanWriteReports("manager"),
        "manager role should be allowed to write reports");
    Require(
        RolePermissionPolicy.CanWriteReports("document-admin"),
        "document admin role should be allowed to write reports");
    Require(
        !RolePermissionPolicy.CanWriteReports(foremanLogin.Role),
        "foreman role should not be allowed to write reports");
    Require(
        !RolePermissionPolicy.CanWriteReports(leadLogin.Role),
        "team lead role should not be allowed to write reports");
    Require(
        !RolePermissionPolicy.CanWriteReports(memberLogin.Role),
        "team member role should not be allowed to write reports");
    Require(
        !RolePermissionPolicy.CanWriteReports("viewer"),
        "viewer role should not be allowed to write reports");

    var rolePolicyMatrix = new[]
    {
        new RolePolicyExpectation("admin", true, true, true, true, true, true, true),
        new RolePolicyExpectation("manager", true, true, true, true, false, false, true),
        new RolePolicyExpectation("viewer", false, true, false, false, false, false, false),
        new RolePolicyExpectation("system-admin", true, true, true, true, true, true, true),
        new RolePolicyExpectation("document-admin", true, true, true, true, false, false, true),
        new RolePolicyExpectation("assistant-manager", true, true, true, true, false, false, true),
        new RolePolicyExpectation("department-manager", true, true, true, true, false, false, true),
        new RolePolicyExpectation("line-foreman", true, true, false, false, false, false, false),
        new RolePolicyExpectation("team-lead", true, true, false, false, false, false, false),
        new RolePolicyExpectation("team-member", false, true, false, false, false, false, false)
    };
    Require(
        RolePermissionPolicy.UserRoleOptions.Select(option => option.Role).OrderBy(role => role)
            .SequenceEqual(rolePolicyMatrix.Select(expected => expected.Role).OrderBy(role => role)),
        "WPF role options should match the documented server role set");
    foreach (var expected in rolePolicyMatrix)
    {
        AssertRolePolicy(
            expected.Role,
            expected,
            $"{expected.Role} WPF button policy should match the documented server role matrix");
    }

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

    var previewCriteria = DocumentPreviewPolicy.SampleCriteria;
    foreach (var fileType in new[] { "TXT", "PDF", "XLSX", "이미지" })
    {
        foreach (var caseName in new[] { "정상", "비정상", "한글 파일명", "공백/괄호 파일명", "긴 경로", "큰 파일" })
        {
            Require(
                previewCriteria.Any(item => item.FileType == fileType && item.CaseName == caseName),
                $"{fileType} preview criteria should include {caseName}");
        }
    }

    Require(
        DocumentPreviewPolicy.ClassifyFileName("도면-프레스A-금형배치.dwg") == DocumentPreviewKind.Cad,
        "CAD files should stay in metadata-only preview scope");
    Require(
        DocumentPreviewPolicy.ClassifyFileName("작업절차서-현장.hwp") == DocumentPreviewKind.Hwp,
        "HWP files should stay in metadata-only preview scope");

    var factoryExceptionCriteria = DocumentPreviewPolicy.FactoryExceptionSampleCriteria;
    foreach (var expected in new[]
             {
                 ("TXT", "대용량"),
                 ("PDF", "손상"),
                 ("PDF", "암호/읽기 실패"),
                 ("TXT", "긴 경로/공백"),
                 ("XLSX", "큰 파일"),
                 ("이미지", "고해상도"),
                 ("이미지", "손상"),
                 ("CAD", "미지원"),
                 ("HWP", "미지원")
             })
    {
        Require(
            factoryExceptionCriteria.Any(item => item.FileType == expected.Item1 && item.CaseName == expected.Item2),
            $"{expected.Item1} factory exception criteria should include {expected.Item2}");
    }

    foreach (var criterion in factoryExceptionCriteria)
    {
        var samplePath = BuildFactoryExceptionSamplePath(testDirectory, criterion, runStamp);
        CreateFactoryExceptionSampleFile(criterion, samplePath);
        Require(File.Exists(samplePath), $"{criterion.FileType} factory exception sample should exist");
        Require(
            DocumentPreviewPolicy.ClassifyPath(samplePath) == criterion.PreviewKind,
            $"{criterion.FileType} factory exception sample should be classified as {criterion.PreviewKind}");

        if (criterion.FileType == "TXT" && criterion.CaseName == "대용량")
        {
            Require(
                new FileInfo(samplePath).Length > DocumentPreviewPolicy.MaxTextPreviewBytes,
                "large TXT sample should exceed the text preview limit");
        }

        if (criterion.FileType is "XLSX" || criterion is { FileType: "이미지", CaseName: "고해상도" })
        {
            Require(
                new FileInfo(samplePath).Length > DocumentPreviewPolicy.LargeSampleBytes,
                $"{criterion.FileType} large factory sample should exceed the large sample threshold");
        }

        if (criterion.CaseName == "긴 경로/공백")
        {
            Require(samplePath.Length >= 160, "long path preview sample should use a long local path");
            Require(
                samplePath.Contains(' ') && samplePath.Contains('(') && samplePath.Contains(')'),
                "long path preview sample should include spaces and parentheses");
        }

        var exceptionDocument = services.Documents.RegisterDocument(
            documentsFolder.Id,
            $"현장형 미리보기 예외 {criterion.FileType} {criterion.CaseName} {runStamp}",
            Path.GetFileName(samplePath),
            criterion.DocumentType,
            smokeActorName,
            samplePath,
            tags: ["preview-exception-smoke", criterion.FileType, criterion.CaseName]);

        var exceptionWindowCloseLogId = services.DocumentViewLogs.StartDocumentView(
            exceptionDocument.DocumentId,
            exceptionDocument.VersionNo,
            smokeActorName);
        services.DocumentViewLogs.CloseDocumentView(exceptionWindowCloseLogId, "window_closed");
        var exceptionAutoCloseLogId = services.DocumentViewLogs.StartDocumentView(
            exceptionDocument.DocumentId,
            exceptionDocument.VersionNo,
            smokeActorName);
        services.DocumentViewLogs.CloseDocumentView(exceptionAutoCloseLogId, "auto_closed");
        var exceptionDownloadBlockedLogId = services.DocumentViewLogs.RecordDownloadBlocked(
            exceptionDocument.DocumentId,
            exceptionDocument.VersionNo,
            memberLogin.DisplayName ?? "team member",
            $"{criterion.FileType} {criterion.CaseName} preview exception smoke blocked controlled copy.");

        if (criterion.RecordsPreviewFailed)
        {
            var failureMessage = BuildPreviewFailureSmokeMessage(criterion, samplePath);
            services.History.Record(
                "document.preview_failed",
                smokeActorName,
                "document",
                exceptionDocument.DocumentId,
                exceptionDocument.FileName,
                failureMessage);
            Require(
                ContainsKoreanPreviewGuidance(criterion, failureMessage),
                $"{criterion.FileType} preview failure should include Korean guidance");
            Require(
                services.History.ListHistory().Any(item =>
                    item.EventType == "document.preview_failed" &&
                    item.TargetId == exceptionDocument.DocumentId),
                $"{criterion.FileType} preview failure should be recorded in history");
        }

        using var exceptionLogConnection = services.Database.OpenConnection();
        Require(
            ScalarLong(
                exceptionLogConnection,
                """
                SELECT COUNT(*)
                FROM document_view_logs
                WHERE document_id = $document_id
                  AND closed_at IS NOT NULL
                  AND close_reason = 'window_closed';
                """,
                ("$document_id", exceptionDocument.DocumentId)) >= 1,
            $"{criterion.FileType} exception preview should record view close");
        Require(
            ScalarLong(
                exceptionLogConnection,
                """
                SELECT COUNT(*)
                FROM document_view_logs
                WHERE document_id = $document_id
                  AND closed_at IS NOT NULL
                  AND close_reason = 'auto_closed';
                """,
                ("$document_id", exceptionDocument.DocumentId)) >= 1,
            $"{criterion.FileType} exception preview should record auto close");
        Require(
            ScalarLong(
                exceptionLogConnection,
                """
                SELECT COUNT(*)
                FROM document_view_logs
                WHERE document_id = $document_id
                  AND closed_at IS NOT NULL
                  AND close_reason = 'download_blocked';
                """,
                ("$document_id", exceptionDocument.DocumentId)) >= 1,
            $"{criterion.FileType} exception preview should record download blocked");
        Require(
            services.History.ListHistory().Any(item =>
                item.EventType == "document.view_started" &&
                item.TargetId == exceptionDocument.DocumentId),
            $"{criterion.FileType} exception preview should record view start history");
        Require(
            services.History.ListHistory().Any(item =>
                item.EventType == "document.download_blocked" &&
                item.TargetId == exceptionDocument.DocumentId),
            $"{criterion.FileType} exception preview should record download blocked history");

        Console.WriteLine(
            $"Preview exception smoke: type={criterion.FileType}, case={criterion.CaseName}, sample={samplePath}, logs={exceptionWindowCloseLogId}/{exceptionAutoCloseLogId}/{exceptionDownloadBlockedLogId}");
    }

    var previewTxtPath = Path.Combine(testDirectory, $"미리보기-TXT-한글-{runStamp}.txt");
    File.WriteAllText(previewTxtPath, "TXT 정상 미리보기 샘플입니다.", Encoding.UTF8);
    var previewXlsxPath = Path.Combine(testDirectory, $"미리보기-XLSX-한글-{runStamp}.xlsx");
    CreateMinimalXlsx(previewXlsxPath);
    var previewImagePath = Path.Combine(testDirectory, $"미리보기-이미지-한글-{runStamp}.png");
    File.WriteAllBytes(previewImagePath, TinyPngBytes());

    var previewAuditSamples = new[]
    {
        ("TXT", previewTxtPath, "Text"),
        ("PDF", koreanPdfPath, "PDF"),
        ("XLSX", previewXlsxPath, "Spreadsheet"),
        ("이미지", previewImagePath, "Image")
    };

    foreach (var (fileType, samplePath, documentType) in previewAuditSamples)
    {
        Require(File.Exists(samplePath), $"{fileType} preview audit sample should exist");
        Require(
            DocumentPreviewPolicy.ClassifyPath(samplePath) is not DocumentPreviewKind.Missing and not DocumentPreviewKind.Unsupported,
            $"{fileType} preview audit sample should be classified");

        var previewDocument = services.Documents.RegisterDocument(
            documentsFolder.Id,
            $"미리보기 감사 로그 {fileType} {runStamp}",
            Path.GetFileName(samplePath),
            documentType,
            smokeActorName,
            samplePath,
            tags: ["preview-smoke", fileType]);

        var previewWindowCloseLogId = services.DocumentViewLogs.StartDocumentView(
            previewDocument.DocumentId,
            previewDocument.VersionNo,
            smokeActorName);
        services.DocumentViewLogs.CloseDocumentView(previewWindowCloseLogId, "window_closed");
        var previewAutoCloseLogId = services.DocumentViewLogs.StartDocumentView(
            previewDocument.DocumentId,
            previewDocument.VersionNo,
            smokeActorName);
        services.DocumentViewLogs.CloseDocumentView(previewAutoCloseLogId, "auto_closed");
        var previewDownloadBlockedLogId = services.DocumentViewLogs.RecordDownloadBlocked(
            previewDocument.DocumentId,
            previewDocument.VersionNo,
            memberLogin.DisplayName ?? "team member",
            $"{fileType} preview smoke blocked controlled copy.");

        using var previewLogConnection = services.Database.OpenConnection();
        Require(
            ScalarLong(
                previewLogConnection,
                """
                SELECT COUNT(*)
                FROM document_view_logs
                WHERE document_id = $document_id
                  AND closed_at IS NOT NULL
                  AND close_reason = 'window_closed';
                """,
                ("$document_id", previewDocument.DocumentId)) >= 1,
            $"{fileType} preview should record view close");
        Require(
            ScalarLong(
                previewLogConnection,
                """
                SELECT COUNT(*)
                FROM document_view_logs
                WHERE document_id = $document_id
                  AND closed_at IS NOT NULL
                  AND close_reason = 'auto_closed';
                """,
                ("$document_id", previewDocument.DocumentId)) >= 1,
            $"{fileType} preview should record auto close");
        Require(
            ScalarLong(
                previewLogConnection,
                """
                SELECT COUNT(*)
                FROM document_view_logs
                WHERE document_id = $document_id
                  AND closed_at IS NOT NULL
                  AND close_reason = 'download_blocked';
                """,
                ("$document_id", previewDocument.DocumentId)) >= 1,
            $"{fileType} preview should record download blocked");
        Require(
            services.History.ListHistory().Any(item =>
                item.EventType == "document.view_started" &&
                item.TargetId == previewDocument.DocumentId),
            $"{fileType} preview should record view start history");
        Require(
            services.History.ListHistory().Any(item =>
                item.EventType == "document.download_blocked" &&
                item.TargetId == previewDocument.DocumentId),
            $"{fileType} preview should record download blocked history");

        Console.WriteLine(
            $"Preview audit smoke: type={fileType}, sample={samplePath}, logs={previewWindowCloseLogId}/{previewAutoCloseLogId}/{previewDownloadBlockedLogId}");
    }

    var leadFieldComment = services.FieldComments.AddDocumentComment(
        koreanPdfDocument.DocumentId,
        "조장 A-1 확인: PDF 한글 표시 정상, 혼합 공정 온도 기준 확인 완료.",
        leadLogin.DisplayName ?? "조장 A-1",
        commentType: "experience",
        inputMode: "template_with_text",
        signalLevel: "green",
        reportedBy: leadLogin.DisplayName,
        operatorName: "반장 A 작업조",
        deviceId: "device-line-a-01",
        locationCode: "line-a");
    Require(leadFieldComment.DocumentVersionNo == 1, "lead field comment should point to Korean PDF version 1");
    Require(leadFieldComment.RawContent.Contains("PDF 한글 표시 정상", StringComparison.Ordinal),
        "lead field comment should preserve Korean content");

    var memberFieldComment = services.FieldComments.AddDocumentComment(
        koreanPdfDocument.DocumentId,
        "조원 A-1 확인: 설비 점검 항목을 작업 전에 읽을 수 있었음.",
        memberLogin.DisplayName ?? "조원 A-1",
        commentType: "work_evaluation",
        inputMode: "free_text",
        signalLevel: "green",
        reportedBy: memberLogin.DisplayName,
        operatorName: "반장 A 작업조",
        deviceId: "device-line-a-02",
        locationCode: "line-a");
    Require(memberFieldComment.DocumentVersionNo == 1, "member field comment should point to Korean PDF version 1");

    var koreanPdfNotes = services.FieldComments.ListDocumentComments(koreanPdfDocument.DocumentId);
    Require(koreanPdfNotes.Count == 2, "Korean PDF document should list both field comments");
    Require(koreanPdfNotes.Any(note => note.AuthorName == "조장 A-1"), "Korean PDF notes should include lead comment");
    Require(koreanPdfNotes.Any(note => note.AuthorName == "조원 A-1"), "Korean PDF notes should include member comment");
    Require(
        services.Documents.ListVersions(koreanPdfDocument.DocumentId).Count == 1,
        "Korean PDF field comments should not create document versions");
    Require(
        services.Documents.ListDocuments(documentsFolder.Id).Any(item =>
            item.DocumentId == koreanPdfDocument.DocumentId &&
            item.LatestComment == "조원 A-1 확인: 설비 점검 항목을 작업 전에 읽을 수 있었음."),
        "Korean PDF document latest comment should reflect the newest field comment");
    Require(
        services.Notifications.ListNotifications("반장 A").Count >= 2,
        "Korean PDF field comments should notify the foreman document creator");

    var managerLogin = services.Auth.Login("manager", "1234");
    var memberA2Login = services.Auth.Login("member-a2", "1234");
    var leadB1Login = services.Auth.Login("lead-b1", "1234");
    var memberB1Login = services.Auth.Login("member-b1", "1234");
    Require(managerLogin.Success, "manager / 1234 login should succeed for AI readiness review");
    Require(memberA2Login.Success, "member-a2 / 1234 login should succeed for human-like smoke activity");
    Require(leadB1Login.Success, "lead-b1 / 1234 login should succeed for human-like smoke activity");
    Require(memberB1Login.Success, "member-b1 / 1234 login should succeed for human-like smoke activity");

    var aiEvidenceFile = Path.Combine(testDirectory, $"ai-readiness-evidence-{runId}.txt");
    File.WriteAllText(
        aiEvidenceFile,
        """
        AI 근거 축적용 익명 작업 기록입니다.
        설비: press-a
        품목: bracket-42
        공정: mixed-press
        오류유형: alignment-delay
        """,
        Encoding.UTF8);
    var aiEvidenceDocument = services.Documents.RegisterDocument(
        currentDocumentFolder.Id,
        $"AI 근거 축적 스모크 작업표준 {runStamp}",
        Path.GetFileName(aiEvidenceFile),
        "Text",
        managerLogin.DisplayName ?? "관리자",
        aiEvidenceFile,
        tags: ["ai-readiness", "equipment:press-a", "item:bracket-42", "process:mixed-press", "issue:alignment-delay"]);
    aiEvidenceDocument = services.Documents.PublishVersion(
        aiEvidenceDocument.DocumentId,
        aiEvidenceDocument.VersionNo,
        managerLogin.DisplayName ?? "관리자");
    Require(aiEvidenceDocument.Status == "PUBLISHED", "AI readiness evidence document should be published for search candidate quality");

    var humanActors = new[]
    {
        (Login: foremanLogin, DeviceId: "device-line-a-foreman", Location: "line-a", Signal: "green", Memo: "반장 A 확인: 전 교대 금형 위치 기준과 현재 작업표준 일치."),
        (Login: leadLogin, DeviceId: "device-line-a-lead-01", Location: "line-a", Signal: "yellow", Memo: "조장 A-1 확인: 투입 전 정렬 지연 2회, 가이드핀 청소 후 정상화."),
        (Login: memberLogin, DeviceId: "device-line-a-02", Location: "line-a", Signal: "green", Memo: "조원 A-1 기록: 사진 기준 위치와 실제 클램프 방향 일치."),
        (Login: memberA2Login, DeviceId: "device-line-a-03", Location: "line-a", Signal: "yellow", Memo: "조원 A-2 기록: 소재 대기 중 짧은 보류 발생, 다음 조에 전달 필요."),
        (Login: leadB1Login, DeviceId: "device-line-b-lead-01", Location: "line-b", Signal: "red", Memo: "조장 B-1 확인: 동일 품목 전환 시 센서 재영점 절차 누락 위험."),
        (Login: memberB1Login, DeviceId: "device-line-b-02", Location: "line-b", Signal: "green", Memo: "조원 B-1 기록: 재영점 후 첫 제품 외관 이상 없음.")
    };
    var humanLikeComments = new List<string>();
    foreach (var activity in humanActors)
    {
        var actorName = activity.Login.DisplayName ?? activity.Login.LoginId ?? "현장 사용자";
        var viewLog = services.DocumentViewLogs.StartDocumentView(
            aiEvidenceDocument.DocumentId,
            aiEvidenceDocument.VersionNo,
            actorName);
        await SimulateHumanPauseAsync();
        services.DocumentViewLogs.CloseDocumentView(viewLog, "window_closed");
        await SimulateHumanPauseAsync();

        var comment = services.FieldComments.AddDocumentComment(
            aiEvidenceDocument.DocumentId,
            $"{activity.Memo} run={runId}",
            actorName,
            commentType: activity.Signal == "red" ? "issue" : "experience",
            inputMode: activity.Signal == "green" ? "template_with_text" : "free_text",
            signalLevel: activity.Signal,
            reportedBy: actorName,
            operatorName: "AI 근거 축적 스모크 작업조",
            deviceId: activity.DeviceId,
            locationCode: activity.Location);
        humanLikeComments.Add(comment.CommentId);
        await SimulateHumanPauseAsync();
    }
    var excludedAiComment = services.FieldComments.AddDocumentComment(
        aiEvidenceDocument.DocumentId,
        $"관리자 제외 검증용 FieldComment run={runId}",
        managerLogin.DisplayName ?? "관리자",
        commentType: "issue",
        inputMode: "free_text",
        reportedBy: managerLogin.DisplayName,
        operatorName: "AI 근거 축적 스모크 작업조",
        deviceId: "device-line-a-manager",
        locationCode: "line-a");
    var archivedAiComment = services.FieldComments.AddDocumentComment(
        aiEvidenceDocument.DocumentId,
        $"관리자 보관 검증용 FieldComment run={runId}",
        managerLogin.DisplayName ?? "관리자",
        commentType: "issue",
        inputMode: "free_text",
        reportedBy: managerLogin.DisplayName,
        operatorName: "AI 근거 축적 스모크 작업조",
        deviceId: "device-line-a-manager",
        locationCode: "line-a");

    using (var aiReadinessConnection = services.Database.OpenConnection())
    {
        ExecuteNonQuery(
            aiReadinessConnection,
            """
            UPDATE field_comments
            SET status = CASE comment_id
                    WHEN $comment1 THEN 'ANALYZED'
                    WHEN $comment2 THEN 'REVIEWED'
                    WHEN $comment3 THEN 'SELECTED'
                    ELSE status
                END,
                normalized_content = CASE comment_id
                    WHEN $comment1 THEN '정렬 지연은 가이드핀 청소 후 정상화됨.'
                    WHEN $comment2 THEN '보류 발생 사항은 다음 조 인수인계 대상으로 분류됨.'
                    WHEN $comment3 THEN '센서 재영점 절차 누락 위험을 관리자 검토 대상으로 선정함.'
                    ELSE normalized_content
                END,
                analysis_content = CASE comment_id
                    WHEN $comment1 THEN '공정 전 청소 기준을 작업표준과 연결해 재발 여부를 추적한다.'
                    WHEN $comment2 THEN '보류 사유와 전달 누락 여부를 보고서 근거로 남긴다.'
                    WHEN $comment3 THEN 'AI 검색 후보에서 절차 누락 위험 사례로 역추적 가능해야 한다.'
                    ELSE analysis_content
                END
            WHERE comment_id IN ($comment1, $comment2, $comment3);
            """,
            ("$comment1", humanLikeComments[1]),
            ("$comment2", humanLikeComments[3]),
            ("$comment3", humanLikeComments[4]));
        ExecuteNonQuery(
            aiReadinessConnection,
            """
            UPDATE field_comments
            SET status = CASE comment_id
                    WHEN $excluded_comment THEN 'EXCLUDED'
                    WHEN $archived_comment THEN 'ARCHIVED'
                    ELSE status
                END,
                normalized_content = '보고서 및 AI 후보 제외 검증용 기록',
                analysis_content = '관리자가 보고서 근거로 사용하지 않기로 결정한 항목'
            WHERE comment_id IN ($excluded_comment, $archived_comment);
            """,
            ("$excluded_comment", excludedAiComment.CommentId),
            ("$archived_comment", archivedAiComment.CommentId));
    }
    foreach (var reviewedCommentId in humanLikeComments.Skip(1).Take(4))
    {
        services.History.Record(
            "field_comment.reviewed",
            managerLogin.DisplayName,
            "field_comment",
            reviewedCommentId,
            aiEvidenceDocument.Title,
            "AI 근거 축적 스모크: 현장 코멘트 관리자 검토 상태 기록");
    }

    var aiFieldCommentSources = services.Reports.ListFieldCommentSources(limit: 500)
        .Where(source => humanLikeComments.Contains(source.SourceId))
        .ToList();
    Require(aiFieldCommentSources.Count == humanLikeComments.Count, "AI readiness report sources should include all human-like field comments");
    Require(
        aiFieldCommentSources.Take(3).Select(source => source.SourceId).SequenceEqual(new[]
        {
            humanLikeComments[4],
            humanLikeComments[3],
            humanLikeComments[1]
        }),
        "AI readiness report sources should show SELECTED, REVIEWED, and ANALYZED field comments first");
    var excludedAiFieldCommentSources = services.Reports.ListFieldCommentSources(limit: 500)
        .Where(source => source.SourceId == excludedAiComment.CommentId || source.SourceId == archivedAiComment.CommentId)
        .ToList();
    Require(
        excludedAiFieldCommentSources.Count == 0,
        "AI readiness report sources should exclude EXCLUDED and ARCHIVED field comments");
    var aiReportSources = aiFieldCommentSources
        .Take(3)
        .Concat(new[]
        {
            new ReportSourceCandidateRecord(
                "DOCUMENT",
                aiEvidenceDocument.DocumentId,
                aiEvidenceDocument.Title,
                aiEvidenceDocument.FileName,
                aiEvidenceDocument.UpdatedAt,
                aiEvidenceDocument.VersionNo.ToString(CultureInfo.InvariantCulture),
                "related_document")
        })
        .ToList();
    var aiReportContent = services.Reports.BuildDraftContent(
        $"AI 근거 축적 스모크 보고서 {runStamp}",
        "여러 현장 계정이 남긴 FieldComment와 공개 문서를 묶어 향후 AI 검색 근거로 추적한다.",
        aiReportSources,
        managerLogin.DisplayName ?? "관리자");
    var aiReportDocument = services.Reports.SaveDraftAsDocument(
        currentDocumentFolder.Id,
        $"AI 근거 축적 스모크 보고서 {runStamp}",
        aiReportContent,
        managerLogin.DisplayName ?? "관리자",
        aiReportSources,
        "여러 현장 계정이 남긴 FieldComment와 공개 문서를 묶어 향후 AI 검색 근거로 추적한다.");
    using (var aiReportConnection = services.Database.OpenConnection())
    {
        Require(
            ScalarLong(
                aiReportConnection,
                """
                SELECT COUNT(*)
                FROM report_sources
                WHERE local_report_document_id = $document_id
                  AND source_type IN ('FIELD_COMMENT', 'DOCUMENT');
                """,
                ("$document_id", aiReportDocument.DocumentId)) == 4,
            "AI readiness report should preserve FieldComment and document source links");
        Require(
            ScalarLong(
                aiReportConnection,
                """
                SELECT COUNT(*)
                FROM field_comments
                WHERE comment_id IN ($comment1, $comment2, $comment3)
                  AND status IN ('ANALYZED', 'REVIEWED', 'SELECTED')
                  AND normalized_content IS NOT NULL
                  AND analysis_content IS NOT NULL;
                """,
                ("$comment1", humanLikeComments[1]),
                ("$comment2", humanLikeComments[3]),
                ("$comment3", humanLikeComments[4])) == 3,
            "AI readiness reviewed field comments should keep normalized and analysis text");
    }
    Console.WriteLine(
        $"AI readiness human-like smoke: document={aiEvidenceDocument.DocumentId}, comments={humanLikeComments.Count}, report={aiReportDocument.DocumentId}");

    var configuredServerBaseUrl = Environment.GetEnvironmentVariable(
        FlowNoteServerApiEnvironment.ApiBaseUrlEnvironmentVariable);
    var serverSmokeBaseUrl = string.IsNullOrWhiteSpace(configuredServerBaseUrl)
        ? FlowNoteServerApiEnvironment.LocalLoopbackApiBaseUrl
        : configuredServerBaseUrl;
    using var serverHttpClient = FlowNoteServerApiEnvironment.CreateHttpClient(
        serverSmokeBaseUrl,
        TimeSpan.FromSeconds(20));
    if (serverHttpClient is null)
    {
        Console.WriteLine("FLOWNOTE_API_BASE_URL is not set or invalid; server integration smoke blocks skipped.");
    }
    else if (string.IsNullOrWhiteSpace(configuredServerBaseUrl) && !await IsServerAvailableAsync(serverHttpClient))
    {
        Console.WriteLine(
            "FLOWNOTE_API_BASE_URL is not set and http://127.0.0.1:5184 is not reachable; server integration smoke blocks skipped.");
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

        var authExpiredDocument = services.Documents.RegisterDocument(
            currentDocumentFolder.Id,
            $"auth-expired-sync-{runId}",
            $"auth-expired-sync-{runId}.txt",
            "Text",
            smokeActorName,
            sampleFile);
        var authExpiredQueueResult = await services.ServerSync.QueueAndTrySyncDocumentAsync(authExpiredDocument, null);
        Require(!authExpiredQueueResult.Success, "missing server URL should queue the auth-expired preservation document");
        var authExpiredQueueCountBefore = services.ServerSync.CountQueuedForEntity("document", authExpiredDocument.DocumentId);
        using (var unauthorizedHttpClient = CreateStaticStatusClient(HttpStatusCode.Unauthorized))
        {
            var unauthorizedDocuments = new FlowNoteServerDocumentClient(unauthorizedHttpClient);
            var authExpiredRetryResult = await services.ServerSync.RetryPendingAsync(unauthorizedDocuments, serverLogin.UserId);
            Require(!authExpiredRetryResult.Success, "server 401 should fail retry without deleting queued data");
        }

        using (var authExpiredConnection = services.Database.OpenConnection())
        {
            Require(
                ScalarLong(
                    authExpiredConnection,
                    """
                    SELECT COUNT(*)
                    FROM documents
                    WHERE document_id = $document_id
                      AND server_document_id IS NULL;
                    """,
                    ("$document_id", authExpiredDocument.DocumentId)) == 1,
                "server 401 retry should preserve the local document without server ids");
            Require(
                ScalarLong(
                    authExpiredConnection,
                    """
                    SELECT COUNT(*)
                    FROM server_sync_queue
                    WHERE entity_type = 'document'
                      AND entity_id = $document_id
                      AND status = 'FAILED'
                      AND last_error LIKE '%로그인%'
                      AND synced_at IS NULL;
                    """,
                    ("$document_id", authExpiredDocument.DocumentId)) == authExpiredQueueCountBefore,
                "server 401 retry should keep the sync queue row failed with an actionable login message");
        }

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
        Require(queuedRetryResult.Attempted >= 8, "queued retry should attempt all offline server sync queue rows");
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
                    SELECT server_comment_id
                    FROM field_comments
                    WHERE comment_id = $comment_id
                      AND synced_at IS NOT NULL;
                    """,
                    ("$comment_id", offlineQueuedFieldComment.CommentId)) is { Length: > 0 },
                "queued field comment retry should store the server comment id");
            Require(
                ScalarString(
                    syncConnection,
                    """
                    SELECT server_attachment_id
                    FROM field_comment_attachments
                    WHERE attachment_id = $attachment_id
                      AND synced_at IS NOT NULL;
                    """,
                    ("$attachment_id", offlineQueuedFieldCommentAttachment.AttachmentId)) is { Length: > 0 },
                "queued field comment attachment retry should store the server attachment id");
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
                    FROM document_versions
                    WHERE document_id = $document_id
                      AND version_no = $version_no
                      AND server_version_id IS NOT NULL
                      AND synced_at IS NOT NULL;
                    """,
                    ("$document_id", uploadedDocument.DocumentId),
                    ("$version_no", offlineVersionDocument.VersionNo)) == 1,
                "queued document version retry should store the server version id");
            Require(
                ScalarLong(
                    syncConnection,
                    """
                    SELECT COUNT(*)
                    FROM documents
                    WHERE document_id = $document_id
                      AND status = 'ARCHIVED'
                      AND published_version_no = $version_no
                      AND server_document_id IS NOT NULL
                      AND server_version_id IS NOT NULL
                      AND synced_at IS NOT NULL;
                    """,
                    ("$document_id", uploadedDocument.DocumentId),
                    ("$version_no", offlineVersionDocument.VersionNo)) == 1,
                "queued publish and status retry should preserve local published version and final status");
            Require(
                ScalarLong(
                    syncConnection,
                    """
                    SELECT COUNT(*)
                    FROM server_sync_queue
                    WHERE entity_id IN ($document_id, $comment_id, $attachment_id, $log_id)
                      AND status = 'SYNCED';
                    """,
                    ("$document_id", uploadedDocument.DocumentId),
                    ("$comment_id", offlineQueuedFieldComment.CommentId),
                    ("$attachment_id", offlineQueuedFieldCommentAttachment.AttachmentId),
                    ("$log_id", offlineAccessLogId.ToString())) == 8,
                "queued retry should mark document, version, publish, status, field comment, attachment, and access log queue rows as synced");
            Require(
                services.ServerSync.ListQueueItems().Count(item =>
                    item.EntityId == uploadedDocument.DocumentId &&
                    item.Status == "SYNCED") >= 4,
                "sync queue list should show document, version, publish, and status queue rows as synced after retry");
            Require(
                ScalarLong(
                    syncConnection,
                    """
                    SELECT COUNT(*)
                    FROM activity_history
                    WHERE event_type = 'server_sync.retry_attempted'
                      AND created_at >= $run_started_at;
                    """,
                    ("$run_started_at", runStartedAt.ToUniversalTime().ToString("O"))) >= 8,
                "queued retry attempts should be preserved in local history");
            Require(
                ScalarLong(
                    syncConnection,
                    """
                    SELECT COUNT(*)
                    FROM activity_history
                    WHERE event_type = 'server_sync.succeeded'
                      AND target_id IN ($document_id, $comment_id, $attachment_id, $log_id)
                      AND created_at >= $run_started_at;
                    """,
                    ("$document_id", uploadedDocument.DocumentId),
                    ("$comment_id", offlineQueuedFieldComment.CommentId),
                    ("$attachment_id", offlineQueuedFieldCommentAttachment.AttachmentId),
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
                    WHERE entity_type = 'document_version'
                      AND entity_id = $document_id
                      AND local_version_no = $version_no
                    LIMIT 1;
                    """,
                    ("$document_id", uploadedDocument.DocumentId),
                    ("$version_no", offlineVersionDocument.VersionNo)) == ServerSyncService.CreateDocumentVersionIdempotencyKey(uploadedDocument.DocumentId, offlineVersionDocument.VersionNo),
                "document version sync queue should use the documented idempotency key");
            Require(
                ScalarString(
                    syncConnection,
                    """
                    SELECT idempotency_key
                    FROM server_sync_queue
                    WHERE entity_type = 'document_publish'
                      AND entity_id = $document_id
                      AND local_version_no = $version_no
                    LIMIT 1;
                    """,
                    ("$document_id", uploadedDocument.DocumentId),
                    ("$version_no", offlineVersionDocument.VersionNo)) == ServerSyncService.CreateDocumentPublishIdempotencyKey(uploadedDocument.DocumentId, offlineVersionDocument.VersionNo),
                "document publish sync queue should use the documented idempotency key");
            Require(
                ScalarString(
                    syncConnection,
                    """
                    SELECT idempotency_key
                    FROM server_sync_queue
                    WHERE entity_type = 'document_status'
                      AND entity_id = $document_id
                    LIMIT 1;
                    """,
                    ("$document_id", uploadedDocument.DocumentId)) is { } statusKey &&
                statusKey.StartsWith($"wpf:document-status:{uploadedDocument.DocumentId}:v{offlineArchivedDocument.VersionNo}:ARCHIVED:", StringComparison.Ordinal),
                "document status sync queue should use the documented idempotency key prefix");
            Require(
                ScalarString(
                    syncConnection,
                    """
                    SELECT idempotency_key
                    FROM server_sync_queue
                    WHERE entity_type = 'field_comment' AND entity_id = $comment_id
                    LIMIT 1;
                    """,
                    ("$comment_id", offlineQueuedFieldComment.CommentId)) == ServerSyncService.CreateFieldCommentIdempotencyKey(offlineQueuedFieldComment.CommentId),
                "field comment sync queue should use the documented idempotency key");
            Require(
                ScalarString(
                    syncConnection,
                    """
                    SELECT idempotency_key
                    FROM server_sync_queue
                    WHERE entity_type = 'field_comment_attachment' AND entity_id = $attachment_id
                    LIMIT 1;
                    """,
                    ("$attachment_id", offlineQueuedFieldCommentAttachment.AttachmentId)) == ServerSyncService.CreateFieldCommentAttachmentIdempotencyKey(offlineQueuedFieldCommentAttachment.AttachmentId),
                "field comment attachment sync queue should use the documented idempotency key");
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
            Require(
                ScalarLong(
                    syncConnection,
                    """
                    SELECT COUNT(*)
                    FROM server_id_mappings
                    WHERE local_id = $document_id
                      AND entity_type IN ('document', 'document_version', 'document_publish', 'document_status')
                      AND server_document_id IS NOT NULL
                      AND server_version_id IS NOT NULL;
                    """,
                    ("$document_id", uploadedDocument.DocumentId)) >= 4,
                "server_id_mappings should connect document, version, publish, and status queue results");

            var duplicateQueueCountBefore = ScalarLong(
                syncConnection,
                """
                SELECT COUNT(*)
                FROM server_sync_queue
                WHERE entity_id IN ($document_id, $comment_id, $attachment_id, $log_id);
                """,
                ("$document_id", uploadedDocument.DocumentId),
                ("$comment_id", offlineQueuedFieldComment.CommentId),
                ("$attachment_id", offlineQueuedFieldCommentAttachment.AttachmentId),
                ("$log_id", offlineAccessLogId.ToString()));
            var duplicateAttemptCountBefore = ScalarLong(
                syncConnection,
                """
                SELECT COALESCE(SUM(attempt_count), 0)
                FROM server_sync_queue
                WHERE entity_id IN ($document_id, $comment_id, $attachment_id, $log_id);
                """,
                ("$document_id", uploadedDocument.DocumentId),
                ("$comment_id", offlineQueuedFieldComment.CommentId),
                ("$attachment_id", offlineQueuedFieldCommentAttachment.AttachmentId),
                ("$log_id", offlineAccessLogId.ToString()));
            _ = await services.ServerSync.QueueAndTrySyncDocumentAsync(
                uploadedDocument,
                serverDocuments,
                serverLogin.UserId);
            _ = await services.ServerSync.QueueAndTrySyncDocumentVersionAsync(
                offlineVersionDocument,
                serverDocuments,
                serverLogin.UserId);
            _ = await services.ServerSync.QueueAndTrySyncDocumentPublishAsync(
                offlinePublishedDocument,
                serverDocuments,
                serverLogin.UserId);
            _ = await services.ServerSync.QueueAndTrySyncDocumentStatusAsync(
                offlineArchivedDocument,
                serverDocuments,
                serverLogin.UserId);
            _ = await services.ServerSync.QueueAndTrySyncFieldCommentAsync(
                offlineQueuedFieldComment,
                serverDocuments,
                serverLogin.UserId);
            _ = await services.ServerSync.QueueAndTrySyncFieldCommentAttachmentAsync(
                offlineQueuedFieldCommentAttachment,
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
                WHERE entity_id IN ($document_id, $comment_id, $attachment_id, $log_id);
                """,
                ("$document_id", uploadedDocument.DocumentId),
                ("$comment_id", offlineQueuedFieldComment.CommentId),
                ("$attachment_id", offlineQueuedFieldCommentAttachment.AttachmentId),
                ("$log_id", offlineAccessLogId.ToString()));
            var duplicateAttemptCountAfter = ScalarLong(
                syncConnection,
                """
                SELECT COALESCE(SUM(attempt_count), 0)
                FROM server_sync_queue
                WHERE entity_id IN ($document_id, $comment_id, $attachment_id, $log_id);
                """,
                ("$document_id", uploadedDocument.DocumentId),
                ("$comment_id", offlineQueuedFieldComment.CommentId),
                ("$attachment_id", offlineQueuedFieldCommentAttachment.AttachmentId),
                ("$log_id", offlineAccessLogId.ToString()));
            Require(
                duplicateQueueCountAfter == duplicateQueueCountBefore,
                "already synced queue items should not create duplicate queue rows");
            Require(
                duplicateAttemptCountAfter == duplicateAttemptCountBefore,
                "already synced queue items should not increment retry attempt counts");

            var reviewedQueuedFieldComment = services.FieldComments.UpdateReview(
                offlineQueuedFieldComment.CommentId,
                "서버 재시도 큐가 FieldComment 정리 내용을 PATCH로 반영함.",
                "검토 상태 변경이 서버 field_comments와 AI 준비도 기준에 누적되는지 확인한다.",
                "ANALYZED",
                smokeActorName);
            var queuedReviewSyncResult = await services.ServerSync.QueueAndTrySyncFieldCommentReviewAsync(
                reviewedQueuedFieldComment,
                serverDocuments,
                serverLogin.UserId);
            Require(
                queuedReviewSyncResult.Synced >= 1 || queuedReviewSyncResult.Skipped >= 1 || queuedReviewSyncResult.Attempted >= 1,
                "field comment review queue retry should process at least one queue item after the comment has a server id");
            var reviewedQueuedServerCommentId = ScalarString(
                syncConnection,
                """
                SELECT server_comment_id
                FROM field_comments
                WHERE comment_id = $comment_id
                  AND synced_at IS NOT NULL;
                """,
                ("$comment_id", offlineQueuedFieldComment.CommentId));
            Require(!string.IsNullOrWhiteSpace(reviewedQueuedServerCommentId), "reviewed queued field comment should keep server comment id");
            var reviewedQueuedServerComment = await serverDocuments.GetFieldCommentAsync(reviewedQueuedServerCommentId!);
            Require(reviewedQueuedServerComment.Status == "ANALYZED", "server field comment review patch should update status");
            Require(
                reviewedQueuedServerComment.NormalizedContent == reviewedQueuedFieldComment.NormalizedContent,
                "server field comment review patch should preserve normalized content");
            Require(
                reviewedQueuedServerComment.AnalysisContent == reviewedQueuedFieldComment.AnalysisContent,
                "server field comment review patch should preserve analysis content");
            Require(
                ScalarLong(
                    syncConnection,
                    """
                    SELECT COUNT(*)
                    FROM server_sync_queue
                    WHERE entity_type = 'field_comment_review'
                      AND entity_id = $comment_id
                      AND action = 'update_field_comment_review'
                      AND status = 'SYNCED'
                      AND server_comment_id = $server_comment_id
                      AND synced_at IS NOT NULL;
                    """,
                    ("$comment_id", offlineQueuedFieldComment.CommentId),
                    ("$server_comment_id", reviewedQueuedServerCommentId!)) >= 1,
                "field comment review queue should keep synced PATCH trace with server comment id");

            var serverVersionsBeforeMappingRecovery = await serverDocuments.ListVersionsAsync(syncedServerDocumentId!);
            var existingServerVersion = serverVersionsBeforeMappingRecovery.SingleOrDefault(item =>
                item.VersionNo == offlineVersionDocument.VersionNo);
            Require(existingServerVersion is not null, "server should already have the queued local v2 before mapping recovery");

            ExecuteNonQuery(
                syncConnection,
                """
                UPDATE document_versions
                SET server_version_id = NULL,
                    synced_at = NULL
                WHERE document_id = $document_id
                  AND version_no = $version_no;

                DELETE FROM server_id_mappings
                WHERE entity_type = 'document_version'
                  AND local_id = $document_id
                  AND local_version_no = $version_no;

                UPDATE server_sync_queue
                SET status = 'FAILED',
                    last_error = 'server mapping recovery smoke',
                    synced_at = NULL,
                    server_version_id = NULL
                WHERE entity_type = 'document_version'
                  AND entity_id = $document_id
                  AND local_version_no = $version_no;
                """,
                ("$document_id", uploadedDocument.DocumentId),
                ("$version_no", offlineVersionDocument.VersionNo));

            var mappingRecoveryResult = await services.ServerSync.RetryPendingAsync(serverDocuments, serverLogin.UserId);
            Require(mappingRecoveryResult.Synced >= 1, "mapping recovery retry should sync the local v2 queue row");

            var serverVersionsAfterMappingRecovery = await serverDocuments.ListVersionsAsync(syncedServerDocumentId!);
            Require(
                serverVersionsAfterMappingRecovery.Count == serverVersionsBeforeMappingRecovery.Count,
                "mapping recovery should not upload a duplicate server version");
            Require(
                serverVersionsAfterMappingRecovery.Count(item => item.VersionNo == offlineVersionDocument.VersionNo) == 1,
                "mapping recovery should keep exactly one server v2");
            Require(
                ScalarString(
                    syncConnection,
                    """
                    SELECT server_version_id
                    FROM document_versions
                    WHERE document_id = $document_id
                      AND version_no = $version_no
                      AND synced_at IS NOT NULL;
                    """,
                    ("$document_id", uploadedDocument.DocumentId),
                    ("$version_no", offlineVersionDocument.VersionNo)) == existingServerVersion!.VersionId,
                "mapping recovery should restore the local document_versions server_version_id");
            Require(
                ScalarLong(
                    syncConnection,
                    """
                    SELECT COUNT(*)
                    FROM server_id_mappings
                    WHERE entity_type = 'document_version'
                      AND local_id = $document_id
                      AND local_version_no = $version_no
                      AND server_document_id = $server_document_id
                      AND server_version_id = $server_version_id
                      AND synced_at IS NOT NULL;
                    """,
                    ("$document_id", uploadedDocument.DocumentId),
                    ("$version_no", offlineVersionDocument.VersionNo),
                    ("$server_document_id", syncedServerDocumentId!),
                    ("$server_version_id", existingServerVersion.VersionId)) == 1,
                "mapping recovery should restore server_id_mappings for the already existing server version");
            Require(
                ScalarLong(
                    syncConnection,
                    """
                    SELECT COUNT(*)
                    FROM server_sync_queue
                    WHERE entity_type = 'document_version'
                      AND entity_id = $document_id
                      AND local_version_no = $version_no
                      AND status = 'SYNCED'
                      AND server_version_id = $server_version_id;
                    """,
                    ("$document_id", uploadedDocument.DocumentId),
                    ("$version_no", offlineVersionDocument.VersionNo),
                    ("$server_version_id", existingServerVersion.VersionId)) == 1,
                "mapping recovery should mark the document version queue row synced with the recovered server version id");

            var dependencyDocumentFile = Path.Combine(testDirectory, $"server-dependency-document-{runId}.txt");
            File.WriteAllText(dependencyDocumentFile, $"Server dependency document smoke test {runId}.");
            var versionDependencyDocument = services.Documents.RegisterDocument(
                currentDocumentFolder.Id,
                $"server-dependency-document-{runId}",
                Path.GetFileName(dependencyDocumentFile),
                "Text",
                smokeActorName,
                dependencyDocumentFile);
            var versionDependencyFile = Path.Combine(testDirectory, $"server-dependency-document-v2-{runId}.txt");
            File.WriteAllText(versionDependencyFile, $"Server dependency document smoke test v2 {runId}.");
            var versionDependencyVersion = services.Documents.AddFileVersion(
                versionDependencyDocument.DocumentId,
                Path.GetFileName(versionDependencyFile),
                versionDependencyFile,
                "v2",
                "Dependency failure smoke version.",
                smokeActorName);
            var versionDependencyResult = await services.ServerSync.QueueAndTrySyncDocumentVersionAsync(
                versionDependencyVersion,
                serverDocuments,
                serverLogin.UserId);
            Require(!versionDependencyResult.Success, "version sync should fail while the first document sync is missing");
            Require(versionDependencyResult.Held >= 1, "version dependency should be counted as a held queue item");
            var versionDependencyError = ScalarString(
                syncConnection,
                """
                SELECT last_error
                FROM server_sync_queue
                WHERE entity_type = 'document_version'
                  AND entity_id = $document_id
                  AND local_version_no = $version_no
                ORDER BY id DESC
                LIMIT 1;
                """,
                ("$document_id", versionDependencyDocument.DocumentId),
                ("$version_no", versionDependencyVersion.VersionNo));
            Require(
                versionDependencyError?.Contains("선행 문서가 아직 서버에 전송되지 않았습니다", StringComparison.Ordinal) == true,
                "version dependency failure should remain in the queue with a Korean reason");
            Require(
                ScalarLong(
                    syncConnection,
                    """
                    SELECT attempt_count
                    FROM server_sync_queue
                    WHERE entity_type = 'document_version'
                      AND entity_id = $document_id
                      AND local_version_no = $version_no
                    ORDER BY id DESC
                    LIMIT 1;
                    """,
                    ("$document_id", versionDependencyDocument.DocumentId),
                    ("$version_no", versionDependencyVersion.VersionNo)) == 0,
                "held version dependency should not increment retry attempt count before the document is synced");
            Require(
                ScalarString(
                    syncConnection,
                    """
                    SELECT message
                    FROM activity_history
                    WHERE event_type = 'server_sync.failed'
                      AND target_type = 'document_version'
                      AND target_id = $document_id
                    ORDER BY id DESC
                    LIMIT 1;
                    """,
                    ("$document_id", versionDependencyDocument.DocumentId)) == versionDependencyError,
                "version dependency queue error should match activity_history");
            _ = await services.ServerSync.QueueAndTrySyncDocumentAsync(
                versionDependencyDocument,
                serverDocuments,
                serverLogin.UserId);
            _ = await services.ServerSync.RetryPendingAsync(serverDocuments, serverLogin.UserId);
            Require(
                ScalarLong(
                    syncConnection,
                    """
                    SELECT COUNT(*)
                    FROM server_sync_queue
                    WHERE entity_id = $document_id
                      AND entity_type IN ('document', 'document_version')
                      AND status = 'SYNCED';
                    """,
                    ("$document_id", versionDependencyDocument.DocumentId)) == 2,
                "version dependency retry should sync both document and version queue rows after the document exists on the server");

            var publishDependencyDocumentFile = Path.Combine(testDirectory, $"server-publish-dependency-{runId}.txt");
            File.WriteAllText(publishDependencyDocumentFile, $"Server publish dependency smoke test {runId}.");
            var publishDependencyDocument = services.Documents.RegisterDocument(
                currentDocumentFolder.Id,
                $"server-publish-dependency-{runId}",
                Path.GetFileName(publishDependencyDocumentFile),
                "Text",
                smokeActorName,
                publishDependencyDocumentFile);
            _ = await services.ServerSync.QueueAndTrySyncDocumentAsync(
                publishDependencyDocument,
                serverDocuments,
                serverLogin.UserId);
            var publishDependencyVersionFile = Path.Combine(testDirectory, $"server-publish-dependency-v2-{runId}.txt");
            File.WriteAllText(publishDependencyVersionFile, $"Server publish dependency smoke test v2 {runId}.");
            var publishDependencyVersion = services.Documents.AddFileVersion(
                publishDependencyDocument.DocumentId,
                Path.GetFileName(publishDependencyVersionFile),
                publishDependencyVersionFile,
                "v2",
                "Publish dependency smoke version.",
                smokeActorName);
            var publishDependencyPublished = services.Documents.PublishVersion(
                publishDependencyDocument.DocumentId,
                publishDependencyVersion.VersionNo,
                smokeActorName);
            var publishDependencyResult = await services.ServerSync.QueueAndTrySyncDocumentPublishAsync(
                publishDependencyPublished,
                serverDocuments,
                serverLogin.UserId);
            Require(!publishDependencyResult.Success, "publish sync should fail until the published local version has a server version id");
            Require(publishDependencyResult.Held >= 1, "publish dependency should be counted as a held queue item");
            var publishDependencyError = ScalarString(
                syncConnection,
                """
                SELECT last_error
                FROM server_sync_queue
                WHERE entity_type = 'document_publish'
                  AND entity_id = $document_id
                  AND local_version_no = $version_no
                ORDER BY id DESC
                LIMIT 1;
                """,
                ("$document_id", publishDependencyDocument.DocumentId),
                ("$version_no", publishDependencyVersion.VersionNo));
            Require(
                publishDependencyError?.Contains("공개할 서버 버전 ID가 아직 확인되지 않아", StringComparison.Ordinal) == true,
                "publish dependency failure should explain the missing server version id in Korean");
            var publishDependencyQueue = services.ServerSync.ListQueueItems().First(item =>
                item.EntityType == "document_publish" &&
                item.EntityId == publishDependencyDocument.DocumentId &&
                item.LocalVersionNo == publishDependencyVersion.VersionNo);
            Require(
                publishDependencyQueue.Diagnosis.Category == "선행 문서 버전 미동기화" &&
                publishDependencyQueue.Diagnosis.IsDependencyHold,
                "publish dependency queue should expose a document version dependency diagnosis");
            Require(
                ScalarString(
                    syncConnection,
                    """
                    SELECT message
                    FROM activity_history
                    WHERE event_type = 'server_sync.failed'
                      AND target_type = 'document_publish'
                      AND target_id = $document_id
                    ORDER BY id DESC
                    LIMIT 1;
                    """,
                    ("$document_id", publishDependencyDocument.DocumentId)) == publishDependencyError,
                "publish dependency queue error should match activity_history");
            _ = await services.ServerSync.QueueAndTrySyncDocumentVersionAsync(
                publishDependencyVersion,
                serverDocuments,
                serverLogin.UserId);
            _ = await services.ServerSync.RetryPendingAsync(serverDocuments, serverLogin.UserId);
            Require(
                ScalarLong(
                    syncConnection,
                    """
                    SELECT COUNT(*)
                    FROM server_sync_queue
                    WHERE entity_type = 'document_publish'
                      AND entity_id = $document_id
                      AND local_version_no = $version_no
                      AND status = 'SYNCED'
                      AND server_version_id IS NOT NULL;
                    """,
                    ("$document_id", publishDependencyDocument.DocumentId),
                    ("$version_no", publishDependencyVersion.VersionNo)) == 1,
                "publish dependency retry should sync after the version queue has recovered the server version id");

            var statusNoVersionFile = Path.Combine(testDirectory, $"server-status-no-published-version-{runId}.txt");
            File.WriteAllText(statusNoVersionFile, $"Server status missing published version smoke test {runId}.");
            var statusNoVersionDocument = services.Documents.RegisterDocument(
                currentDocumentFolder.Id,
                $"server-status-no-published-version-{runId}",
                Path.GetFileName(statusNoVersionFile),
                "Text",
                smokeActorName,
                statusNoVersionFile);
            _ = await services.ServerSync.QueueAndTrySyncDocumentAsync(
                statusNoVersionDocument,
                serverDocuments,
                serverLogin.UserId);
            var statusNoVersionUpdatedAt = DateTime.UtcNow;
            ExecuteNonQuery(
                syncConnection,
                """
                UPDATE documents
                SET status = 'PUBLISHED',
                    published_version_no = NULL,
                    updated_at = $updated_at
                WHERE document_id = $document_id;
                """,
                ("$document_id", statusNoVersionDocument.DocumentId),
                ("$updated_at", statusNoVersionUpdatedAt.ToString("O")));
            var statusNoVersionResult = await services.ServerSync.QueueAndTrySyncDocumentStatusAsync(
                statusNoVersionDocument with
                {
                    Status = "PUBLISHED",
                    PublishedVersionNo = null,
                    UpdatedAt = statusNoVersionUpdatedAt
                },
                serverDocuments,
                serverLogin.UserId);
            Require(!statusNoVersionResult.Success, "PUBLISHED status sync should fail when no local published version is selected");
            var statusNoVersionError = ScalarString(
                syncConnection,
                """
                SELECT last_error
                FROM server_sync_queue
                WHERE entity_type = 'document_status'
                  AND entity_id = $document_id
                ORDER BY id DESC
                LIMIT 1;
                """,
                ("$document_id", statusNoVersionDocument.DocumentId));
            Require(
                statusNoVersionError?.Contains("로컬 공개 버전이 지정되지 않았습니다", StringComparison.Ordinal) == true,
                "PUBLISHED status without a local published version should remain in the queue with a Korean reason");
            ExecuteNonQuery(
                syncConnection,
                """
                UPDATE documents
                SET published_version_no = 1
                WHERE document_id = $document_id;
                """,
                ("$document_id", statusNoVersionDocument.DocumentId));
            _ = await services.ServerSync.QueueAndTrySyncDocumentPublishAsync(
                statusNoVersionDocument with
                {
                    Status = "PUBLISHED",
                    PublishedVersionNo = 1,
                    UpdatedAt = statusNoVersionUpdatedAt
                },
                serverDocuments,
                serverLogin.UserId);
            _ = await services.ServerSync.RetryPendingAsync(serverDocuments, serverLogin.UserId);
            Require(
                ScalarLong(
                    syncConnection,
                    """
                    SELECT COUNT(*)
                    FROM server_sync_queue
                    WHERE entity_id = $document_id
                      AND entity_type IN ('document_publish', 'document_status')
                      AND status = 'SYNCED';
                    """,
                    ("$document_id", statusNoVersionDocument.DocumentId)) == 2,
                "PUBLISHED status without version should sync after selecting a published version and syncing publish first");

            var statusNoPublishMappingFile = Path.Combine(testDirectory, $"server-status-no-publish-mapping-{runId}.txt");
            File.WriteAllText(statusNoPublishMappingFile, $"Server status missing publish mapping smoke test {runId}.");
            var statusNoPublishMappingDocument = services.Documents.RegisterDocument(
                currentDocumentFolder.Id,
                $"server-status-no-publish-mapping-{runId}",
                Path.GetFileName(statusNoPublishMappingFile),
                "Text",
                smokeActorName,
                statusNoPublishMappingFile);
            _ = await services.ServerSync.QueueAndTrySyncDocumentAsync(
                statusNoPublishMappingDocument,
                serverDocuments,
                serverLogin.UserId);
            var statusNoPublishMappingUpdatedAt = DateTime.UtcNow;
            ExecuteNonQuery(
                syncConnection,
                """
                UPDATE documents
                SET status = 'PUBLISHED',
                    published_version_no = 1,
                    updated_at = $updated_at
                WHERE document_id = $document_id;
                """,
                ("$document_id", statusNoPublishMappingDocument.DocumentId),
                ("$updated_at", statusNoPublishMappingUpdatedAt.ToString("O")));
            var statusNoPublishMappingResult = await services.ServerSync.QueueAndTrySyncDocumentStatusAsync(
                statusNoPublishMappingDocument with
                {
                    Status = "PUBLISHED",
                    PublishedVersionNo = 1,
                    UpdatedAt = statusNoPublishMappingUpdatedAt
                },
                serverDocuments,
                serverLogin.UserId);
            Require(!statusNoPublishMappingResult.Success, "PUBLISHED status sync should fail until the publish queue has a server mapping");
            var statusNoPublishMappingError = ScalarString(
                syncConnection,
                """
                SELECT last_error
                FROM server_sync_queue
                WHERE entity_type = 'document_status'
                  AND entity_id = $document_id
                ORDER BY id DESC
                LIMIT 1;
                """,
                ("$document_id", statusNoPublishMappingDocument.DocumentId));
            Require(
                statusNoPublishMappingError?.Contains("공개 버전의 서버 매핑이 없습니다", StringComparison.Ordinal) == true,
                "PUBLISHED status without a publish mapping should remain in the queue with a Korean reason");
            Require(
                ScalarString(
                    syncConnection,
                    """
                    SELECT message
                    FROM activity_history
                    WHERE event_type = 'server_sync.failed'
                      AND target_type = 'document_status'
                      AND target_id = $document_id
                    ORDER BY id DESC
                    LIMIT 1;
                    """,
                    ("$document_id", statusNoPublishMappingDocument.DocumentId)) == statusNoPublishMappingError,
                "PUBLISHED status queue error should match activity_history");
            _ = await services.ServerSync.QueueAndTrySyncDocumentPublishAsync(
                statusNoPublishMappingDocument with
                {
                    Status = "PUBLISHED",
                    PublishedVersionNo = 1,
                    UpdatedAt = statusNoPublishMappingUpdatedAt
                },
                serverDocuments,
                serverLogin.UserId);
            _ = await services.ServerSync.RetryPendingAsync(serverDocuments, serverLogin.UserId);
            Require(
                ScalarLong(
                    syncConnection,
                    """
                    SELECT COUNT(*)
                    FROM server_sync_queue
                    WHERE entity_id = $document_id
                      AND entity_type IN ('document_publish', 'document_status')
                      AND status = 'SYNCED';
                    """,
                    ("$document_id", statusNoPublishMappingDocument.DocumentId)) == 2,
                "PUBLISHED status retry should sync after the publish queue has restored the server mapping");

            var orderedQueueFile = Path.Combine(testDirectory, $"server-ordered-document-{runId}.txt");
            File.WriteAllText(orderedQueueFile, $"Server ordered queue smoke test {runId}.");
            var orderedQueueDocument = services.Documents.RegisterDocument(
                currentDocumentFolder.Id,
                $"server-ordered-document-{runId}",
                Path.GetFileName(orderedQueueFile),
                "Text",
                smokeActorName,
                orderedQueueFile);
            var orderedQueueVersionFile = Path.Combine(testDirectory, $"server-ordered-document-v2-{runId}.txt");
            File.WriteAllText(orderedQueueVersionFile, $"Server ordered queue smoke test v2 {runId}.");
            var orderedQueueVersion = services.Documents.AddFileVersion(
                orderedQueueDocument.DocumentId,
                Path.GetFileName(orderedQueueVersionFile),
                orderedQueueVersionFile,
                "v2",
                "Ordered retry smoke version.",
                smokeActorName);
            var orderedQueuePublished = services.Documents.PublishVersion(
                orderedQueueDocument.DocumentId,
                orderedQueueVersion.VersionNo,
                smokeActorName);
            var orderedQueueArchived = services.Documents.UpdateDocumentStatus(
                orderedQueueDocument.DocumentId,
                "ARCHIVED",
                smokeActorName);
            var orderedQueueFieldComment = services.FieldComments.AddDocumentComment(
                orderedQueueDocument.DocumentId,
                $"Ordered retry field comment {runId}.",
                smokeActorName);
            var orderedQueueAttachmentFile = Path.Combine(testDirectory, $"server-ordered-field-comment-attachment-{runId}.txt");
            File.WriteAllText(orderedQueueAttachmentFile, $"Server ordered FieldComment attachment smoke test {runId}.");
            var orderedQueueAttachment = services.FieldComments.AddAttachment(
                orderedQueueFieldComment.CommentId,
                orderedQueueAttachmentFile,
                smokeActorName,
                "Ordered retry FieldComment attachment");
            var orderedQueueAccessLogId = services.DocumentViewLogs.StartDocumentView(
                orderedQueueDocument.DocumentId,
                orderedQueueDocument.VersionNo,
                smokeActorName);
            var orderedQueueStartedAccessLog = services.DocumentViewLogs.GetLog(orderedQueueAccessLogId)
                ?? throw new InvalidOperationException("ordered access log should be readable after start");
            services.DocumentViewLogs.CloseDocumentView(orderedQueueAccessLogId, "window_closed");
            var orderedQueueClosedAccessLog = services.DocumentViewLogs.GetLog(orderedQueueAccessLogId)
                ?? throw new InvalidOperationException("ordered access log should be readable after close");
            var orderedReportSources = new[]
            {
                new ReportSourceCandidateRecord(
                    "FIELD_COMMENT",
                    orderedQueueFieldComment.CommentId,
                    orderedQueueDocument.Title,
                    orderedQueueFieldComment.RawContent,
                    orderedQueueFieldComment.CreatedAt,
                    RelationType: "primary"),
                new ReportSourceCandidateRecord(
                    "DOCUMENT",
                    orderedQueueDocument.DocumentId,
                    orderedQueueDocument.Title,
                    orderedQueueDocument.FileName,
                    orderedQueueDocument.UpdatedAt,
                    orderedQueueVersion.VersionNo.ToString(CultureInfo.InvariantCulture),
                    "related_document")
            };
            var orderedReportContent = services.Reports.BuildDraftContent(
                $"Server ordered retry report {runStamp}",
                "Server retry should save the report only after document and FieldComment sources are synced.",
                orderedReportSources,
                smokeActorName);
            var orderedReportDocument = services.Reports.SaveDraftAsDocument(
                currentDocumentFolder.Id,
                $"Server ordered retry report {runStamp}",
                orderedReportContent,
                smokeActorName,
                orderedReportSources,
                "Server retry should save the report only after document and FieldComment sources are synced.");

            _ = await services.ServerSync.QueueAndTrySyncReportAsync(orderedReportDocument, null);
            _ = await services.ServerSync.QueueAndTrySyncAccessLogAsync(orderedQueueClosedAccessLog, "view_closed", null);
            _ = await services.ServerSync.QueueAndTrySyncAccessLogAsync(orderedQueueStartedAccessLog, "view_started", null);
            _ = await services.ServerSync.QueueAndTrySyncFieldCommentAttachmentAsync(orderedQueueAttachment, null);
            _ = await services.ServerSync.QueueAndTrySyncFieldCommentAsync(orderedQueueFieldComment, null);
            _ = await services.ServerSync.QueueAndTrySyncDocumentStatusAsync(orderedQueueArchived, null);
            _ = await services.ServerSync.QueueAndTrySyncDocumentPublishAsync(orderedQueuePublished, null);
            _ = await services.ServerSync.QueueAndTrySyncDocumentVersionAsync(orderedQueueVersion, null);
            _ = await services.ServerSync.QueueAndTrySyncDocumentAsync(orderedQueueDocument, null);

            var orderedRetryStartedAt = DateTime.UtcNow;
            var orderedRetryResult = await services.ServerSync.RetryPendingAsync(serverDocuments, serverLogin.UserId);
            Require(orderedRetryResult.Synced >= 9, "document queue retry should process the reverse-queued document, FieldComment, access log, and report flow");
            Require(
                ScalarLong(
                    syncConnection,
                    """
                    SELECT COUNT(*)
                    FROM server_sync_queue
                    WHERE entity_id = $document_id
                      AND entity_type IN ('document', 'document_version', 'document_publish', 'document_status')
                      AND status = 'SYNCED'
                      AND attempt_count >= 1
                      AND last_attempt_at IS NOT NULL
                      AND synced_at IS NOT NULL;
                    """,
                    ("$document_id", orderedQueueDocument.DocumentId)) == 4,
                "document, version, publish, and status queue rows should keep attempts and sync timestamps");
            Require(
                ScalarLong(
                    syncConnection,
                    """
                    SELECT COUNT(*)
                    FROM server_sync_queue
                    WHERE (
                        (
                            entity_id = $document_id
                            AND entity_type IN ('document', 'document_version', 'document_publish', 'document_status')
                        )
                        OR (entity_type = 'field_comment' AND entity_id = $comment_id)
                        OR (entity_type = 'field_comment_attachment' AND entity_id = $attachment_id)
                        OR (entity_type = 'document_access_log' AND entity_id = $log_id)
                        OR (entity_type = 'report' AND entity_id = $report_id)
                    )
                      AND status = 'SYNCED';
                    """,
                    ("$document_id", orderedQueueDocument.DocumentId),
                    ("$comment_id", orderedQueueFieldComment.CommentId),
                    ("$attachment_id", orderedQueueAttachment.AttachmentId),
                    ("$log_id", orderedQueueAccessLogId.ToString()),
                    ("$report_id", orderedReportDocument.DocumentId)) == 9,
                "full ordered retry should mark document, version, publish, status, FieldComment, attachment, access logs, and report as synced");

            var orderedAttemptOrder = ScalarString(
                syncConnection,
                """
                SELECT GROUP_CONCAT(entity_type || ':' || action, '|')
                FROM (
                    SELECT server_sync_queue.entity_type AS entity_type,
                           server_sync_queue.action AS action
                    FROM activity_history
                    JOIN server_sync_queue
                      ON server_sync_queue.entity_type = activity_history.target_type
                     AND server_sync_queue.entity_id = activity_history.target_id
                     AND activity_history.message LIKE '%' || server_sync_queue.idempotency_key || '%'
                    WHERE activity_history.event_type = 'server_sync.retry_attempted'
                      AND activity_history.created_at >= $ordered_retry_started_at
                      AND (
                            activity_history.target_id = $document_id
                         OR activity_history.target_id = $comment_id
                         OR activity_history.target_id = $attachment_id
                         OR activity_history.target_id = $log_id
                         OR activity_history.target_id = $report_id
                      )
                    ORDER BY activity_history.id
                );
                """,
                ("$document_id", orderedQueueDocument.DocumentId),
                ("$comment_id", orderedQueueFieldComment.CommentId),
                ("$attachment_id", orderedQueueAttachment.AttachmentId),
                ("$log_id", orderedQueueAccessLogId.ToString()),
                ("$report_id", orderedReportDocument.DocumentId),
                ("$ordered_retry_started_at", orderedRetryStartedAt.ToString("O")));
            Require(
                orderedAttemptOrder ==
                    "document:register_document|" +
                    "document_version:register_document_version|" +
                    "document_publish:publish_document_version|" +
                    "document_status:update_document_status|" +
                    "field_comment:register_field_comment|" +
                    "field_comment_attachment:register_field_comment_attachment|" +
                    "document_access_log:register_access_log_started|" +
                    "document_access_log:register_access_log_closed|" +
                    "report:register_report",
                "full queue retry attempts should run document, version, publish, status, FieldComment, attachment, access logs, then report");
            Require(
                ScalarLong(
                    syncConnection,
                    """
                    SELECT COUNT(*)
                    FROM field_comments
                    WHERE comment_id = $comment_id
                      AND server_comment_id IS NOT NULL
                      AND synced_at IS NOT NULL;
                    """,
                    ("$comment_id", orderedQueueFieldComment.CommentId)) == 1,
                "ordered FieldComment retry should store the server comment id before report sync");
            Require(
                ScalarLong(
                    syncConnection,
                    """
                    SELECT COUNT(*)
                    FROM field_comment_attachments
                    WHERE attachment_id = $attachment_id
                      AND server_attachment_id IS NOT NULL
                      AND synced_at IS NOT NULL;
                    """,
                    ("$attachment_id", orderedQueueAttachment.AttachmentId)) == 1,
                "ordered FieldComment attachment retry should store the server attachment id");
            Require(
                ScalarLong(
                    syncConnection,
                    """
                    SELECT COUNT(*)
                    FROM document_view_logs
                    WHERE id = $log_id
                      AND server_start_log_id IS NOT NULL
                      AND server_close_log_id IS NOT NULL
                      AND synced_at IS NOT NULL;
                    """,
                    ("$log_id", orderedQueueAccessLogId)) == 1,
                "ordered access log retry should store both server access log ids");
            var orderedReportServerId = ScalarString(
                syncConnection,
                """
                SELECT server_report_id
                FROM documents
                WHERE document_id = $report_id
                  AND server_report_id IS NOT NULL
                  AND server_document_id IS NOT NULL
                  AND synced_at IS NOT NULL;
                """,
                ("$report_id", orderedReportDocument.DocumentId));
            Require(
                orderedReportServerId?.StartsWith("report_", StringComparison.Ordinal) == true,
                "ordered report retry should link the local report document to a server report id");
            var orderedServerDocumentId = ScalarString(
                syncConnection,
                """
                SELECT server_document_id
                FROM documents
                WHERE document_id = $document_id;
                """,
                ("$document_id", orderedQueueDocument.DocumentId));
            var orderedReportDetail = await serverDocuments.GetReportAsync(orderedReportServerId!);
            var orderedServerCommentId = ScalarString(
                syncConnection,
                """
                SELECT server_comment_id
                FROM field_comments
                WHERE comment_id = $comment_id;
                """,
                ("$comment_id", orderedQueueFieldComment.CommentId));
            Require(
                orderedReportDetail.Sources.Any(item => item.SourceType == "FIELD_COMMENT" && item.SourceId == orderedServerCommentId),
                "ordered report retry should trace the synced server FieldComment source");
            Require(
                orderedReportDetail.Sources.Any(item => item.SourceType == "DOCUMENT" && item.SourceId == orderedServerDocumentId),
                "ordered report retry should trace the synced server document source");
            Require(
                ScalarLong(
                    syncConnection,
                    """
                    SELECT COUNT(*)
                    FROM (
                        SELECT entity_type, local_id, local_version_no, COUNT(*) AS mapping_count
                        FROM server_id_mappings
                        WHERE local_id IN ($document_id, $comment_id, $attachment_id, $log_id, $report_id)
                        GROUP BY entity_type, local_id, local_version_no
                        HAVING mapping_count > 1
                    );
                    """,
                    ("$document_id", orderedQueueDocument.DocumentId),
                    ("$comment_id", orderedQueueFieldComment.CommentId),
                    ("$attachment_id", orderedQueueAttachment.AttachmentId),
                    ("$log_id", orderedQueueAccessLogId.ToString()),
                    ("$report_id", orderedReportDocument.DocumentId)) == 0,
                "ordered retry should not create duplicate server_id_mappings rows");
            var orderedQueuedReportCountBeforeDuplicateRetry = (await serverDocuments.ListReportsAsync())
                .Count(item => item.Title == orderedReportDocument.Title);
            _ = await services.ServerSync.QueueAndTrySyncReportAsync(
                orderedReportDocument,
                serverDocuments,
                serverLogin.UserId);
            var orderedQueuedReportCountAfterDuplicateRetry = (await serverDocuments.ListReportsAsync())
                .Count(item => item.Title == orderedReportDocument.Title);
            Require(
                orderedQueuedReportCountAfterDuplicateRetry == orderedQueuedReportCountBeforeDuplicateRetry,
                "repeated ordered report retry should not create a duplicate server report");

            var orderedDocumentAttemptOrder = ScalarString(
                syncConnection,
                """
                SELECT GROUP_CONCAT(action, '|')
                FROM (
                    SELECT server_sync_queue.action AS action
                    FROM activity_history
                    JOIN server_sync_queue
                      ON server_sync_queue.entity_type = activity_history.target_type
                     AND server_sync_queue.entity_id = activity_history.target_id
                     AND activity_history.message LIKE '%' || server_sync_queue.idempotency_key || '%'
                    WHERE activity_history.event_type = 'server_sync.retry_attempted'
                      AND activity_history.target_id = $document_id
                      AND activity_history.created_at >= $ordered_retry_started_at
                    ORDER BY activity_history.id
                    LIMIT 4
                );
                """,
                ("$document_id", orderedQueueDocument.DocumentId),
                ("$ordered_retry_started_at", orderedRetryStartedAt.ToString("O")));
            Require(
                orderedDocumentAttemptOrder == "register_document|register_document_version|publish_document_version|update_document_status",
                "document queue retry attempts should run document, version, publish, then status");

            var orderedServerVersionId = ScalarString(
                syncConnection,
                """
                SELECT server_version_id
                FROM document_versions
                WHERE document_id = $document_id
                  AND version_no = $version_no;
                """,
                ("$document_id", orderedQueueDocument.DocumentId),
                ("$version_no", orderedQueueVersion.VersionNo));
            Require(
                ScalarLong(
                    syncConnection,
                    """
                    SELECT COUNT(*)
                    FROM server_id_mappings
                    WHERE local_id = $document_id
                      AND local_version_no = $version_no
                      AND entity_type IN ('document_version', 'document_publish')
                      AND server_document_id = $server_document_id
                      AND server_version_id = $server_version_id;
                    """,
                    ("$document_id", orderedQueueDocument.DocumentId),
                    ("$version_no", orderedQueueVersion.VersionNo),
                    ("$server_document_id", orderedServerDocumentId!),
                    ("$server_version_id", orderedServerVersionId!)) == 2,
                "server_id_mappings should trace the local v2 version and published version to the same server ids");
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
            var serverFieldComment = await serverDocuments.RegisterFieldCommentAsync(
                fieldComment,
                documentId: serverDocument.DocumentId,
                documentVersionId: latestServerVersion.VersionId);
            Require(!string.IsNullOrWhiteSpace(serverFieldComment.CommentId), "server field comment should receive an id");
            Require(serverFieldComment.DocumentId == serverDocument.DocumentId, "server field comment should reference the uploaded document");
            Require(
                serverFieldComment.DocumentVersionId == latestServerVersion.VersionId,
                "server field comment should reference the uploaded document version");
            Require(
                serverFieldComment.RawContent == "Program test field comment stored separately from document versions.",
                "server field comment should preserve raw content");
            Require(serverFieldComment.Status == "NEW", "server field comment should start in NEW status");
            var serverFieldCommentAttachment = await serverDocuments.RegisterFieldCommentAttachmentAsync(
                serverFieldComment.CommentId,
                fieldCommentAttachmentFile,
                caption: "Windows smoke FieldComment attachment",
                createdBy: serverLogin.UserId);
            Require(!string.IsNullOrWhiteSpace(serverFieldCommentAttachment.AttachmentId), "server field comment attachment should receive an id");
            Require(serverFieldCommentAttachment.CommentId == serverFieldComment.CommentId, "server field comment attachment should reference the note");
            Require(
                serverFieldCommentAttachment.File.OriginalFilename == Path.GetFileName(fieldCommentAttachmentFile),
                "server field comment attachment should preserve the original filename");
            Require(
                serverFieldCommentAttachment.File.SizeBytes == new FileInfo(fieldCommentAttachmentFile).Length,
                "server field comment attachment should preserve the file size");
            Require(
                !string.IsNullOrWhiteSpace(serverFieldCommentAttachment.File.HashSha256),
                "server field comment attachment should store a file hash");
            var serverFieldCommentAttachments = await serverDocuments.ListFieldCommentAttachmentsAsync(serverFieldComment.CommentId);
            Require(
                serverFieldCommentAttachments.Any(item => item.AttachmentId == serverFieldCommentAttachment.AttachmentId),
                "server field comment attachment list should include the uploaded attachment");

            var reportSequenceBoard = await serverDocuments.CreateWorkSequenceBoardAsync(
                new ServerWorkSequenceBoardCreateRequest
                {
                    Title = $"Server report source sequence {runStamp}",
                    LineCode = "line-a",
                    BoardDate = DateOnly.FromDateTime(DateTime.Today),
                    CreatedBy = serverLogin.UserId
                });
            var reportSequenceWithItem = await serverDocuments.AddWorkSequenceItemAsync(
                reportSequenceBoard.BoardId,
                new ServerWorkSequenceItemCreateRequest
                {
                    Title = $"Server report source item {runStamp}",
                    DocumentId = serverDocument.DocumentId,
                    CreatedBy = serverLogin.UserId
                });
            var reportSequenceItem = reportSequenceWithItem.Items.Single();
            var reportSequenceHistory = await serverDocuments.ListWorkSequenceHistoryAsync(reportSequenceBoard.BoardId);
            var reportSequenceHistorySource = reportSequenceHistory.First(item => item.ItemId == reportSequenceItem.ItemId);

            var reportSources = new[]
            {
                new ReportSourceCandidateRecord(
                    "FIELD_COMMENT",
                    serverFieldComment.CommentId,
                    serverDocument.Title,
                    serverFieldComment.RawContent,
                    serverFieldComment.CreatedAt,
                    RelationType: "primary"),
                new ReportSourceCandidateRecord(
                    "DOCUMENT",
                    serverDocument.DocumentId,
                    serverDocument.Title,
                    serverDocument.LatestVersion?.File.OriginalFilename ?? serverDocument.Title,
                    serverDocument.UpdatedAt,
                    latestServerVersion.VersionId,
                    "related_document"),
                new ReportSourceCandidateRecord(
                    "WORK_SEQUENCE_ITEM",
                    reportSequenceItem.ItemId,
                    reportSequenceItem.Title,
                    reportSequenceItem.Status,
                    reportSequenceItem.CreatedAt,
                    RelationType: "work_sequence"),
                new ReportSourceCandidateRecord(
                    "WORK_SEQUENCE_HISTORY",
                    reportSequenceHistorySource.ChangeId,
                    reportSequenceItem.Title,
                    reportSequenceHistorySource.ChangeType,
                    reportSequenceHistorySource.CreatedAt,
                    RelationType: "work_sequence_history")
            };
            var reportContent = services.Reports.BuildDraftContent(
                $"Windows server report {runStamp}",
                "Windows smoke grouped FieldComment, document, and work sequence history.",
                reportSources,
                smokeActorName);
            var reportResult = await services.Reports.SaveDraftToServerAsync(
                serverDocuments,
                currentDocumentFolder.Id,
                $"Windows server report {runStamp}",
                "Windows smoke grouped FieldComment, document, and work sequence history.",
                reportContent,
                reportSources,
                smokeActorName);
            Require(
                reportResult.ReportId?.StartsWith("report_", StringComparison.Ordinal) == true,
                "server report save should return report_id");
            Require(
                reportResult.GeneratedDocumentId?.StartsWith("doc_", StringComparison.Ordinal) == true,
                "server report save should return generated_document_id");
            Require(reportResult.SkippedSources.Count == 0, "server report save should map all server report sources");
            var reportId = reportResult.ReportId!;

            var savedReportDetail = await serverDocuments.GetReportAsync(reportId);
            Require(savedReportDetail.GeneratedDocumentId == reportResult.GeneratedDocumentId, "server report detail should keep generated document id");
            Require(
                savedReportDetail.Sources.Any(item => item.SourceType == "FIELD_COMMENT" && item.SourceId == serverFieldComment.CommentId),
                "server report detail should trace the FieldComment source");
            Require(
                savedReportDetail.Sources.Any(item => item.SourceType == "DOCUMENT" && item.SourceVersionId == latestServerVersion.VersionId),
                "server report detail should trace the document version source");
            Require(
                savedReportDetail.Sources.Any(item => item.SourceType == "WORK_SEQUENCE_HISTORY" && item.SourceId == reportSequenceHistorySource.ChangeId),
                "server report detail should trace the work sequence history source");
            var reportList = await serverDocuments.ListReportsAsync();
            Require(reportList.Any(item => item.ReportId == reportId), "server report list should include the saved report");
            var reportDocumentList = await serverDocuments.ListDocumentsAsync();
            Require(
                reportDocumentList.Any(item =>
                    item.DocumentId == reportResult.GeneratedDocumentId &&
                    item.DocumentType == "report" &&
                    item.Tags.Contains("Report") &&
                    item.Tags.Contains("FieldComment") &&
                    item.Tags.Contains("Document") &&
                    item.Tags.Contains("WorkSequence")),
                "server document list should include generated report document tags");

            using var reportConnection = services.Database.OpenConnection();
            Require(
                ScalarLong(
                    reportConnection,
                    """
                    SELECT COUNT(*)
                    FROM documents
                    WHERE document_id = $document_id
                      AND server_report_id = $server_report_id
                      AND server_document_id = $server_document_id
                      AND synced_at IS NOT NULL;
                    """,
                    ("$document_id", reportResult.LocalDocument.DocumentId),
                    ("$server_report_id", reportId),
                    ("$server_document_id", reportResult.GeneratedDocumentId!)) == 1,
                "local report document should link server report_id and generated_document_id");
            Require(
                ScalarLong(
                    reportConnection,
                    """
                    SELECT COUNT(*)
                    FROM server_id_mappings
                    WHERE local_id = $document_id
                      AND entity_type IN ('document', 'document_version', 'report')
                      AND server_document_id = $server_document_id
                      AND synced_at IS NOT NULL;
                    """,
                    ("$document_id", reportResult.LocalDocument.DocumentId),
                    ("$server_document_id", reportResult.GeneratedDocumentId!)) == 3,
                "local report document should write document, document_version, and report server id mappings");

            var offlineReportContent = services.Reports.BuildDraftContent(
                $"Windows offline queued report {runStamp}",
                "Windows smoke stores a local report first and retries server save.",
                reportSources,
                smokeActorName);
            using var unavailableReportHttpClient = new HttpClient
            {
                BaseAddress = new Uri("http://127.0.0.1:9/"),
                Timeout = TimeSpan.FromSeconds(2)
            };
            var unavailableReportServer = new FlowNoteServerDocumentClient(unavailableReportHttpClient);
            var offlineReportResult = await services.Reports.SaveDraftToServerAsync(
                unavailableReportServer,
                currentDocumentFolder.Id,
                $"Windows offline queued report {runStamp}",
                "Windows smoke stores a local report first and retries server save.",
                offlineReportContent,
                reportSources,
                smokeActorName);
            Require(!offlineReportResult.SyncResult.Success, "missing server client should keep report sync queued locally");
            Require(offlineReportResult.ReportId is null, "offline report save should not have a server report id yet");
            Require(
                ScalarLong(
                    reportConnection,
                    """
                    SELECT COUNT(*)
                    FROM documents
                    WHERE document_id = $document_id
                      AND server_report_id IS NULL;
                    """,
                    ("$document_id", offlineReportResult.LocalDocument.DocumentId)) == 1,
                "offline report save should keep a local report document without a server report id");
            Require(
                ScalarLong(
                    reportConnection,
                    """
                    SELECT COUNT(*)
                    FROM server_sync_queue
                    WHERE entity_type = 'report'
                      AND entity_id = $document_id
                      AND action = 'register_report'
                      AND status = 'FAILED'
                      AND attempt_count >= 1
                      AND last_attempt_at IS NOT NULL
                      AND last_error IS NOT NULL;
                    """,
                    ("$document_id", offlineReportResult.LocalDocument.DocumentId)) == 1,
                "offline report save should leave a failed report sync queue row");
            Require(
                ScalarLong(
                    reportConnection,
                    """
                    SELECT COUNT(*)
                    FROM report_sources
                    WHERE local_report_document_id = $document_id
                      AND source_type IN ('FIELD_COMMENT', 'DOCUMENT', 'WORK_SEQUENCE_ITEM', 'WORK_SEQUENCE_HISTORY');
                    """,
                    ("$document_id", offlineReportResult.LocalDocument.DocumentId)) == 4,
                "offline report save should preserve all local report source links");

            _ = await services.ServerSync.RetryPendingAsync(serverDocuments, serverLogin.UserId);
            Require(
                ScalarLong(
                    reportConnection,
                    """
                    SELECT COUNT(*)
                    FROM server_sync_queue
                    WHERE entity_type = 'report'
                      AND entity_id = $document_id
                      AND status = 'SYNCED'
                      AND server_report_id IS NOT NULL
                      AND attempt_count >= 1;
                    """,
                    ("$document_id", offlineReportResult.LocalDocument.DocumentId)) == 1,
                "report retry should sync the queued report after the server client is available");
            var retriedReportId = ScalarString(
                reportConnection,
                """
                SELECT server_report_id
                FROM documents
                WHERE document_id = $document_id
                  AND server_report_id IS NOT NULL
                  AND server_document_id IS NOT NULL
                  AND synced_at IS NOT NULL;
                """,
                ("$document_id", offlineReportResult.LocalDocument.DocumentId));
            Require(
                retriedReportId?.StartsWith("report_", StringComparison.Ordinal) == true,
                "retried report should link the local document to a server report id");
            var retriedReportDetail = await serverDocuments.GetReportAsync(retriedReportId!);
            Require(
                retriedReportDetail.Sources.Any(item => item.SourceType == "FIELD_COMMENT" && item.SourceId == serverFieldComment.CommentId),
                "retried report detail should trace the FieldComment source");
            Require(
                retriedReportDetail.Sources.Any(item => item.SourceType == "WORK_SEQUENCE_HISTORY" && item.SourceId == reportSequenceHistorySource.ChangeId),
                "retried report detail should trace the work sequence history source");
            var offlineReportTitle = $"Windows offline queued report {runStamp}";
            var serverReportCountBeforeDuplicateRetry = (await serverDocuments.ListReportsAsync()).Count(item => item.Title == offlineReportTitle);
            _ = await services.ServerSync.QueueAndTrySyncReportAsync(
                offlineReportResult.LocalDocument,
                serverDocuments,
                serverLogin.UserId);
            var serverReportCountAfterDuplicateRetry = (await serverDocuments.ListReportsAsync()).Count(item => item.Title == offlineReportTitle);
            Require(
                serverReportCountAfterDuplicateRetry == serverReportCountBeforeDuplicateRetry,
                "repeated report retry should not create a duplicate server report");
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

static Task SimulateHumanPauseAsync()
{
    return Task.Delay(Random.Shared.Next(450, 1150));
}

static async Task<bool> IsServerAvailableAsync(HttpClient httpClient)
{
    try
    {
        using var response = await httpClient.GetAsync("api/v1/health");
        return response.IsSuccessStatusCode;
    }
    catch (HttpRequestException)
    {
        return false;
    }
    catch (TaskCanceledException)
    {
        return false;
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

static void ExecuteNonQuery(SqliteConnection connection, string sql, params (string Name, object Value)[] parameters)
{
    using var command = connection.CreateCommand();
    command.CommandText = sql;
    foreach (var parameter in parameters)
    {
        command.Parameters.AddWithValue(parameter.Name, parameter.Value);
    }

    command.ExecuteNonQuery();
}

static void AssertRolePolicy(string? role, RolePolicyExpectation expected, string context)
{
    Require(string.Equals(role, expected.Role, StringComparison.OrdinalIgnoreCase), $"{context}: expected role {expected.Role}");
    Require(
        RolePermissionPolicy.CanRegisterDocuments(role) == expected.CanRegisterDocuments,
        $"{context}: document registration, upload, status, publish, and work board buttons should match");
    Require(
        RolePermissionPolicy.CanWriteFieldComments(role) == expected.CanWriteFieldComments,
        $"{context}: FieldComment save button should match");
    Require(
        RolePermissionPolicy.CanManageFileWatch(role) == expected.CanManageFileWatch,
        $"{context}: file watch button should match");
    Require(
        RolePermissionPolicy.CanWriteReports(role) == expected.CanWriteReports,
        $"{context}: report button should match");
    Require(
        RolePermissionPolicy.CanReadAccessLogs(role) == expected.CanReadAccessLogs,
        $"{context}: access log read policy should match");
    Require(
        RolePermissionPolicy.CanManageUsers(role) == expected.CanManageUsers,
        $"{context}: user management button should match");
    Require(
        RolePermissionPolicy.CanDownloadDocuments(role) == expected.CanDownloadDocuments,
        $"{context}: controlled copy download button should match");
}

static HttpClient CreateStaticStatusClient(HttpStatusCode statusCode)
{
    return new HttpClient(new StaticStatusHandler(statusCode))
    {
        BaseAddress = new Uri("http://127.0.0.1/")
    };
}

static HttpClient CreateJsonStatusClient(HttpStatusCode statusCode, string json)
{
    return new HttpClient(new JsonStatusHandler(statusCode, json))
    {
        BaseAddress = new Uri("http://127.0.0.1/")
    };
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

static string BuildRunSampleFileName(string sampleFileName, string runStamp)
{
    var extension = Path.GetExtension(sampleFileName);
    var name = Path.GetFileNameWithoutExtension(sampleFileName);
    return $"{name}-{runStamp}{extension}";
}

static string BuildFactoryExceptionSamplePath(
    string testDirectory,
    DocumentPreviewExceptionSampleCriterion criterion,
    string runStamp)
{
    var fileName = BuildRunSampleFileName(criterion.AnonymousSampleFileName, runStamp);
    if (criterion.CaseName != "긴 경로/공백")
    {
        return Path.Combine(testDirectory, fileName);
    }

    return Path.Combine(
        testDirectory,
        "현장 미리보기 예외 샘플",
        "라인 A (혼합 공정)",
        "2026년 운영 안정화",
        "작업표준서 검증용 긴 경로 더미 폴더",
        "교대조 공유 문서 (익명)",
        fileName);
}

static void CreateFactoryExceptionSampleFile(
    DocumentPreviewExceptionSampleCriterion criterion,
    string path)
{
    Directory.CreateDirectory(Path.GetDirectoryName(path)!);
    switch (criterion.PreviewKind)
    {
        case DocumentPreviewKind.Text:
            File.WriteAllText(
                path,
                string.Join(
                    Environment.NewLine,
                    Enumerable.Range(1, 9000)
                        .Select(index => $"익명 작업표준서 대용량 행 {index:0000}: 혼합 공정 점검 항목과 현장 확인 문구입니다.")),
                Encoding.UTF8);
            return;
        case DocumentPreviewKind.Pdf:
            if (criterion.CaseName == "암호/읽기 실패")
            {
                CreateUnreadablePdf(path);
                return;
            }

            File.WriteAllText(
                path,
                "이 파일은 실제 고객 문서가 아닌 손상 PDF 미리보기 검증용 익명 샘플입니다.",
                Encoding.UTF8);
            return;
        case DocumentPreviewKind.Spreadsheet:
            CreateLargeXlsx(path);
            return;
        case DocumentPreviewKind.Image:
            if (criterion.CaseName == "손상")
            {
                CreateCorruptImage(path);
                return;
            }

            CreateHighResolutionBmp(path);
            return;
        case DocumentPreviewKind.Cad:
            File.WriteAllText(
                path,
                "익명 CAD 원본 자리표시자입니다. 본문 미리보기는 지원하지 않습니다.",
                Encoding.UTF8);
            return;
        case DocumentPreviewKind.Hwp:
            File.WriteAllText(
                path,
                "익명 HWP 원본 자리표시자입니다. 본문 미리보기는 지원하지 않습니다.",
                Encoding.UTF8);
            return;
        default:
            File.WriteAllText(path, "익명 미지원 파일 샘플입니다.", Encoding.UTF8);
            return;
    }
}

static string BuildPreviewFailureSmokeMessage(
    DocumentPreviewExceptionSampleCriterion criterion,
    string samplePath)
{
    return criterion.PreviewKind switch
    {
        DocumentPreviewKind.Text =>
            DocumentPreviewPolicy.BuildLargeTextMessage(new FileInfo(samplePath).Length),
        DocumentPreviewKind.Pdf =>
            "PDF 미리보기를 생성할 수 없습니다.\n파일이 손상되었거나 암호, 권한, 현재 클라이언트에서 지원하지 않는 PDF 형식 문제일 수 있습니다.",
        DocumentPreviewKind.Image =>
            "이미지 미리보기를 생성할 수 없습니다.\n파일이 손상되었거나 현재 클라이언트에서 지원하지 않는 이미지 형식입니다.",
        DocumentPreviewKind.Cad or DocumentPreviewKind.Hwp or DocumentPreviewKind.Unsupported =>
            DocumentPreviewPolicy.BuildPreviewUnavailableMessage(criterion.PreviewKind, Path.GetFileName(samplePath)),
        _ =>
            $"{DocumentPreviewPolicy.DisplayName(criterion.PreviewKind)} 미리보기를 생성할 수 없습니다."
    };
}

static bool ContainsKoreanPreviewGuidance(
    DocumentPreviewExceptionSampleCriterion criterion,
    string message)
{
    var expected = criterion.PreviewKind switch
    {
        DocumentPreviewKind.Text => "TXT 파일이 미리보기 기준보다 큽니다",
        DocumentPreviewKind.Pdf => "PDF 미리보기를 생성할 수 없습니다",
        DocumentPreviewKind.Image => "이미지 미리보기를 생성할 수 없습니다",
        DocumentPreviewKind.Cad => "CAD 고급 뷰어는 현재 MVP 범위에서 제외",
        DocumentPreviewKind.Hwp => "HWP 고급 뷰어는 현재 MVP 범위에서 제외",
        _ => "미리보기"
    };

    return message.Contains(expected, StringComparison.Ordinal);
}

static void CreateUnreadablePdf(string path)
{
    File.WriteAllText(
        path,
        """
        %PDF-1.7
        1 0 obj
        << /Type /Catalog /Pages 2 0 R >>
        endobj
        2 0 obj
        << /Type /Pages /Kids [3 0 R] /Count 1 >>
        endobj
        3 0 obj
        << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>
        endobj
        trailer
        << /Root 1 0 R /Encrypt << /Filter /Standard /V 2 /R 3 /Length 128 >> >>
        %%EOF
        """,
        Encoding.ASCII);
}

static void CreateCorruptImage(string path)
{
    File.WriteAllBytes(
        path,
        [0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x46, 0x6C, 0x6F, 0x77, 0x4E, 0x6F, 0x74, 0x65]);
}

static void CreateMinimalXlsx(string path)
{
    using var archive = ZipFile.Open(path, ZipArchiveMode.Create);
    WriteZipText(
        archive,
        "[Content_Types].xml",
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
          <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
          <Default Extension="xml" ContentType="application/xml"/>
          <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
          <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
        </Types>
        """);
    WriteZipText(
        archive,
        "_rels/.rels",
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
        </Relationships>
        """);
    WriteZipText(
        archive,
        "xl/_rels/workbook.xml.rels",
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
        </Relationships>
        """);
    WriteZipText(
        archive,
        "xl/workbook.xml",
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets>
            <sheet name="점검" sheetId="1" r:id="rId1"/>
          </sheets>
        </workbook>
        """);
    WriteZipText(
        archive,
        "xl/worksheets/sheet1.xml",
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <sheetData>
            <row r="1"><c r="A1" t="inlineStr"><is><t>항목</t></is></c><c r="B1" t="inlineStr"><is><t>결과</t></is></c></row>
            <row r="2"><c r="A2" t="inlineStr"><is><t>라인A</t></is></c><c r="B2" t="inlineStr"><is><t>정상</t></is></c></row>
          </sheetData>
        </worksheet>
        """);
}

static void CreateLargeXlsx(string path)
{
    using var archive = ZipFile.Open(path, ZipArchiveMode.Create);
    WriteZipText(
        archive,
        "[Content_Types].xml",
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
          <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
          <Default Extension="xml" ContentType="application/xml"/>
          <Default Extension="bin" ContentType="application/octet-stream"/>
          <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
          <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
        </Types>
        """);
    WriteZipText(
        archive,
        "_rels/.rels",
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
        </Relationships>
        """);
    WriteZipText(
        archive,
        "xl/_rels/workbook.xml.rels",
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
        </Relationships>
        """);
    WriteZipText(
        archive,
        "xl/workbook.xml",
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets>
            <sheet name="익명점검표" sheetId="1" r:id="rId1"/>
          </sheets>
        </workbook>
        """);

    var sheet = new StringBuilder();
    sheet.AppendLine("""<?xml version="1.0" encoding="UTF-8"?>""");
    sheet.AppendLine("""<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">""");
    sheet.AppendLine("<sheetData>");
    sheet.AppendLine("""<row r="1"><c r="A1" t="inlineStr"><is><t>점검항목</t></is></c><c r="B1" t="inlineStr"><is><t>결과</t></is></c><c r="C1" t="inlineStr"><is><t>메모</t></is></c></row>""");
    for (var row = 2; row <= 180; row++)
    {
        sheet.AppendLine($"""<row r="{row}"><c r="A{row}" t="inlineStr"><is><t>익명 설비 점검 {row - 1:000}</t></is></c><c r="B{row}" t="inlineStr"><is><t>정상</t></is></c><c r="C{row}" t="inlineStr"><is><t>현장형 대용량 엑셀 양식 미리보기 검증 행입니다.</t></is></c></row>""");
    }

    sheet.AppendLine("</sheetData>");
    sheet.AppendLine("</worksheet>");
    WriteZipText(archive, "xl/worksheets/sheet1.xml", sheet.ToString());

    var pad = new byte[DocumentPreviewPolicy.LargeSampleBytes + 128 * 1024];
    new Random(20260702).NextBytes(pad);
    var padEntry = archive.CreateEntry("xl/media/anonymous-pad.bin", CompressionLevel.NoCompression);
    using var padStream = padEntry.Open();
    padStream.Write(pad, 0, pad.Length);
}

static void CreateHighResolutionBmp(string path)
{
    const int width = 1600;
    const int height = 1200;
    const int bytesPerPixel = 3;
    var stride = ((width * bytesPerPixel + 3) / 4) * 4;
    var imageSize = stride * height;
    var fileSize = 14 + 40 + imageSize;
    using var stream = File.Create(path);
    using var writer = new BinaryWriter(stream, Encoding.ASCII);

    writer.Write((byte)'B');
    writer.Write((byte)'M');
    writer.Write(fileSize);
    writer.Write((short)0);
    writer.Write((short)0);
    writer.Write(14 + 40);
    writer.Write(40);
    writer.Write(width);
    writer.Write(height);
    writer.Write((short)1);
    writer.Write((short)24);
    writer.Write(0);
    writer.Write(imageSize);
    writer.Write(2835);
    writer.Write(2835);
    writer.Write(0);
    writer.Write(0);

    var rowBuffer = new byte[stride];
    for (var y = height - 1; y >= 0; y--)
    {
        Array.Clear(rowBuffer);
        for (var x = 0; x < width; x++)
        {
            var offset = x * bytesPerPixel;
            rowBuffer[offset] = (byte)(x % 256);
            rowBuffer[offset + 1] = (byte)(y % 256);
            rowBuffer[offset + 2] = (byte)((x + y) % 256);
        }

        writer.Write(rowBuffer);
    }
}

static void WriteZipText(ZipArchive archive, string entryName, string content)
{
    var entry = archive.CreateEntry(entryName);
    using var stream = entry.Open();
    using var writer = new StreamWriter(stream, new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));
    writer.Write(content);
}

static byte[] TinyPngBytes()
{
    return Convert.FromBase64String("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=");
}

static void CreateKoreanPdfOnStaThread(string pdfPath)
{
    CreateKoreanPdf(pdfPath);
}

static void CreateKoreanPdf(string pdfPath)
{
    var contentLines = new[]
    {
        "BT",
        "/F1 24 Tf",
        "72 760 Td",
        "(FlowNote Korean PDF functional smoke) Tj",
        "0 -36 Td",
        "(Foreman A registered this work-standard PDF.) Tj",
        "0 -28 Td",
        "(Lead and member comments are linked as field evidence.) Tj",
        "0 -28 Td",
        "(Mixed process temperature, equipment checks, and issue sharing are tested.) Tj",
        "ET",
        "% FlowNote 한글 PDF 기능 테스트",
        "% 반장 A가 등록한 작업 표준서 PDF입니다.",
        "% 조장 A-1과 조원 A-1의 현장 코멘트를 남기는 흐름을 검증합니다.",
        "% 혼합 공정 온도 확인, 설비 점검, 이상 발생 시 즉시 공유합니다."
    };
    var content = Encoding.UTF8.GetBytes(string.Join("\n", contentLines));
    var compressedContent = Compress(content);
    var objects = new List<byte[]>
    {
        PdfAscii("<< /Type /Catalog /Pages 2 0 R >>"),
        PdfAscii("<< /Type /Pages /Kids [3 0 R] /Count 1 >>"),
        PdfAscii("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"),
        PdfStream(
            $"<< /Length {compressedContent.Length} /Filter /FlateDecode >>",
            compressedContent),
        PdfAscii("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    };

    File.WriteAllBytes(pdfPath, BuildPdf(objects));
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

sealed record RolePolicyExpectation(
    string Role,
    bool CanRegisterDocuments,
    bool CanWriteFieldComments,
    bool CanManageFileWatch,
    bool CanWriteReports,
    bool CanReadAccessLogs,
    bool CanManageUsers,
    bool CanDownloadDocuments);

sealed class StaticStatusHandler(HttpStatusCode statusCode) : HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        return Task.FromResult(
            new HttpResponseMessage(statusCode)
            {
                Content = new StringContent("{\"detail\":\"smoke\"}", Encoding.UTF8, "application/json")
            });
    }
}

sealed class JsonStatusHandler(HttpStatusCode statusCode, string json) : HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        return Task.FromResult(
            new HttpResponseMessage(statusCode)
            {
                Content = new StringContent(json, Encoding.UTF8, "application/json")
            });
    }
}
