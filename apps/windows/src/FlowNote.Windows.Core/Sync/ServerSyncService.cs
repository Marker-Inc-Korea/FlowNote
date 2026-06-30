using FlowNote.Windows.Core.Audit;
using FlowNote.Windows.Core.Documents;
using FlowNote.Windows.Core.FieldComments;
using FlowNote.Windows.Core.History;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Storage;
using FlowNote.Windows.Core.Tags;
using Microsoft.Data.Sqlite;

namespace FlowNote.Windows.Core.Sync;

public sealed class ServerSyncService(FlowNoteLocalDatabase database)
{
    private const string Pending = "PENDING";
    private const string Failed = "FAILED";
    private const string Synced = "SYNCED";

    public async Task<ServerSyncResult> QueueAndTrySyncDocumentAsync(
        DocumentRecord document,
        FlowNoteServerDocumentClient? serverClient,
        string? serverUserId = null,
        CancellationToken cancellationToken = default)
    {
        EnqueueDocument(document, null);
        if (serverClient is null)
        {
            MarkLatestFailure("document", document.DocumentId, "Server URL is not configured.");
            return new ServerSyncResult(false, "Server URL is not configured. Document sync is queued.");
        }

        return await RetryPendingAsync(serverClient, serverUserId, cancellationToken);
    }

    public async Task<ServerSyncResult> QueueAndTrySyncFieldCommentAsync(
        FieldCommentRecord fieldComment,
        FlowNoteServerDocumentClient? serverClient,
        string? serverUserId = null,
        CancellationToken cancellationToken = default)
    {
        EnqueueFieldComment(fieldComment, null);
        if (serverClient is null)
        {
            MarkLatestFailure("field_comment", fieldComment.CommentId, "Server URL is not configured.");
            return new ServerSyncResult(false, "Server URL is not configured. Field comment sync is queued.");
        }

        return await RetryPendingAsync(serverClient, serverUserId, cancellationToken);
    }

    public async Task<ServerSyncResult> QueueAndTrySyncFieldCommentAttachmentAsync(
        FieldCommentAttachmentRecord attachment,
        FlowNoteServerDocumentClient? serverClient,
        string? serverUserId = null,
        CancellationToken cancellationToken = default)
    {
        EnqueueFieldCommentAttachment(attachment, null);
        if (serverClient is null)
        {
            MarkLatestFailure("field_comment_attachment", attachment.AttachmentId, "Server URL is not configured.");
            return new ServerSyncResult(false, "Server URL is not configured. Field comment attachment sync is queued.");
        }

        return await RetryPendingAsync(serverClient, serverUserId, cancellationToken);
    }

    public async Task<ServerSyncResult> QueueAndTrySyncAccessLogAsync(
        DocumentViewLogRecord accessLog,
        string action,
        FlowNoteServerDocumentClient? serverClient,
        string? serverUserId = null,
        CancellationToken cancellationToken = default)
    {
        EnqueueAccessLog(accessLog, action, null);
        if (serverClient is null)
        {
            MarkLatestFailure("document_access_log", accessLog.Id.ToString(), "Server URL is not configured.");
            return new ServerSyncResult(false, "Server URL is not configured. Access log sync is queued.");
        }

        return await RetryPendingAsync(serverClient, serverUserId, cancellationToken);
    }

    public async Task<ServerSyncResult> RetryPendingAsync(
        FlowNoteServerDocumentClient serverClient,
        string? serverUserId = null,
        CancellationToken cancellationToken = default)
    {
        var items = LoadRetryItems();
        var attempted = 0;
        var synced = 0;
        var failed = 0;
        var skipped = 0;
        string? firstFailureReason = null;

        foreach (var item in items)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (TryMarkAlreadySynced(item))
            {
                skipped++;
                continue;
            }

            attempted++;
            MarkAttempt(item);

            try
            {
                switch (item.Action)
                {
                    case "register_document":
                        await SyncDocumentAsync(item, serverClient, serverUserId, cancellationToken);
                        break;
                    case "register_field_comment":
                        await SyncFieldCommentAsync(item, serverClient, cancellationToken);
                        break;
                    case "register_field_comment_attachment":
                        await SyncFieldCommentAttachmentAsync(item, serverClient, serverUserId, cancellationToken);
                        break;
                    case "register_access_log_started":
                    case "register_access_log_closed":
                    case "register_access_log_auto_closed":
                    case "register_access_log_download_blocked":
                        await SyncAccessLogAsync(item, serverClient, serverUserId, cancellationToken);
                        break;
                    default:
                        throw new InvalidOperationException($"Unsupported sync action: {item.Action}");
                }

                synced++;
            }
            catch (Exception exception) when (exception is HttpRequestException or InvalidOperationException or TaskCanceledException or IOException)
            {
                failed++;
                var reason = SummarizeFailure(exception);
                firstFailureReason ??= reason;
                RecordFailure(item, reason);
            }
        }

