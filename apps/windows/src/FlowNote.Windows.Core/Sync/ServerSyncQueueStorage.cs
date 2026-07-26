using FlowNote.Windows.Core.Audit;
using FlowNote.Windows.Core.Documents;
using FlowNote.Windows.Core.FieldComments;
using FlowNote.Windows.Core.History;
using FlowNote.Windows.Core.Reports;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Storage;
using FlowNote.Windows.Core.Tags;
using Microsoft.Data.Sqlite;
using System.Security.Cryptography;
using System.Text.Encodings.Web;
using System.Text.Json;

namespace FlowNote.Windows.Core.Sync;

public sealed partial class ServerSyncService
{
    public static string CreateDocumentIdempotencyKey(string documentId, int versionNo = 1)
    {
        return $"wpf:document:{documentId}:v{versionNo}";
    }

    public static string CreateDocumentVersionIdempotencyKey(string documentId, int versionNo)
    {
        return $"wpf:document-version:{documentId}:v{versionNo}";
    }

    public static string CreateDocumentPublishIdempotencyKey(string documentId, int versionNo)
    {
        return $"wpf:document-publish:{documentId}:v{versionNo}";
    }

    public static string CreateDocumentStatusIdempotencyKey(string documentId, int versionNo, string status, DateTime updatedAt)
    {
        return $"wpf:document-status:{documentId}:v{versionNo}:{status}:{updatedAt:yyyyMMddHHmmssfffffff}";
    }

    public static string CreateDocumentTagsIdempotencyKey(
        string documentId,
        IReadOnlyList<string> tags,
        DateTime updatedAt)
    {
        var tagHash = ComputeSha256(JsonSerializer.Serialize(tags.OrderBy(value => value, StringComparer.Ordinal)));
        return $"wpf:document-tags:{documentId}:{tagHash}:{updatedAt:yyyyMMddHHmmssfffffff}";
    }

    public static string CreateFieldCommentIdempotencyKey(string commentId)
    {
        return $"wpf:field-comment:{commentId}";
    }

    public static string CreateFieldCommentAttachmentIdempotencyKey(string attachmentId)
    {
        return $"wpf:field-comment-attachment:{attachmentId}";
    }

    public static string CreateFieldCommentReviewIdempotencyKey(string commentId, DateTime changedAt)
    {
        return $"wpf:field-comment-review:{commentId}:{changedAt:yyyyMMddHHmmssfffffff}";
    }

    public static string CreateAccessLogIdempotencyKey(long accessLogId, string action)
    {
        return $"wpf:access-log:{accessLogId}:{NormalizeAccessLogAction(action)}";
    }