        var message = failed == 0
            ? $"Server sync completed. synced={synced}, skipped={skipped}, attempted={attempted}."
            : $"Server sync completed with failures. synced={synced}, skipped={skipped}, failed={failed}, attempted={attempted}. First failure: {firstFailureReason}";
        if (items.Count > 0)
        {
            using var connection = database.OpenConnection();
            RecordSyncHistory(
                connection,
                failed == 0 ? "server_sync.retry_completed" : "server_sync.retry_completed_with_failures",
                "server_sync_queue",
                "pending",
                message,
                DateTime.UtcNow);
        }

        return new ServerSyncResult(failed == 0, message, attempted, synced, failed, skipped);
    }

    public int CountQueuedForEntity(string entityType, string entityId, string? status = null)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = status is null
            ? """
              SELECT COUNT(*)
              FROM server_sync_queue
              WHERE entity_type = $entity_type AND entity_id = $entity_id;
              """
            : """
              SELECT COUNT(*)
              FROM server_sync_queue
              WHERE entity_type = $entity_type AND entity_id = $entity_id AND status = $status;
              """;
        command.Parameters.AddWithValue("$entity_type", entityType);
        command.Parameters.AddWithValue("$entity_id", entityId);
        if (status is not null)
        {
            command.Parameters.AddWithValue("$status", status);
        }

        return Convert.ToInt32(command.ExecuteScalar());
    }

    public static string CreateDocumentIdempotencyKey(string documentId, int versionNo = 1)
    {
        return $"wpf:document:{documentId}:v{versionNo}";
    }

    public static string CreateFieldCommentIdempotencyKey(string commentId)
    {
        return $"wpf:field-comment:{commentId}";
    }

    public static string CreateFieldCommentAttachmentIdempotencyKey(string attachmentId)
    {
        return $"wpf:field-comment-attachment:{attachmentId}";
    }

    public static string CreateAccessLogIdempotencyKey(long accessLogId, string action)
    {
        return $"wpf:access-log:{accessLogId}:{NormalizeAccessLogAction(action)}";
    }

    private void EnqueueDocument(DocumentRecord document, string? failureReason)
    {
        Enqueue(
            "document",
            document.DocumentId,
            "register_document",
            document.DocumentId,
            1,
            CreateDocumentIdempotencyKey(document.DocumentId),
            failureReason);
    }

    private void EnqueueFieldComment(FieldCommentRecord fieldComment, string? failureReason)
    {
        Enqueue(
            "field_comment",
            fieldComment.CommentId,
            "register_field_comment",
            fieldComment.DocumentId,
            fieldComment.DocumentVersionNo,
            CreateFieldCommentIdempotencyKey(fieldComment.CommentId),
            failureReason);
    }

    private void EnqueueFieldCommentAttachment(FieldCommentAttachmentRecord attachment, string? failureReason)
    {
        Enqueue(
            "field_comment_attachment",
            attachment.AttachmentId,
            "register_field_comment_attachment",
            null,
            null,
            CreateFieldCommentAttachmentIdempotencyKey(attachment.AttachmentId),
            failureReason);
    }

    private void EnqueueAccessLog(DocumentViewLogRecord accessLog, string action, string? failureReason)
    {
        var normalizedAction = NormalizeAccessLogAction(action);

        Enqueue(
            "document_access_log",
            accessLog.Id.ToString(),
            normalizedAction,
            accessLog.DocumentId,
            accessLog.VersionNo,
            CreateAccessLogIdempotencyKey(accessLog.Id, normalizedAction),
            failureReason);
    }

    private void Enqueue(
        string entityType,
        string entityId,
        string action,
        string? localDocumentId,
        int? localVersionNo,
        string idempotencyKey,
        string? failureReason)
    {
        var now = DateTime.UtcNow;
        var status = string.IsNullOrWhiteSpace(failureReason) ? Pending : Failed;
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            INSERT INTO server_sync_queue (
                sync_id,
                entity_type,
                entity_id,
                action,
                local_document_id,
                local_version_no,
                idempotency_key,
                status,
                attempt_count,
                last_error,
                created_at
            )
            VALUES (
                $sync_id,
                $entity_type,
                $entity_id,
                $action,
                $local_document_id,
                $local_version_no,
                $idempotency_key,
                $status,
                0,
                $last_error,
                $created_at
            )
            ON CONFLICT(idempotency_key) DO UPDATE SET
                status = CASE
                    WHEN server_sync_queue.status = 'SYNCED' THEN server_sync_queue.status
                    ELSE excluded.status
                END,
                last_error = CASE
                    WHEN server_sync_queue.status = 'SYNCED' THEN server_sync_queue.last_error
                    ELSE excluded.last_error
                END;
            """;
        command.Parameters.AddWithValue("$sync_id", $"sync-{Guid.NewGuid():N}");
        command.Parameters.AddWithValue("$entity_type", entityType);
        command.Parameters.AddWithValue("$entity_id", entityId);
        command.Parameters.AddWithValue("$action", action);
        command.Parameters.AddWithValue("$local_document_id", string.IsNullOrWhiteSpace(localDocumentId) ? DBNull.Value : localDocumentId);
        command.Parameters.AddWithValue("$local_version_no", localVersionNo is null ? DBNull.Value : localVersionNo.Value);
        command.Parameters.AddWithValue("$idempotency_key", idempotencyKey);
        command.Parameters.AddWithValue("$status", status);
        command.Parameters.AddWithValue("$last_error", string.IsNullOrWhiteSpace(failureReason) ? DBNull.Value : failureReason);
        command.Parameters.AddWithValue("$created_at", now.ToString("O"));
        command.ExecuteNonQuery();

        if (!string.IsNullOrWhiteSpace(failureReason))
        {
            RecordSyncHistory(connection, "server_sync.failed", entityType, entityId, failureReason, now);
        }
    }

    private IReadOnlyList<QueueItem> LoadRetryItems()
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, entity_type, entity_id, action, local_document_id, local_version_no, idempotency_key
            FROM server_sync_queue
            WHERE status IN ('PENDING', 'FAILED')
            ORDER BY id;
            """;

        using var reader = command.ExecuteReader();
        var items = new List<QueueItem>();
        while (reader.Read())
        {
            items.Add(new QueueItem(
                reader.GetInt64(0),
                reader.GetString(1),
                reader.GetString(2),
                reader.GetString(3),
                reader.IsDBNull(4) ? null : reader.GetString(4),
                reader.IsDBNull(5) ? null : reader.GetInt32(5),
                reader.GetString(6)));
        }

        return items;
    }

    private bool TryMarkAlreadySynced(QueueItem item)
    {
        switch (item.Action)
        {
            case "register_document":
                if (TryGetDocumentServerMapping(item.EntityId) is { ServerDocumentId: not null } document)
                {
                    MarkQueueAlreadySynced(
                        item,
                        document.ServerDocumentId,
                        document.ServerVersionId,
                        null,
                        null,
                        null);
                    return true;
                }

                return false;

            case "register_field_comment":
                if (TryGetFieldCommentServerId(item.EntityId) is { } serverCommentId)
                {
                    MarkQueueAlreadySynced(item, null, null, serverCommentId, null, null);
                    return true;
                }

                return false;

            case "register_field_comment_attachment":
                if (TryGetFieldCommentAttachmentServerId(item.EntityId) is { } serverAttachmentId)
                {
                    MarkQueueAlreadySynced(item, null, null, null, null, serverAttachmentId);
                    return true;
                }

                return false;

            case "register_access_log_started":
            case "register_access_log_closed":
            case "register_access_log_auto_closed":
            case "register_access_log_download_blocked":
                if (!long.TryParse(item.EntityId, out var accessLogId))
                {
                    return false;
                }

                var isCloseAction = item.Action is "register_access_log_closed" or "register_access_log_auto_closed" or "register_access_log_download_blocked";
                if (TryGetAccessLogServerId(accessLogId, isCloseAction) is { } serverLogId)
                {
                    MarkQueueAlreadySynced(item, null, null, null, serverLogId, null);
                    return true;
                }

                return false;

            default:
                return false;
        }
    }

    private async Task SyncDocumentAsync(
        QueueItem item,
        FlowNoteServerDocumentClient serverClient,
        string? serverUserId,
        CancellationToken cancellationToken)
    {
        if (TryGetDocumentServerMapping(item.EntityId) is { ServerDocumentId: not null } existing)
        {
            MarkQueueSynced(item.Id, existing.ServerDocumentId, existing.ServerVersionId, null, null);
            return;
        }

        var document = LoadDocument(item.EntityId)
            ?? throw new InvalidOperationException($"Local document not found: {item.EntityId}");
        if (string.IsNullOrWhiteSpace(document.LocalPath))
        {
            throw new InvalidOperationException("Local document has no file path for server upload.");
        }

        var filePath = FlowNoteLocalDatabase.ResolveLocalContentPath(document.LocalPath);
        if (!File.Exists(filePath))
        {
            throw new IOException($"Local document file not found: {filePath}");
        }

        var response = await serverClient.RegisterDocumentAsync(
            filePath,
            document.Title,
            document.DocumentType,
            FlowNoteServerDocumentClient.DefaultWpfLocalUploadChangeReason,
            createdBy: Clean(serverUserId),
            idempotencyKey: item.IdempotencyKey,
            tags: document.TagList,
            cancellationToken: cancellationToken);

        var serverVersionId = response.LatestVersion?.VersionId ?? response.LatestVersionId;
        var now = DateTime.UtcNow;
        using var connection = database.OpenConnection();
        using var updateDocument = connection.CreateCommand();
        updateDocument.CommandText = """
            UPDATE documents
            SET server_document_id = $server_document_id,
                server_version_id = $server_version_id,
                synced_at = $synced_at
            WHERE document_id = $document_id;

            UPDATE document_versions
            SET server_version_id = $server_version_id,
                synced_at = $synced_at
            WHERE document_id = $document_id AND version_no = 1;
            """;
        updateDocument.Parameters.AddWithValue("$server_document_id", response.DocumentId);
        updateDocument.Parameters.AddWithValue("$server_version_id", string.IsNullOrWhiteSpace(serverVersionId) ? DBNull.Value : serverVersionId);
        updateDocument.Parameters.AddWithValue("$synced_at", now.ToString("O"));
        updateDocument.Parameters.AddWithValue("$document_id", document.DocumentId);
        updateDocument.ExecuteNonQuery();

        UpsertMapping(connection, "document", document.DocumentId, 0, response.DocumentId, serverVersionId, null, null, null, now);
        UpsertMapping(connection, "document_version", document.DocumentId, 1, response.DocumentId, serverVersionId, null, null, null, now);
        MarkQueueSynced(connection, item.Id, response.DocumentId, serverVersionId, null, null, now);
        RecordSyncHistory(connection, "server_sync.succeeded", "document", document.DocumentId, $"Server document synced: {response.DocumentId}", now);
    }

    private async Task SyncFieldCommentAsync(
        QueueItem item,
        FlowNoteServerDocumentClient serverClient,
        CancellationToken cancellationToken)
    {
        if (TryGetFieldCommentServerId(item.EntityId) is { } existingServerCommentId)
        {
            MarkQueueSynced(item.Id, null, null, existingServerCommentId, null);
            return;
        }

        var fieldComment = LoadFieldComment(item.EntityId)
            ?? throw new InvalidOperationException($"Local field comment not found: {item.EntityId}");
        if (string.IsNullOrWhiteSpace(fieldComment.DocumentId))
        {
            throw new InvalidOperationException("Local field comment has no document id.");
        }

        var documentMapping = TryGetDocumentServerMapping(fieldComment.DocumentId);
        if (documentMapping?.ServerDocumentId is null)
        {
            throw new InvalidOperationException("Local document is not synced to server yet.");
        }

        var response = await serverClient.RegisterFieldCommentAsync(
            fieldComment,
            documentMapping.ServerDocumentId,
            documentMapping.ServerVersionId,
            item.IdempotencyKey,
            cancellationToken);

        var now = DateTime.UtcNow;
        using var connection = database.OpenConnection();
        using var update = connection.CreateCommand();
        update.CommandText = """
            UPDATE field_comments
            SET server_comment_id = $server_comment_id,
                synced_at = $synced_at
            WHERE comment_id = $comment_id;
            """;
        update.Parameters.AddWithValue("$server_comment_id", response.CommentId);
        update.Parameters.AddWithValue("$synced_at", now.ToString("O"));
        update.Parameters.AddWithValue("$comment_id", fieldComment.CommentId);
        update.ExecuteNonQuery();

        UpsertMapping(connection, "field_comment", fieldComment.CommentId, 0, response.DocumentId, response.DocumentVersionId, response.CommentId, null, null, now);
        MarkQueueSynced(connection, item.Id, response.DocumentId, response.DocumentVersionId, response.CommentId, null, now);
        RecordSyncHistory(connection, "server_sync.succeeded", "field_comment", fieldComment.CommentId, $"Server field comment synced: {response.CommentId}", now);
    }

    private async Task SyncFieldCommentAttachmentAsync(
        QueueItem item,
        FlowNoteServerDocumentClient serverClient,
        string? serverUserId,
        CancellationToken cancellationToken)
    {
        if (TryGetFieldCommentAttachmentServerId(item.EntityId) is { } existingServerAttachmentId)
        {
            MarkQueueSynced(item.Id, null, null, null, null, existingServerAttachmentId);
            return;
        }

        var attachment = LoadFieldCommentAttachment(item.EntityId)
            ?? throw new InvalidOperationException($"Local field comment attachment not found: {item.EntityId}");
        var serverCommentId = TryGetFieldCommentServerId(attachment.CommentId);
        if (string.IsNullOrWhiteSpace(serverCommentId))
        {
            throw new InvalidOperationException("Local field comment is not synced to server yet.");
        }

        var filePath = FlowNoteLocalDatabase.ResolveLocalContentPath(attachment.LocalPath);
        if (!File.Exists(filePath))
        {
            throw new IOException($"Local field comment attachment file not found: {filePath}");
        }

        var response = await serverClient.RegisterFieldCommentAttachmentAsync(
            serverCommentId,
            filePath,
            attachment.AttachmentType,
            attachment.Caption,
            attachment.CapturedAt,
            Clean(serverUserId),
            cancellationToken);

        var now = DateTime.UtcNow;
        using var connection = database.OpenConnection();
        using var update = connection.CreateCommand();
        update.CommandText = """
            UPDATE field_comment_attachments
            SET server_attachment_id = $server_attachment_id,
                synced_at = $synced_at
            WHERE attachment_id = $attachment_id;
            """;
        update.Parameters.AddWithValue("$server_attachment_id", response.AttachmentId);
        update.Parameters.AddWithValue("$synced_at", now.ToString("O"));
        update.Parameters.AddWithValue("$attachment_id", attachment.AttachmentId);
        update.ExecuteNonQuery();

        UpsertMapping(
            connection,
            "field_comment_attachment",
            attachment.AttachmentId,
            0,
            null,
            null,
            response.CommentId,
            response.AttachmentId,
            null,
            now);
        MarkQueueSynced(connection, item.Id, null, null, response.CommentId, null, now, response.AttachmentId);
        RecordSyncHistory(
            connection,
            "server_sync.succeeded",
            "field_comment_attachment",
            attachment.AttachmentId,
            $"Server field comment attachment synced: {response.AttachmentId}",
            now);
    }

    private async Task SyncAccessLogAsync(
        QueueItem item,
        FlowNoteServerDocumentClient serverClient,
        string? serverUserId,
        CancellationToken cancellationToken)
    {
        var accessLog = LoadAccessLog(item.EntityId)
            ?? throw new InvalidOperationException($"Local access log not found: {item.EntityId}");
        var isCloseAction = item.Action is "register_access_log_closed" or "register_access_log_auto_closed" or "register_access_log_download_blocked";
        if (TryGetAccessLogServerId(accessLog.Id, isCloseAction) is { } existingServerLogId)
        {
            MarkQueueSynced(item.Id, null, null, null, existingServerLogId);
            return;
        }

        var documentMapping = TryGetDocumentServerMapping(accessLog.DocumentId);
        if (documentMapping?.ServerDocumentId is null)
        {
            throw new InvalidOperationException("Local document is not synced to server yet.");
        }

        var action = item.Action switch
        {
            "register_access_log_auto_closed" => "auto_closed",
            "register_access_log_download_blocked" => "download_blocked",
            "register_access_log_closed" => "view_closed",
            _ => "view_started"
        };
        var response = await serverClient.RegisterAccessLogAsync(
            documentMapping.ServerDocumentId,
            new ServerDocumentAccessLogCreateRequest
            {
                DocumentVersionId = documentMapping.ServerVersionId,
                Action = action,
                ActorId = Clean(serverUserId),
                UserAgent = "FlowNote.Windows",
                IdempotencyKey = item.IdempotencyKey
            },
            cancellationToken);

        var now = DateTime.UtcNow;
        using var connection = database.OpenConnection();
        using var update = connection.CreateCommand();
        update.CommandText = isCloseAction
            ? """
              UPDATE document_view_logs
              SET server_close_log_id = $server_log_id,
                  synced_at = $synced_at
              WHERE id = $id;
              """
            : """
              UPDATE document_view_logs
              SET server_start_log_id = $server_log_id,
                  synced_at = $synced_at
              WHERE id = $id;
              """;
        update.Parameters.AddWithValue("$server_log_id", response.LogId);
        update.Parameters.AddWithValue("$synced_at", now.ToString("O"));
        update.Parameters.AddWithValue("$id", accessLog.Id);
        update.ExecuteNonQuery();

        UpsertMapping(
            connection,
            item.Action == "register_access_log_download_blocked"
                ? "document_access_log_download_blocked"
                : isCloseAction ? "document_access_log_closed" : "document_access_log_started",
            accessLog.Id.ToString(),
            0,
            response.DocumentId,
            response.DocumentVersionId,
            null,
            null,
            response.LogId.ToString(),
            now);
        MarkQueueSynced(connection, item.Id, response.DocumentId, response.DocumentVersionId, null, response.LogId.ToString(), now);
        RecordSyncHistory(connection, "server_sync.succeeded", "document_access_log", accessLog.Id.ToString(), $"Server access log synced: {response.LogId}", now);
    }

    private DocumentRecord? LoadDocument(string documentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, document_id, folder_id, title, file_name, document_type, status, created_by,
                   created_at, updated_at, local_path, version_no, latest_comment
            FROM documents
            WHERE document_id = $document_id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$document_id", documentId);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return null;
        }

        return new DocumentRecord(
            reader.GetInt64(0),
            reader.GetString(1),
            reader.GetInt64(2),
            reader.GetString(3),
            reader.GetString(4),
            reader.GetString(5),
            reader.GetString(6),
            reader.GetString(7),
            DateTime.Parse(reader.GetString(8)),
            DateTime.Parse(reader.GetString(9)),
            reader.IsDBNull(10) ? null : reader.GetString(10),
            reader.GetInt32(11),
            reader.IsDBNull(12) ? null : reader.GetString(12),
            TagService.ListDocumentTags(connection, documentId));
    }

    private FieldCommentRecord? LoadFieldComment(string commentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, comment_id, document_id, document_version_no, comment_type, input_mode, signal_level,
                   raw_content, normalized_content, analysis_content, author_name, reported_by,
                   operator_name, entry_source, device_id, location_code, status, created_at, synced_at
            FROM field_comments
            WHERE comment_id = $comment_id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$comment_id", commentId);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return null;
        }

        return new FieldCommentRecord(
            reader.GetInt64(0),
            reader.GetString(1),
            reader.IsDBNull(2) ? null : reader.GetString(2),
            reader.IsDBNull(3) ? null : reader.GetInt32(3),
            reader.GetString(4),
            reader.GetString(5),
            reader.IsDBNull(6) ? null : reader.GetString(6),
            reader.GetString(7),
            reader.IsDBNull(8) ? null : reader.GetString(8),
            reader.IsDBNull(9) ? null : reader.GetString(9),
            reader.GetString(10),
            reader.IsDBNull(11) ? null : reader.GetString(11),
            reader.IsDBNull(12) ? null : reader.GetString(12),
            reader.GetString(13),
            reader.IsDBNull(14) ? null : reader.GetString(14),
            reader.IsDBNull(15) ? null : reader.GetString(15),
            reader.GetString(16),
            DateTime.Parse(reader.GetString(17)),
            reader.IsDBNull(18) ? null : DateTime.Parse(reader.GetString(18)));
    }

    private FieldCommentAttachmentRecord? LoadFieldCommentAttachment(string attachmentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, attachment_id, comment_id, local_path, original_file_name, extension,
                   content_type, size_bytes, hash_sha256, attachment_type, caption,
                   captured_at, created_by, created_at, server_attachment_id, synced_at
            FROM field_comment_attachments
            WHERE attachment_id = $attachment_id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$attachment_id", attachmentId);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return null;
        }

        return new FieldCommentAttachmentRecord(
            reader.GetInt64(0),
            reader.GetString(1),
            reader.GetString(2),
            reader.GetString(3),
            reader.GetString(4),
            reader.GetString(5),
            reader.IsDBNull(6) ? null : reader.GetString(6),
            reader.GetInt64(7),
            reader.GetString(8),
            reader.GetString(9),
            reader.IsDBNull(10) ? null : reader.GetString(10),
            reader.IsDBNull(11) ? null : DateTime.Parse(reader.GetString(11)),
            reader.GetString(12),
            DateTime.Parse(reader.GetString(13)),
            reader.IsDBNull(14) ? null : reader.GetString(14),
            reader.IsDBNull(15) ? null : DateTime.Parse(reader.GetString(15)));
    }

    private DocumentViewLogRecord? LoadAccessLog(string entityId)
    {
        if (!long.TryParse(entityId, out var id))
        {
            return null;
        }

        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, document_id, version_no, user_name, view_started_at, closed_at, close_reason
            FROM document_view_logs
            WHERE id = $id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$id", id);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return null;
        }

        return new DocumentViewLogRecord(
            reader.GetInt64(0),
            reader.GetString(1),
            reader.GetInt32(2),
            reader.GetString(3),
            DateTime.Parse(reader.GetString(4)),
            reader.IsDBNull(5) ? null : DateTime.Parse(reader.GetString(5)),
            reader.IsDBNull(6) ? null : reader.GetString(6));
    }

    private DocumentServerMapping? TryGetDocumentServerMapping(string documentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT server_document_id, server_version_id
            FROM documents
            WHERE document_id = $document_id
              AND server_document_id IS NOT NULL
              AND synced_at IS NOT NULL
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$document_id", documentId);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return null;
        }

        return new DocumentServerMapping(
            reader.IsDBNull(0) ? null : reader.GetString(0),
            reader.IsDBNull(1) ? null : reader.GetString(1));
    }

    private string? TryGetFieldCommentServerId(string commentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT server_comment_id
            FROM field_comments
            WHERE comment_id = $comment_id
              AND server_comment_id IS NOT NULL
              AND synced_at IS NOT NULL
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$comment_id", commentId);
        return command.ExecuteScalar() as string;
    }

    private string? TryGetFieldCommentAttachmentServerId(string attachmentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT server_attachment_id
            FROM field_comment_attachments
            WHERE attachment_id = $attachment_id
              AND server_attachment_id IS NOT NULL
              AND synced_at IS NOT NULL
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$attachment_id", attachmentId);
        return command.ExecuteScalar() as string;
    }

    private string? TryGetAccessLogServerId(long id, bool closeAction)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = closeAction
            ? """
              SELECT server_close_log_id
              FROM document_view_logs
              WHERE id = $id AND server_close_log_id IS NOT NULL;
              """
            : """
              SELECT server_start_log_id
              FROM document_view_logs
              WHERE id = $id AND server_start_log_id IS NOT NULL;
              """;
        command.Parameters.AddWithValue("$id", id);
        var value = command.ExecuteScalar();
        return value is null or DBNull ? null : Convert.ToString(value);
    }

    private void MarkAttempt(QueueItem item)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            UPDATE server_sync_queue
            SET attempt_count = attempt_count + 1,
                last_attempt_at = $last_attempt_at
            WHERE id = $id;
            """;
        command.Parameters.AddWithValue("$last_attempt_at", DateTime.UtcNow.ToString("O"));
        command.Parameters.AddWithValue("$id", item.Id);
        command.ExecuteNonQuery();
        RecordSyncHistory(
            connection,
            "server_sync.retry_attempted",
            item.EntityType,
            item.EntityId,
            $"Server sync retry attempted: {item.Action} ({item.IdempotencyKey})",
            DateTime.UtcNow);
    }

    private void MarkLatestFailure(string entityType, string entityId, string reason)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            UPDATE server_sync_queue
            SET status = CASE WHEN status = 'SYNCED' THEN status ELSE 'FAILED' END,
                last_error = CASE WHEN status = 'SYNCED' THEN last_error ELSE $last_error END
            WHERE id = (
                SELECT id
                FROM server_sync_queue
                WHERE entity_type = $entity_type AND entity_id = $entity_id
                ORDER BY id DESC
                LIMIT 1
            );
            """;
        command.Parameters.AddWithValue("$last_error", reason);
        command.Parameters.AddWithValue("$entity_type", entityType);
        command.Parameters.AddWithValue("$entity_id", entityId);
        command.ExecuteNonQuery();
        RecordSyncHistory(connection, "server_sync.failed", entityType, entityId, reason, DateTime.UtcNow);
    }

    private void RecordFailure(QueueItem item, string reason)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            UPDATE server_sync_queue
            SET status = 'FAILED',
                last_error = $last_error
            WHERE id = $id;
            """;
        command.Parameters.AddWithValue("$last_error", reason);
        command.Parameters.AddWithValue("$id", item.Id);
        command.ExecuteNonQuery();
        RecordSyncHistory(connection, "server_sync.failed", item.EntityType, item.EntityId, reason, DateTime.UtcNow);
    }

    private void MarkQueueSynced(
        long queueId,
        string? serverDocumentId,
        string? serverVersionId,
        string? serverCommentId,
        string? serverLogId,
        string? serverAttachmentId = null)
    {
        using var connection = database.OpenConnection();
        MarkQueueSynced(
            connection,
            queueId,
            serverDocumentId,
            serverVersionId,
            serverCommentId,
            serverLogId,
            DateTime.UtcNow,
            serverAttachmentId);
    }

    private static void MarkQueueSynced(
        SqliteConnection connection,
        long queueId,
        string? serverDocumentId,
        string? serverVersionId,
        string? serverCommentId,
        string? serverLogId,
        DateTime syncedAt,
        string? serverAttachmentId = null)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            UPDATE server_sync_queue
            SET status = 'SYNCED',
                last_error = NULL,
                synced_at = $synced_at,
                server_document_id = $server_document_id,
                server_version_id = $server_version_id,
                server_comment_id = $server_comment_id,
                server_attachment_id = $server_attachment_id,
                server_log_id = $server_log_id
            WHERE id = $id;
            """;
        command.Parameters.AddWithValue("$synced_at", syncedAt.ToString("O"));
        command.Parameters.AddWithValue("$server_document_id", string.IsNullOrWhiteSpace(serverDocumentId) ? DBNull.Value : serverDocumentId);
        command.Parameters.AddWithValue("$server_version_id", string.IsNullOrWhiteSpace(serverVersionId) ? DBNull.Value : serverVersionId);
        command.Parameters.AddWithValue("$server_comment_id", string.IsNullOrWhiteSpace(serverCommentId) ? DBNull.Value : serverCommentId);
        command.Parameters.AddWithValue("$server_attachment_id", string.IsNullOrWhiteSpace(serverAttachmentId) ? DBNull.Value : serverAttachmentId);
        command.Parameters.AddWithValue("$server_log_id", string.IsNullOrWhiteSpace(serverLogId) ? DBNull.Value : serverLogId);
        command.Parameters.AddWithValue("$id", queueId);
        command.ExecuteNonQuery();
    }

    private void MarkQueueAlreadySynced(
        QueueItem item,
        string? serverDocumentId,
        string? serverVersionId,
        string? serverCommentId,
        string? serverLogId,
        string? serverAttachmentId)
    {
        var now = DateTime.UtcNow;
        using var connection = database.OpenConnection();
        MarkQueueSynced(
            connection,
            item.Id,
            serverDocumentId,
            serverVersionId,
            serverCommentId,
            serverLogId,
            now,
            serverAttachmentId);
        RecordSyncHistory(
            connection,
            "server_sync.skipped_already_synced",
            item.EntityType,
            item.EntityId,
            $"Server sync skipped because local synced_at/server id already exists: {item.Action} ({item.IdempotencyKey})",
            now);
    }

    private static void UpsertMapping(
        SqliteConnection connection,
        string entityType,
        string localId,
        int localVersionNo,
        string? serverDocumentId,
        string? serverVersionId,
        string? serverCommentId,
        string? serverAttachmentId,
        string? serverLogId,
        DateTime syncedAt)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            INSERT INTO server_id_mappings (
                entity_type,
                local_id,
                local_version_no,
                server_document_id,
                server_version_id,
                server_comment_id,
                server_attachment_id,
                server_log_id,
                synced_at
            )
            VALUES (
                $entity_type,
                $local_id,
                $local_version_no,
                $server_document_id,
                $server_version_id,
                $server_comment_id,
                $server_attachment_id,
                $server_log_id,
                $synced_at
            )
            ON CONFLICT(entity_type, local_id, local_version_no) DO UPDATE SET
                server_document_id = excluded.server_document_id,
                server_version_id = excluded.server_version_id,
                server_comment_id = excluded.server_comment_id,
                server_attachment_id = excluded.server_attachment_id,
                server_log_id = excluded.server_log_id,
                synced_at = excluded.synced_at;
            """;
        command.Parameters.AddWithValue("$entity_type", entityType);
        command.Parameters.AddWithValue("$local_id", localId);
        command.Parameters.AddWithValue("$local_version_no", localVersionNo);
        command.Parameters.AddWithValue("$server_document_id", string.IsNullOrWhiteSpace(serverDocumentId) ? DBNull.Value : serverDocumentId);
        command.Parameters.AddWithValue("$server_version_id", string.IsNullOrWhiteSpace(serverVersionId) ? DBNull.Value : serverVersionId);
        command.Parameters.AddWithValue("$server_comment_id", string.IsNullOrWhiteSpace(serverCommentId) ? DBNull.Value : serverCommentId);
        command.Parameters.AddWithValue("$server_attachment_id", string.IsNullOrWhiteSpace(serverAttachmentId) ? DBNull.Value : serverAttachmentId);
        command.Parameters.AddWithValue("$server_log_id", string.IsNullOrWhiteSpace(serverLogId) ? DBNull.Value : serverLogId);
        command.Parameters.AddWithValue("$synced_at", syncedAt.ToString("O"));
        command.ExecuteNonQuery();
    }

    private static void RecordSyncHistory(
        SqliteConnection connection,
        string eventType,
        string targetType,
        string targetId,
        string message,
        DateTime createdAt)
    {
        HistoryService.Record(
            connection,
            eventType,
            "server-sync",
            targetType,
            targetId,
            null,
            message,
            createdAt);
    }

    private static string SummarizeFailure(Exception exception)
    {
        var message = exception switch
        {
            FlowNoteServerAuthenticationException => "Server login expired or revoked. Sign in again; this item remains in the retry queue.",
            TaskCanceledException => "Server response timeout.",
            HttpRequestException => "Server connection failed.",
            _ => exception.Message
        };

        if (string.IsNullOrWhiteSpace(message))
        {
            message = exception.GetType().Name;
        }

        message = message.Replace(Environment.NewLine, " ");
        const int maxLength = 300;
        return message.Length <= maxLength ? message : $"{message[..maxLength]}...";
    }

    private static string? Clean(string? value)
    {
        return string.IsNullOrWhiteSpace(value) ? null : value.Trim();
    }

    private static string NormalizeAccessLogAction(string action)
    {
        return action switch
        {
            "auto_closed" or "register_access_log_auto_closed" => "register_access_log_auto_closed",
            "download_blocked" or "register_access_log_download_blocked" => "register_access_log_download_blocked",
            "view_closed" or "register_access_log_closed" => "register_access_log_closed",
            _ => "register_access_log_started"
        };
    }

    private sealed record QueueItem(
        long Id,
        string EntityType,
        string EntityId,
        string Action,
        string? LocalDocumentId,
        int? LocalVersionNo,
        string IdempotencyKey);

    private sealed record DocumentServerMapping(string? ServerDocumentId, string? ServerVersionId);
}