    public static string CreateReportIdempotencyKey(string localReportDocumentId)
    {
        return $"wpf:report:{localReportDocumentId}";
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

    private void EnqueueDocumentVersion(DocumentRecord document, string? failureReason)
    {
        Enqueue(
            "document_version",
            document.DocumentId,
            "register_document_version",
            document.DocumentId,
            document.VersionNo,
            CreateDocumentVersionIdempotencyKey(document.DocumentId, document.VersionNo),
            failureReason);
    }

    private void EnqueueDocumentPublish(DocumentRecord document, string? failureReason)
    {
        var versionNo = document.PublishedVersionNo ?? document.VersionNo;
        Enqueue(
            "document_publish",
            document.DocumentId,
            "publish_document_version",
            document.DocumentId,
            versionNo,
            CreateDocumentPublishIdempotencyKey(document.DocumentId, versionNo),
            failureReason);
    }

    private void EnqueueDocumentStatus(DocumentRecord document, string? failureReason)
    {
        var payloadJson = JsonSerializer.Serialize(new DocumentStatusSyncPayload(document.Status));
        Enqueue(
            "document_status",
            document.DocumentId,
            "update_document_status",
            document.DocumentId,
            document.VersionNo,
            CreateDocumentStatusIdempotencyKey(document.DocumentId, document.VersionNo, document.Status, document.UpdatedAt),
            failureReason,
            payloadJson);
    }

    private void EnqueueDocumentTags(DocumentRecord document, string? failureReason)
    {
        var tags = TagService.CleanTags(document.TagList)
            .OrderBy(value => value, StringComparer.Ordinal)
            .ToList();
        Enqueue(
            "document_tags",
            document.DocumentId,
            "replace_document_tags",
            document.DocumentId,
            document.VersionNo,
            CreateDocumentTagsIdempotencyKey(document.DocumentId, tags, document.UpdatedAt),
            failureReason,
            JsonSerializer.Serialize(new DocumentTagsSyncPayload(tags)));
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
        var parent = TryGetFieldCommentParent(attachment.CommentId);
        Enqueue(
            "field_comment_attachment",
            attachment.AttachmentId,
            "register_field_comment_attachment",
            parent.DocumentId,
            parent.VersionNo,
            CreateFieldCommentAttachmentIdempotencyKey(attachment.AttachmentId),
            failureReason);
    }

    private void EnqueueFieldCommentReview(FieldCommentRecord fieldComment, DateTime changedAt, string? failureReason)
    {
        Enqueue(
            "field_comment_review",
            fieldComment.CommentId,
            "update_field_comment_review",
            fieldComment.DocumentId,
            fieldComment.DocumentVersionNo,
            CreateFieldCommentReviewIdempotencyKey(fieldComment.CommentId, changedAt),
            failureReason,
            JsonSerializer.Serialize(FieldCommentReviewSyncPayload.From(fieldComment)),
            Math.Max(1, fieldComment.ReviewRevision - 1));
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

    private void EnqueueReport(DocumentRecord reportDocument, string? failureReason)
    {
        Enqueue(
            "report",
            reportDocument.DocumentId,
            "register_report",
            reportDocument.DocumentId,
            reportDocument.VersionNo,
            CreateReportIdempotencyKey(reportDocument.DocumentId),
            failureReason);
    }

    private void Enqueue(
        string entityType,
        string entityId,
        string action,
        string? localDocumentId,
        int? localVersionNo,
        string idempotencyKey,
        string? failureReason,
        string? payloadJson = null,
        int? baseDomainRevisionOverride = null)
    {
        var now = DateTime.UtcNow;
        var status = string.IsNullOrWhiteSpace(failureReason) ? Pending : Failed;
        using var connection = database.OpenConnection();
        var snapshot = LoadDocumentSyncSnapshot(connection, localDocumentId, localVersionNo);
        var baseDomainRevision = baseDomainRevisionOverride ??
            LoadBaseDomainRevision(connection, entityType, entityId);
        var intentHash = ComputeSha256($"{entityType}|{entityId}|{action}|{idempotencyKey}|{baseDomainRevision}");
        var sourceSetHash = entityType == "report" ? LoadReportSourceSetHash(connection, entityId) : null;
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
                created_at,
                base_server_revision,
                expected_server_version_id,
                expected_published_version_id,
                local_file_hash_sha256,
                base_domain_revision,
                intent_hash,
                source_set_hash
                ,payload_json
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
                $created_at,
                $base_server_revision,
                $expected_server_version_id,
                $expected_published_version_id,
                $local_file_hash_sha256,
                $base_domain_revision,
                $intent_hash,
                $source_set_hash
                ,$payload_json
            )
            ON CONFLICT(idempotency_key) DO UPDATE SET
                status = CASE
                    WHEN server_sync_queue.status IN ('SYNCED', 'DISCARDED') THEN server_sync_queue.status
                    ELSE excluded.status
                END,
                last_error = CASE
                    WHEN server_sync_queue.status IN ('SYNCED', 'DISCARDED') THEN server_sync_queue.last_error
                    ELSE excluded.last_error
                END,
                base_server_revision = CASE
                    WHEN server_sync_queue.status IN ('SYNCED', 'DISCARDED') THEN server_sync_queue.base_server_revision
                    ELSE excluded.base_server_revision
                END,
                expected_server_version_id = CASE
                    WHEN server_sync_queue.status IN ('SYNCED', 'DISCARDED') THEN server_sync_queue.expected_server_version_id
                    ELSE excluded.expected_server_version_id
                END,
                expected_published_version_id = CASE
                    WHEN server_sync_queue.status IN ('SYNCED', 'DISCARDED') THEN server_sync_queue.expected_published_version_id
                    ELSE excluded.expected_published_version_id
                END,
                local_file_hash_sha256 = CASE
                    WHEN server_sync_queue.status IN ('SYNCED', 'DISCARDED') THEN server_sync_queue.local_file_hash_sha256
                    ELSE excluded.local_file_hash_sha256
                END,
                base_domain_revision = COALESCE(server_sync_queue.base_domain_revision, excluded.base_domain_revision),
                intent_hash = COALESCE(server_sync_queue.intent_hash, excluded.intent_hash),
                source_set_hash = COALESCE(server_sync_queue.source_set_hash, excluded.source_set_hash),
                payload_json = COALESCE(server_sync_queue.payload_json, excluded.payload_json);
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
        command.Parameters.AddWithValue("$base_server_revision", snapshot.ServerRevision is null ? DBNull.Value : snapshot.ServerRevision.Value);
        command.Parameters.AddWithValue("$expected_server_version_id", string.IsNullOrWhiteSpace(snapshot.ServerVersionId) ? DBNull.Value : snapshot.ServerVersionId);
        command.Parameters.AddWithValue("$expected_published_version_id", string.IsNullOrWhiteSpace(snapshot.ServerPublishedVersionId) ? DBNull.Value : snapshot.ServerPublishedVersionId);
        command.Parameters.AddWithValue("$local_file_hash_sha256", string.IsNullOrWhiteSpace(snapshot.LocalFileHashSha256) ? DBNull.Value : snapshot.LocalFileHashSha256);
        command.Parameters.AddWithValue("$base_domain_revision", baseDomainRevision is null ? DBNull.Value : baseDomainRevision.Value);
        command.Parameters.AddWithValue("$intent_hash", intentHash);
        command.Parameters.AddWithValue("$source_set_hash", string.IsNullOrWhiteSpace(sourceSetHash) ? DBNull.Value : sourceSetHash);
        command.Parameters.AddWithValue("$payload_json", string.IsNullOrWhiteSpace(payloadJson) ? DBNull.Value : payloadJson);
        command.ExecuteNonQuery();

        if (!string.IsNullOrWhiteSpace(failureReason))
        {
            RecordSyncHistory(connection, "server_sync.failed", entityType, entityId, failureReason, now);
        }
    }

    private static int? LoadBaseDomainRevision(SqliteConnection connection, string entityType, string entityId)
    {
        if (entityType != "field_comment_review")
        {
            return null;
        }
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT review_revision FROM field_comments WHERE comment_id = $id LIMIT 1;";
        command.Parameters.AddWithValue("$id", entityId);
        var value = command.ExecuteScalar();
        return value is null or DBNull ? null : Convert.ToInt32(value);
    }

    private static string? LoadReportSourceSetHash(SqliteConnection connection, string reportDocumentId)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT source_type, local_source_id, COALESCE(source_version_id, ''),
                   COALESCE(source_hash_sha256, ''), COALESCE(relation_type, '')
            FROM report_sources
            WHERE local_report_document_id = $id
            ORDER BY source_type, local_source_id, source_version_id, relation_type, source_hash_sha256;
            """;
        command.Parameters.AddWithValue("$id", reportDocumentId);
        using var reader = command.ExecuteReader();
        var rows = new List<string>();
        while (reader.Read())
        {
            rows.Add(string.Join("|", Enumerable.Range(0, 5).Select(reader.GetString)));
        }
        return rows.Count == 0 ? null : ComputeSha256(string.Join("\n", rows));
    }

    private static string ComputeSha256(string value) =>
        Convert.ToHexString(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

    private static DocumentSyncSnapshot LoadDocumentSyncSnapshot(
        SqliteConnection connection,
        string? localDocumentId,
        int? localVersionNo)
    {
        if (string.IsNullOrWhiteSpace(localDocumentId))
        {
            return new(null, null, null, null);
        }

        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT document.server_revision, document.server_version_id,
                   document.server_published_version_id,
                   COALESCE(version.local_path, document.local_path)
            FROM documents AS document
            LEFT JOIN document_versions AS version
              ON version.document_id = document.document_id
             AND version.version_no = $version_no
            WHERE document.document_id = $document_id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$document_id", localDocumentId);
        command.Parameters.AddWithValue("$version_no", localVersionNo is null ? DBNull.Value : localVersionNo.Value);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return new(null, null, null, null);
        }

        var storedPath = reader.IsDBNull(3) ? null : reader.GetString(3);
        string? hash = null;
        if (!string.IsNullOrWhiteSpace(storedPath))
        {
            var path = FlowNoteLocalDatabase.ResolveLocalContentPath(storedPath);
            if (File.Exists(path))
            {
                using var stream = File.OpenRead(path);
                hash = Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
            }
        }

        return new(
            reader.IsDBNull(0) ? null : reader.GetInt32(0),
            reader.IsDBNull(1) ? null : reader.GetString(1),
            reader.IsDBNull(2) ? null : reader.GetString(2),
            hash);
    }

    private IReadOnlyList<QueueItem> LoadRetryItems()
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, entity_type, entity_id, action, local_document_id, local_version_no,
                   idempotency_key, base_server_revision, expected_server_version_id,
                   expected_published_version_id, local_file_hash_sha256,
                   base_domain_revision, intent_hash, source_set_hash
                   ,payload_json, attempt_count, last_error
            FROM server_sync_queue
            WHERE status IN ('PENDING', 'FAILED')
            ORDER BY
                COALESCE(
                    CASE
                        WHEN entity_type = 'report' THEN (
                            SELECT COALESCE(
                                CASE report_sources.source_type
                                    WHEN 'DOCUMENT' THEN report_sources.local_source_id
                                END,
                                (
                                    SELECT field_comments.document_id
                                    FROM field_comments
                                    WHERE field_comments.comment_id = report_sources.local_source_id
                                    LIMIT 1
                                )
                            )
                            FROM report_sources
                            WHERE report_sources.local_report_document_id = server_sync_queue.entity_id
                              AND report_sources.source_type IN ('DOCUMENT', 'FIELD_COMMENT')
                            ORDER BY
                                CASE report_sources.source_type
                                    WHEN 'DOCUMENT' THEN 0
                                    WHEN 'FIELD_COMMENT' THEN 1
                                    ELSE 2
                                END,
                                report_sources.id
                            LIMIT 1
                        )
                    END,
                    local_document_id,
                    CASE
                        WHEN entity_type = 'field_comment_attachment' THEN (
                            SELECT field_comments.document_id
                            FROM field_comment_attachments
                            JOIN field_comments
                              ON field_comments.comment_id = field_comment_attachments.comment_id
                            WHERE field_comment_attachments.attachment_id = server_sync_queue.entity_id
                            LIMIT 1
                        )
                    END,
                    entity_id
                ),
                CASE action
                    WHEN 'register_document' THEN 10
                    WHEN 'register_document_version' THEN 20
                    WHEN 'publish_document_version' THEN 30
                    WHEN 'update_document_status' THEN 40
                    WHEN 'replace_document_tags' THEN 45
                    WHEN 'register_field_comment' THEN 50
                    WHEN 'update_field_comment_review' THEN 55
                    WHEN 'register_field_comment_attachment' THEN 60
                    WHEN 'register_access_log_started' THEN 70
                    WHEN 'register_access_log_closed' THEN 80
                    WHEN 'register_access_log_auto_closed' THEN 80
                    WHEN 'register_access_log_download_blocked' THEN 80
                    WHEN 'register_report' THEN 90
                    ELSE 100
                END,
                COALESCE(
                    local_version_no,
                    CASE
                        WHEN entity_type = 'field_comment_attachment' THEN (
                            SELECT field_comments.document_version_no
                            FROM field_comment_attachments
                            JOIN field_comments
                              ON field_comments.comment_id = field_comment_attachments.comment_id
                            WHERE field_comment_attachments.attachment_id = server_sync_queue.entity_id
                            LIMIT 1
                        )
                    END,
                    0
                ),
                id;
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
                reader.GetString(6),
                reader.IsDBNull(7) ? null : reader.GetInt32(7),
                reader.IsDBNull(8) ? null : reader.GetString(8),
                reader.IsDBNull(9) ? null : reader.GetString(9),
                reader.IsDBNull(10) ? null : reader.GetString(10),
                reader.IsDBNull(11) ? null : reader.GetInt32(11),
                reader.IsDBNull(12) ? null : reader.GetString(12),
                reader.IsDBNull(13) ? null : reader.GetString(13),
                reader.IsDBNull(14) ? null : reader.GetString(14),
                reader.GetInt32(15),
                reader.IsDBNull(16) ? null : reader.GetString(16)));
        }

        return items;
    }

    private (string? DocumentId, int? VersionNo) TryGetFieldCommentParent(string commentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT document_id, document_version_no
            FROM field_comments
            WHERE comment_id = $comment_id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$comment_id", commentId);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return (null, null);
        }

        return (
            reader.IsDBNull(0) ? null : reader.GetString(0),
            reader.IsDBNull(1) ? null : reader.GetInt32(1));
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

            case "register_document_version":
                if (item.LocalVersionNo is not null &&
                    TryGetDocumentVersionServerMapping(item.EntityId, item.LocalVersionNo.Value) is { ServerDocumentId: not null } version)
                {
                    MarkQueueAlreadySynced(item, version.ServerDocumentId, version.ServerVersionId, null, null, null);
                    return true;
                }

                return false;

            case "publish_document_version":
                if (item.LocalVersionNo is not null &&
                    TryGetServerIdMapping("document_publish", item.EntityId, item.LocalVersionNo.Value) is { ServerDocumentId: not null } publish)
                {
                    MarkQueueAlreadySynced(item, publish.ServerDocumentId, publish.ServerVersionId, null, null, null);
                    return true;
                }

                return false;

            case "update_document_status":
                return false;

            case "replace_document_tags":
                return false;

            case "register_field_comment":
                if (TryGetFieldCommentServerId(item.EntityId) is { } serverCommentId)
                {
                    MarkQueueAlreadySynced(item, null, null, serverCommentId, null, null);
                    return true;
                }

                return false;

            case "update_field_comment_review":
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

            case "register_report":
                if (TryGetReportServerMapping(item.EntityId) is { ServerReportId: not null } report)
                {
                    MarkQueueAlreadySynced(
                        item,
                        report.ServerDocumentId,
                        report.ServerVersionId,
                        null,
                        null,
                        null,
                        report.ServerReportId);
                    return true;
                }

                return false;

            default:
                return false;
        }
    }


}
