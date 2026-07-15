using FlowNote.Windows.Core.Audit;
using FlowNote.Windows.Core.Documents;
using FlowNote.Windows.Core.FieldComments;
using FlowNote.Windows.Core.History;
using FlowNote.Windows.Core.Reports;
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

    public ControlledCopyServerMapping? GetControlledCopyServerMapping(string documentId, int versionNo)
    {
        var mapping = TryGetDocumentVersionServerMapping(documentId, versionNo);
        return string.IsNullOrWhiteSpace(mapping?.ServerDocumentId) || string.IsNullOrWhiteSpace(mapping.ServerVersionId)
            ? null
            : new ControlledCopyServerMapping(mapping.ServerDocumentId, mapping.ServerVersionId);
    }

    public async Task<ServerSyncResult> QueueAndTrySyncDocumentAsync(
        DocumentRecord document,
        FlowNoteServerDocumentClient? serverClient,
        string? serverUserId = null,
        CancellationToken cancellationToken = default)
    {
        EnqueueDocument(document, null);
        if (serverClient is null)
        {
            MarkLatestFailure("document", document.DocumentId, SyncFailureMessages.ServerUrlNotConfigured);
            return new ServerSyncResult(false, "서버 URL이 설정되지 않아 문서 전송을 큐에 보관했습니다. 서버 설정 후 동기화 큐에서 재시도하세요.");
        }

        return await RetryPendingAsync(serverClient, serverUserId, cancellationToken);
    }

    public async Task<ServerSyncResult> QueueAndTrySyncDocumentVersionAsync(
        DocumentRecord document,
        FlowNoteServerDocumentClient? serverClient,
        string? serverUserId = null,
        CancellationToken cancellationToken = default)
    {
        EnqueueDocumentVersion(document, null);
        if (serverClient is null)
        {
            MarkLatestFailure("document_version", document.DocumentId, SyncFailureMessages.ServerUrlNotConfigured);
            return new ServerSyncResult(false, "서버 URL이 설정되지 않아 문서 버전 전송을 큐에 보관했습니다. 서버 설정 후 동기화 큐에서 재시도하세요.");
        }

        return await RetryPendingAsync(serverClient, serverUserId, cancellationToken);
    }

    public async Task<ServerSyncResult> QueueAndTrySyncDocumentPublishAsync(
        DocumentRecord document,
        FlowNoteServerDocumentClient? serverClient,
        string? serverUserId = null,
        CancellationToken cancellationToken = default)
    {
        EnqueueDocumentPublish(document, null);
        if (serverClient is null)
        {
            MarkLatestFailure("document_publish", document.DocumentId, SyncFailureMessages.ServerUrlNotConfigured);
            return new ServerSyncResult(false, "서버 URL이 설정되지 않아 문서 공개 전송을 큐에 보관했습니다. 서버 설정 후 동기화 큐에서 재시도하세요.");
        }

        return await RetryPendingAsync(serverClient, serverUserId, cancellationToken);
    }

    public async Task<ServerSyncResult> QueueAndTrySyncDocumentStatusAsync(
        DocumentRecord document,
        FlowNoteServerDocumentClient? serverClient,
        string? serverUserId = null,
        CancellationToken cancellationToken = default)
    {
        EnqueueDocumentStatus(document, null);
        if (serverClient is null)
        {
            MarkLatestFailure("document_status", document.DocumentId, SyncFailureMessages.ServerUrlNotConfigured);
            return new ServerSyncResult(false, "서버 URL이 설정되지 않아 문서 상태 전송을 큐에 보관했습니다. 서버 설정 후 동기화 큐에서 재시도하세요.");
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
            MarkLatestFailure("field_comment", fieldComment.CommentId, SyncFailureMessages.ServerUrlNotConfigured);
            return new ServerSyncResult(false, "서버 URL이 설정되지 않아 FieldComment 전송을 큐에 보관했습니다. 서버 설정 후 동기화 큐에서 재시도하세요.");
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
            MarkLatestFailure("field_comment_attachment", attachment.AttachmentId, SyncFailureMessages.ServerUrlNotConfigured);
            return new ServerSyncResult(false, "서버 URL이 설정되지 않아 FieldComment 첨부 전송을 큐에 보관했습니다. 서버 설정 후 동기화 큐에서 재시도하세요.");
        }

        return await RetryPendingAsync(serverClient, serverUserId, cancellationToken);
    }

    public async Task<ServerSyncResult> QueueAndTrySyncFieldCommentReviewAsync(
        FieldCommentRecord fieldComment,
        FlowNoteServerDocumentClient? serverClient,
        string? serverUserId = null,
        DateTime? changedAt = null,
        CancellationToken cancellationToken = default)
    {
        EnqueueFieldCommentReview(fieldComment, changedAt ?? DateTime.UtcNow, null);
        if (serverClient is null)
        {
            MarkLatestFailure("field_comment_review", fieldComment.CommentId, SyncFailureMessages.ServerUrlNotConfigured);
            return new ServerSyncResult(false, "서버 URL이 설정되지 않아 FieldComment 검토 변경을 큐에 보관했습니다. 서버 설정 후 동기화 큐에서 재시도하세요.");
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
            MarkLatestFailure("document_access_log", accessLog.Id.ToString(), SyncFailureMessages.ServerUrlNotConfigured);
            return new ServerSyncResult(false, "서버 URL이 설정되지 않아 접근 로그 전송을 큐에 보관했습니다. 서버 설정 후 동기화 큐에서 재시도하세요.");
        }

        return await RetryPendingAsync(serverClient, serverUserId, cancellationToken);
    }

    public async Task<ServerSyncResult> QueueAndTrySyncReportAsync(
        DocumentRecord reportDocument,
        FlowNoteServerDocumentClient? serverClient,
        string? serverUserId = null,
        CancellationToken cancellationToken = default)
    {
        EnqueueReport(reportDocument, null);
        if (serverClient is null)
        {
            MarkLatestFailure("report", reportDocument.DocumentId, SyncFailureMessages.ServerUrlNotConfigured, countAttempt: true);
            return new ServerSyncResult(false, "서버 URL이 설정되지 않아 보고서 서버 저장을 큐에 보관했습니다. 서버 설정 후 동기화 큐에서 재시도하세요.");
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
        var held = 0;
        string? firstFailureReason = null;

        foreach (var item in items)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (TryMarkAlreadySynced(item))
            {
                skipped++;
                continue;
            }

            if (GetDependencyHoldReason(item) is { } holdReason)
            {
                held++;
                firstFailureReason ??= holdReason;
                MarkDependencyHold(item, holdReason);
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
                    case "register_document_version":
                        await SyncDocumentVersionAsync(item, serverClient, serverUserId, cancellationToken);
                        break;
                    case "publish_document_version":
                        await SyncDocumentPublishAsync(item, serverClient, cancellationToken);
                        break;
                    case "update_document_status":
                        await SyncDocumentStatusAsync(item, serverClient, cancellationToken);
                        break;
                    case "register_field_comment":
                        await SyncFieldCommentAsync(item, serverClient, cancellationToken);
                        break;
                    case "update_field_comment_review":
                        await SyncFieldCommentReviewAsync(item, serverClient, serverUserId, cancellationToken);
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
                    case "register_report":
                        await SyncReportAsync(item, serverClient, cancellationToken);
                        break;
                    default:
                        throw new InvalidOperationException($"Unsupported sync action: {item.Action}");
                }

                synced++;
            }
            catch (FlowNoteServerAuthenticationException exception)
            {
                failed++;
                var reason = SummarizeFailure(exception);
                firstFailureReason ??= reason;
                RecordFailure(item, reason);
                break;
            }
            catch (Exception exception) when (exception is HttpRequestException or TaskCanceledException)
            {
                failed++;
                var reason = SummarizeFailure(exception);
                firstFailureReason ??= reason;
                RecordFailure(item, reason);
                break;
            }
            catch (Exception exception) when (exception is InvalidOperationException or IOException)
            {
                failed++;
                var reason = SummarizeFailure(exception);
                firstFailureReason ??= reason;
                RecordFailure(item, reason);
            }
        }

        var metrics = GetOperationalMetrics();
        var success = failed == 0 && held == 0;
        var message = success
            ? $"서버 동기화 완료: 성공 {synced}건, 이미 처리 {skipped}건, 시도 {attempted}건. 남은 큐 {metrics.QueueDepth}건, 최장 대기 {metrics.OldestWaitingText}, 최근 1시간 처리 {metrics.SyncedLastHour}건."
            : $"서버 동기화에 조치가 필요한 항목이 있습니다: 성공 {synced}건, 이미 처리 {skipped}건, 보류 {held}건, 실패 {failed}건, 시도 {attempted}건. 남은 큐 {metrics.QueueDepth}건, 최장 대기 {metrics.OldestWaitingText}, 실패 분포 {metrics.FailureDistributionText}. 첫 사유: {firstFailureReason} 동기화 큐의 우선순위와 조치 내용을 확인한 뒤 서버 실행 상태, 서버 URL, 로그인 상태, 선행 문서/버전 동기화 여부를 조치하고 재시도하세요. 로컬 데이터는 삭제되지 않습니다.";
        if (items.Count > 0)
        {
            using var connection = database.OpenConnection();
            RecordSyncHistory(
                connection,
                success ? "server_sync.retry_completed" : "server_sync.retry_completed_with_failures",
                "server_sync_queue",
                "pending",
                message,
                DateTime.UtcNow);
        }

        return new ServerSyncResult(success, message, attempted, synced, failed, skipped, held);
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

    public IReadOnlyList<ServerSyncQueueRecord> ListQueueItems(int limit = 500)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, sync_id, entity_type, entity_id, action, local_document_id, local_version_no,
                   idempotency_key, status, attempt_count, last_error, created_at, last_attempt_at,
                   synced_at, server_document_id, server_version_id, server_report_id, server_comment_id,
                   server_attachment_id, server_log_id
            FROM server_sync_queue
            ORDER BY
                CASE status
                    WHEN 'FAILED' THEN 0
                    WHEN 'PENDING' THEN 1
                    ELSE 2
                END,
                COALESCE(last_attempt_at, created_at) DESC,
                id DESC
            LIMIT $limit;
            """;
        command.Parameters.AddWithValue("$limit", limit);

        using var reader = command.ExecuteReader();
        var records = new List<ServerSyncQueueRecord>();
        while (reader.Read())
        {
            records.Add(new ServerSyncQueueRecord(
                reader.GetInt64(0),
                reader.GetString(1),
                reader.GetString(2),
                reader.GetString(3),
                reader.GetString(4),
                reader.IsDBNull(5) ? null : reader.GetString(5),
                reader.IsDBNull(6) ? null : reader.GetInt32(6),
                reader.GetString(7),
                reader.GetString(8),
                reader.GetInt32(9),
                reader.IsDBNull(10) ? null : TranslateFailureReason(reader.GetString(10)),
                DateTime.Parse(reader.GetString(11)),
                reader.IsDBNull(12) ? null : DateTime.Parse(reader.GetString(12)),
                reader.IsDBNull(13) ? null : DateTime.Parse(reader.GetString(13)),
                reader.IsDBNull(14) ? null : reader.GetString(14),
                reader.IsDBNull(15) ? null : reader.GetString(15),
                reader.IsDBNull(16) ? null : reader.GetString(16),
                reader.IsDBNull(17) ? null : reader.GetString(17),
                reader.IsDBNull(18) ? null : reader.GetString(18),
                reader.IsDBNull(19) ? null : reader.GetString(19)));
        }

        return records;
    }

    public ServerSyncQueueSummary GetQueueSummary()
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT status, entity_type, action, last_error
            FROM server_sync_queue;
            """;

        var pending = 0;
        var failed = 0;
        var synced = 0;
        var held = 0;
        using var reader = command.ExecuteReader();
        while (reader.Read())
        {
            var status = reader.GetString(0);
            var diagnosis = ServerSyncQueueDiagnostics.Classify(
                status,
                reader.GetString(1),
                reader.GetString(2),
                reader.IsDBNull(3) ? null : TranslateFailureReason(reader.GetString(3)));
            pending += string.Equals(status, Pending, StringComparison.Ordinal) ? 1 : 0;
            failed += string.Equals(status, Failed, StringComparison.Ordinal) ? 1 : 0;
            synced += string.Equals(status, Synced, StringComparison.Ordinal) ? 1 : 0;
            held += diagnosis.IsDependencyHold && !string.Equals(status, Synced, StringComparison.Ordinal) ? 1 : 0;
        }

        return new ServerSyncQueueSummary(pending, failed, synced, held);
    }

    public ServerSyncOperationalMetrics GetOperationalMetrics(DateTime? now = null)
    {
        var measuredAt = now ?? DateTime.UtcNow;
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT status, entity_type, action, last_error, created_at, synced_at
            FROM server_sync_queue;
            """;

        var queueDepth = 0;
        DateTime? oldestCreatedAt = null;
        var syncedLastHour = 0;
        var failureReasons = new Dictionary<string, int>(StringComparer.Ordinal);
        using var reader = command.ExecuteReader();
        while (reader.Read())
        {
            var status = reader.GetString(0);
            if (string.Equals(status, Synced, StringComparison.Ordinal))
            {
                if (!reader.IsDBNull(5) &&
                    DateTime.TryParse(reader.GetString(5), out var syncedAt) &&
                    syncedAt >= measuredAt.AddHours(-1) && syncedAt <= measuredAt)
                {
                    syncedLastHour++;
                }
                continue;
            }

            queueDepth++;
            if (DateTime.TryParse(reader.GetString(4), out var createdAt) &&
                (oldestCreatedAt is null || createdAt < oldestCreatedAt.Value))
            {
                oldestCreatedAt = createdAt;
            }

            if (string.Equals(status, Failed, StringComparison.Ordinal))
            {
                var diagnosis = ServerSyncQueueDiagnostics.Classify(
                    status,
                    reader.GetString(1),
                    reader.GetString(2),
                    reader.IsDBNull(3) ? null : TranslateFailureReason(reader.GetString(3)));
                failureReasons[diagnosis.Category] = failureReasons.GetValueOrDefault(diagnosis.Category) + 1;
            }
        }

        var oldestWaitingTime = oldestCreatedAt is null
            ? null
            : measuredAt - oldestCreatedAt.Value;
        return new ServerSyncOperationalMetrics(
            queueDepth,
            oldestWaitingTime,
            syncedLastHour,
            failureReasons
                .OrderByDescending(item => item.Value)
                .ThenBy(item => item.Key, StringComparer.Ordinal)
                .Select(item => new ServerSyncFailureMetric(item.Key, item.Value))
                .ToList());
    }

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
        Enqueue(
            "document_status",
            document.DocumentId,
            "update_document_status",
            document.DocumentId,
            document.VersionNo,
            CreateDocumentStatusIdempotencyKey(document.DocumentId, document.VersionNo, document.Status, document.UpdatedAt),
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
                reader.GetString(6)));
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

    private async Task SyncDocumentVersionAsync(
        QueueItem item,
        FlowNoteServerDocumentClient serverClient,
        string? serverUserId,
        CancellationToken cancellationToken)
    {
        var versionNo = item.LocalVersionNo
            ?? throw new InvalidOperationException("Local document version number is required.");
        if (TryGetDocumentVersionServerMapping(item.EntityId, versionNo) is { ServerDocumentId: not null } existing)
        {
            MarkQueueSynced(item.Id, existing.ServerDocumentId, existing.ServerVersionId, null, null);
            return;
        }

        var document = LoadDocument(item.EntityId)
            ?? throw new InvalidOperationException($"Local document not found: {item.EntityId}");
        var documentMapping = TryGetDocumentServerMapping(item.EntityId);
        if (documentMapping?.ServerDocumentId is null)
        {
            throw new InvalidOperationException(SyncFailureMessages.DocumentDependencyNotSynced);
        }

        var localVersion = LoadDocumentVersion(item.EntityId, versionNo)
            ?? throw new InvalidOperationException($"Local document version not found: {item.EntityId} v{versionNo}");
        var existingServerVersion = await TryFindServerVersionByNumberAsync(
            serverClient,
            documentMapping.ServerDocumentId,
            versionNo,
            cancellationToken);
        if (existingServerVersion is not null)
        {
            MarkDocumentVersionSynced(
                item,
                document,
                localVersion,
                documentMapping.ServerDocumentId,
                existingServerVersion.VersionId,
                DateTime.UtcNow);
            return;
        }

        if (string.IsNullOrWhiteSpace(localVersion.LocalPath))
        {
            throw new InvalidOperationException("Local document version has no file path for server upload.");
        }

        var filePath = FlowNoteLocalDatabase.ResolveLocalContentPath(localVersion.LocalPath);
        if (!File.Exists(filePath))
        {
            throw new IOException($"Local document file not found: {filePath}");
        }

        ServerDocumentVersionResponse response;
        try
        {
            response = await serverClient.RegisterVersionAsync(
                documentMapping.ServerDocumentId,
                filePath,
                Clean(localVersion.Comment) ?? FlowNoteServerDocumentClient.DefaultWpfLocalUploadChangeReason,
                localVersion.VersionLabel,
                Clean(serverUserId),
                item.IdempotencyKey,
                cancellationToken);
        }
        catch (InvalidOperationException exception) when (IsServerVersionConflict(exception))
        {
            existingServerVersion = await TryFindServerVersionByNumberAsync(
                serverClient,
                documentMapping.ServerDocumentId,
                versionNo,
                cancellationToken);
            if (existingServerVersion is null)
            {
                throw;
            }

            MarkDocumentVersionSynced(
                item,
                document,
                localVersion,
                documentMapping.ServerDocumentId,
                existingServerVersion.VersionId,
                DateTime.UtcNow);
            return;
        }

        MarkDocumentVersionSynced(
            item,
            document,
            localVersion,
            response.DocumentId,
            response.VersionId,
            DateTime.UtcNow);
    }

    private async Task SyncDocumentPublishAsync(
        QueueItem item,
        FlowNoteServerDocumentClient serverClient,
        CancellationToken cancellationToken)
    {
        var versionNo = item.LocalVersionNo
            ?? throw new InvalidOperationException("Local document version number is required.");
        var document = LoadDocument(item.EntityId)
            ?? throw new InvalidOperationException($"Local document not found: {item.EntityId}");
        var documentMapping = TryGetDocumentServerMapping(item.EntityId);
        if (documentMapping?.ServerDocumentId is null)
        {
            throw new InvalidOperationException(SyncFailureMessages.DocumentDependencyNotSynced);
        }

        var versionMapping = TryGetDocumentVersionServerMapping(item.EntityId, versionNo);
        if (versionMapping?.ServerVersionId is null)
        {
            throw new InvalidOperationException(SyncFailureMessages.DocumentPublishVersionNotConfirmed);
        }

        var response = await serverClient.PublishVersionAsync(
            documentMapping.ServerDocumentId,
            versionMapping.ServerVersionId,
            $"WPF local publish sync v{versionNo}",
            cancellationToken);
        var publishedVersionId = response.PublishedVersion?.VersionId ?? response.PublishedVersionId ?? versionMapping.ServerVersionId;
        var now = DateTime.UtcNow;

        using var connection = database.OpenConnection();
        UpsertMapping(connection, "document_publish", document.DocumentId, versionNo, response.DocumentId, publishedVersionId, null, null, null, now);
        UpsertMapping(connection, "document", document.DocumentId, 0, response.DocumentId, response.LatestVersionId ?? documentMapping.ServerVersionId, null, null, null, now);
        MarkQueueSynced(connection, item.Id, response.DocumentId, publishedVersionId, null, null, now);
        RecordSyncHistory(connection, "server_sync.succeeded", "document_publish", document.DocumentId, $"Server document publish synced: {response.DocumentId} v{versionNo}", now);
    }

    private async Task SyncDocumentStatusAsync(
        QueueItem item,
        FlowNoteServerDocumentClient serverClient,
        CancellationToken cancellationToken)
    {
        var document = LoadDocument(item.EntityId)
            ?? throw new InvalidOperationException($"Local document not found: {item.EntityId}");
        var documentMapping = TryGetDocumentServerMapping(item.EntityId);
        if (documentMapping?.ServerDocumentId is null)
        {
            throw new InvalidOperationException(SyncFailureMessages.DocumentDependencyNotSynced);
        }

        if (string.Equals(document.Status, "PUBLISHED", StringComparison.Ordinal))
        {
            if (document.PublishedVersionNo is null)
            {
                throw new InvalidOperationException(SyncFailureMessages.PublishedStatusMissingPublishedVersion);
            }

            if (TryGetServerIdMapping("document_publish", item.EntityId, document.PublishedVersionNo.Value)?.ServerVersionId is null)
            {
                throw new InvalidOperationException(SyncFailureMessages.PublishedStatusPublishMappingNotSynced);
            }
        }

        var response = await serverClient.UpdateDocumentStatusAsync(
            documentMapping.ServerDocumentId,
            document.Status,
            $"WPF local status sync: {document.Status}",
            cancellationToken);
        var now = DateTime.UtcNow;
        var serverVersionId = response.LatestVersionId ?? documentMapping.ServerVersionId;

        using var connection = database.OpenConnection();
        UpsertMapping(connection, "document_status", document.DocumentId, item.LocalVersionNo ?? document.VersionNo, response.DocumentId, serverVersionId, null, null, null, now);
        UpsertMapping(connection, "document", document.DocumentId, 0, response.DocumentId, serverVersionId, null, null, null, now);
        MarkQueueSynced(connection, item.Id, response.DocumentId, serverVersionId, null, null, now);
        RecordSyncHistory(connection, "server_sync.succeeded", "document_status", document.DocumentId, $"Server document status synced: {response.DocumentId} {document.Status}", now);
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

        var documentMapping = fieldComment.DocumentVersionNo is null
            ? TryGetDocumentServerMapping(fieldComment.DocumentId)
            : TryGetDocumentVersionServerMapping(fieldComment.DocumentId, fieldComment.DocumentVersionNo.Value)
              ?? TryGetDocumentServerMapping(fieldComment.DocumentId);
        if (documentMapping?.ServerDocumentId is null)
        {
            throw new InvalidOperationException(SyncFailureMessages.DocumentDependencyNotSynced);
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

    private async Task SyncFieldCommentReviewAsync(
        QueueItem item,
        FlowNoteServerDocumentClient serverClient,
        string? serverUserId,
        CancellationToken cancellationToken)
    {
        var fieldComment = LoadFieldComment(item.EntityId)
            ?? throw new InvalidOperationException($"Local field comment not found: {item.EntityId}");
        var serverCommentId = TryGetFieldCommentServerId(fieldComment.CommentId);
        if (string.IsNullOrWhiteSpace(serverCommentId))
        {
            throw new InvalidOperationException(SyncFailureMessages.FieldCommentDependencyNotSynced);
        }

        var response = await serverClient.UpdateFieldCommentReviewAsync(
            serverCommentId,
            ServerFieldCommentReviewRequest.FromLocal(fieldComment, serverUserId),
            cancellationToken);

        var now = DateTime.UtcNow;
        using var connection = database.OpenConnection();
        UpsertMapping(
            connection,
            "field_comment_review",
            fieldComment.CommentId,
            0,
            response.DocumentId,
            response.DocumentVersionId,
            response.CommentId,
            null,
            null,
            now);
        MarkQueueSynced(connection, item.Id, response.DocumentId, response.DocumentVersionId, response.CommentId, null, now);
        RecordSyncHistory(
            connection,
            "server_sync.succeeded",
            "field_comment_review",
            fieldComment.CommentId,
            $"Server field comment review synced: {response.CommentId} {response.Status}",
            now);
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
            throw new InvalidOperationException(SyncFailureMessages.FieldCommentDependencyNotSynced);
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
            item.IdempotencyKey,
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

        var documentMapping = TryGetDocumentVersionServerMapping(accessLog.DocumentId, accessLog.VersionNo)
            ?? TryGetDocumentServerMapping(accessLog.DocumentId);
        if (documentMapping?.ServerDocumentId is null)
        {
            throw new InvalidOperationException(SyncFailureMessages.DocumentDependencyNotSynced);
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

    private async Task SyncReportAsync(
        QueueItem item,
        FlowNoteServerDocumentClient serverClient,
        CancellationToken cancellationToken)
    {
        if (TryGetReportServerMapping(item.EntityId) is { ServerReportId: not null } existing)
        {
            MarkQueueSynced(
                item.Id,
                existing.ServerDocumentId,
                existing.ServerVersionId,
                null,
                null,
                serverReportId: existing.ServerReportId);
            return;
        }

        var document = LoadDocument(item.EntityId)
            ?? throw new InvalidOperationException($"Local report document not found: {item.EntityId}");
        if (!string.Equals(document.DocumentType, "Report", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("Local queued report document has an unsupported document type.");
        }

        if (string.IsNullOrWhiteSpace(document.LocalPath))
        {
            throw new InvalidOperationException("Local report document has no file path for server upload.");
        }

        var filePath = FlowNoteLocalDatabase.ResolveLocalContentPath(document.LocalPath);
        if (!File.Exists(filePath))
        {
            throw new IOException($"Local report document file not found: {filePath}");
        }

        var content = await File.ReadAllTextAsync(filePath, cancellationToken);
        var sources = MapQueuedReportSources(item.EntityId);
        var sourceCount = CountQueuedReportSources(item.EntityId);
        if (sourceCount == 0 || sources.Count < sourceCount)
        {
            throw new InvalidOperationException(SyncFailureMessages.ReportSourceDependencyNotSynced);
        }

        var response = await serverClient.SaveReportAsync(
            new ServerReportSaveRequest
            {
                IdempotencyKey = item.IdempotencyKey,
                ReportType = "field_review",
                Title = document.Title,
                Summary = document.LatestComment,
                AnalysisContent = content,
                Sources = sources,
                SaveAsDocument = true,
                DocumentTitle = document.Title,
                DocumentStatus = document.Status
            },
            cancellationToken);

        LinkReportDocumentToServer(item, document, response, DateTime.UtcNow);
    }

    private DocumentRecord? LoadDocument(string documentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, document_id, folder_id, title, file_name, document_type, status, created_by,
                   created_at, updated_at, local_path, version_no, latest_comment, published_version_no
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
            TagService.ListDocumentTags(connection, documentId),
            reader.IsDBNull(13) ? null : reader.GetInt32(13));
    }

    private DocumentVersionRecord? LoadDocumentVersion(string documentId, int versionNo)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, document_id, version_no, file_name, local_path, comment, created_by, created_at,
                   version_status, is_latest, is_published, published_at, version_label
            FROM document_versions
            WHERE document_id = $document_id AND version_no = $version_no
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$document_id", documentId);
        command.Parameters.AddWithValue("$version_no", versionNo);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return null;
        }

        return new DocumentVersionRecord(
            reader.GetInt64(0),
            reader.GetString(1),
            reader.GetInt32(2),
            reader.GetString(3),
            reader.IsDBNull(4) ? null : reader.GetString(4),
            reader.IsDBNull(5) ? null : reader.GetString(5),
            reader.GetString(6),
            DateTime.Parse(reader.GetString(7)),
            reader.GetString(8),
            reader.GetInt32(9) == 1,
            reader.GetInt32(10) == 1,
            reader.IsDBNull(11) ? null : DateTime.Parse(reader.GetString(11)),
            reader.IsDBNull(12) ? null : reader.GetString(12));
    }

    private async Task<ServerDocumentVersionResponse?> TryFindServerVersionByNumberAsync(
        FlowNoteServerDocumentClient serverClient,
        string serverDocumentId,
        int versionNo,
        CancellationToken cancellationToken)
    {
        var versions = await serverClient.ListVersionsAsync(serverDocumentId, cancellationToken);
        return versions.FirstOrDefault(version => version.VersionNo == versionNo);
    }

    private void MarkDocumentVersionSynced(
        QueueItem item,
        DocumentRecord document,
        DocumentVersionRecord version,
        string serverDocumentId,
        string? serverVersionId,
        DateTime syncedAt)
    {
        using var connection = database.OpenConnection();
        using var update = connection.CreateCommand();
        update.CommandText = """
            UPDATE document_versions
            SET server_version_id = $server_version_id,
                synced_at = $synced_at
            WHERE document_id = $document_id AND version_no = $version_no;

            UPDATE documents
            SET server_document_id = $server_document_id,
                server_version_id = CASE WHEN version_no = $version_no THEN $server_version_id ELSE server_version_id END,
                synced_at = $synced_at
            WHERE document_id = $document_id;
            """;
        update.Parameters.AddWithValue("$server_document_id", serverDocumentId);
        update.Parameters.AddWithValue("$server_version_id", string.IsNullOrWhiteSpace(serverVersionId) ? DBNull.Value : serverVersionId);
        update.Parameters.AddWithValue("$synced_at", syncedAt.ToString("O"));
        update.Parameters.AddWithValue("$document_id", document.DocumentId);
        update.Parameters.AddWithValue("$version_no", version.VersionNo);
        update.ExecuteNonQuery();

        UpsertMapping(connection, "document_version", document.DocumentId, version.VersionNo, serverDocumentId, serverVersionId, null, null, null, syncedAt);
        if (version.IsLatest || document.VersionNo == version.VersionNo)
        {
            UpsertMapping(connection, "document", document.DocumentId, 0, serverDocumentId, serverVersionId, null, null, null, syncedAt);
        }

        MarkQueueSynced(connection, item.Id, serverDocumentId, serverVersionId, null, null, syncedAt);
        RecordSyncHistory(connection, "server_sync.succeeded", "document_version", document.DocumentId, $"Server document version synced: {serverDocumentId} v{version.VersionNo}", syncedAt);
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

    private IReadOnlyList<ServerReportSourceRequest> MapQueuedReportSources(string localReportDocumentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT source_type, local_source_id, source_version_id, relation_type
            FROM report_sources
            WHERE local_report_document_id = $document_id
            ORDER BY id;
            """;
        command.Parameters.AddWithValue("$document_id", localReportDocumentId);

        using var reader = command.ExecuteReader();
        var sources = new List<ServerReportSourceRequest>();
        while (reader.Read())
        {
            var localSource = new LocalReportSource(
                reader.GetString(0),
                reader.GetString(1),
                reader.IsDBNull(2) ? null : reader.GetString(2),
                reader.IsDBNull(3) ? null : reader.GetString(3));
            if (TryMapQueuedReportSource(connection, localSource) is { } mapped)
            {
                sources.Add(mapped);
            }
        }

        return sources;
    }

    private int CountQueuedReportSources(string localReportDocumentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT COUNT(*)
            FROM report_sources
            WHERE local_report_document_id = $document_id;
            """;
        command.Parameters.AddWithValue("$document_id", localReportDocumentId);
        return Convert.ToInt32(command.ExecuteScalar());
    }

    private static ServerReportSourceRequest? TryMapQueuedReportSource(
        SqliteConnection connection,
        LocalReportSource source)
    {
        var sourceType = Clean(source.SourceType)?.ToUpperInvariant();
        var sourceId = Clean(source.LocalSourceId);
        if (sourceType is null || sourceId is null)
        {
            return null;
        }

        return sourceType switch
        {
            "FIELD_COMMENT" => TryMapQueuedFieldCommentSource(connection, source, sourceId),
            "DOCUMENT" => TryMapQueuedDocumentSource(connection, source, sourceId),
            "WORK_SEQUENCE_ITEM" => TryMapQueuedLocalOnlySource(connection, "work_sequence_items", "item_id", source, sourceId),
            "WORK_SEQUENCE_HISTORY" => TryMapQueuedLocalOnlySource(connection, "work_sequence_change_history", "change_id", source, sourceId),
            "WORK_RECORD" or "WORK_RECORD_VERSION" => CreateQueuedReportSource(source, sourceType, sourceId),
            _ => null
        };
    }

    private static ServerReportSourceRequest? TryMapQueuedFieldCommentSource(
        SqliteConnection connection,
        LocalReportSource source,
        string sourceId)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT server_comment_id
            FROM field_comments
            WHERE comment_id = $comment_id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$comment_id", sourceId);
        var value = command.ExecuteScalar();
        if (value is null)
        {
            return CreateQueuedReportSource(source, "FIELD_COMMENT", sourceId);
        }

        var serverCommentId = value is DBNull ? null : Convert.ToString(value);
        return string.IsNullOrWhiteSpace(serverCommentId)
            ? null
            : CreateQueuedReportSource(source, "FIELD_COMMENT", serverCommentId);
    }

    private static ServerReportSourceRequest? TryMapQueuedDocumentSource(
        SqliteConnection connection,
        LocalReportSource source,
        string sourceId)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT server_document_id, server_version_id
            FROM documents
            WHERE document_id = $document_id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$document_id", sourceId);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return CreateQueuedReportSource(source, "DOCUMENT", sourceId, source.SourceVersionId);
        }

        var serverDocumentId = reader.IsDBNull(0) ? null : reader.GetString(0);
        if (string.IsNullOrWhiteSpace(serverDocumentId))
        {
            return null;
        }

        var serverVersionId = reader.IsDBNull(1) ? source.SourceVersionId : reader.GetString(1);
        return CreateQueuedReportSource(source, "DOCUMENT", serverDocumentId, serverVersionId);
    }

    private static ServerReportSourceRequest? TryMapQueuedLocalOnlySource(
        SqliteConnection connection,
        string tableName,
        string idColumn,
        LocalReportSource source,
        string sourceId)
    {
        using var command = connection.CreateCommand();
        command.CommandText = $"SELECT 1 FROM {tableName} WHERE {idColumn} = $source_id LIMIT 1;";
        command.Parameters.AddWithValue("$source_id", sourceId);
        var value = command.ExecuteScalar();
        return value is null
            ? CreateQueuedReportSource(source, source.SourceType.ToUpperInvariant(), sourceId, source.SourceVersionId)
            : null;
    }

    private static ServerReportSourceRequest CreateQueuedReportSource(
        LocalReportSource source,
        string sourceType,
        string sourceId,
        string? sourceVersionId = null)
    {
        return new ServerReportSourceRequest
        {
            SourceType = sourceType,
            SourceId = sourceId,
            SourceVersionId = Clean(sourceVersionId) ?? Clean(source.SourceVersionId),
            RelationType = Clean(source.RelationType) ?? DefaultReportRelationType(sourceType)
        };
    }

    private static string DefaultReportRelationType(string sourceType)
    {
        return sourceType switch
        {
            "FIELD_COMMENT" => "primary",
            "DOCUMENT" => "related_document",
            "WORK_SEQUENCE_ITEM" => "work_sequence",
            "WORK_SEQUENCE_HISTORY" => "work_sequence_history",
            "WORK_RECORD" => "work_record",
            "WORK_RECORD_VERSION" => "work_record_version",
            _ => "related"
        };
    }

    private void LinkReportDocumentToServer(
        QueueItem item,
        DocumentRecord document,
        ServerReportResponse savedReport,
        DateTime syncedAt)
    {
        var generatedDocument = savedReport.GeneratedDocument;
        var serverDocumentId = savedReport.GeneratedDocumentId;
        var serverVersionId = generatedDocument?.LatestVersionId ?? generatedDocument?.PublishedVersionId;

        using var connection = database.OpenConnection();
        using var update = connection.CreateCommand();
        update.CommandText = """
            UPDATE documents
            SET server_report_id = $server_report_id,
                server_document_id = $server_document_id,
                server_version_id = $server_version_id,
                synced_at = $synced_at
            WHERE document_id = $document_id;

            UPDATE document_versions
            SET server_version_id = $server_version_id,
                synced_at = $synced_at
            WHERE document_id = $document_id AND is_latest = 1;
            """;
        update.Parameters.AddWithValue("$server_report_id", savedReport.ReportId);
        update.Parameters.AddWithValue("$server_document_id", string.IsNullOrWhiteSpace(serverDocumentId) ? DBNull.Value : serverDocumentId);
        update.Parameters.AddWithValue("$server_version_id", string.IsNullOrWhiteSpace(serverVersionId) ? DBNull.Value : serverVersionId);
        update.Parameters.AddWithValue("$synced_at", syncedAt.ToString("O"));
        update.Parameters.AddWithValue("$document_id", document.DocumentId);
        update.ExecuteNonQuery();

        UpsertMapping(connection, "document", document.DocumentId, 0, serverDocumentId, serverVersionId, null, null, null, syncedAt, savedReport.ReportId);
        UpsertMapping(connection, "document_version", document.DocumentId, 1, serverDocumentId, serverVersionId, null, null, null, syncedAt, savedReport.ReportId);
        UpsertMapping(connection, "report", document.DocumentId, 0, serverDocumentId, serverVersionId, null, null, null, syncedAt, savedReport.ReportId);
        MarkQueueSynced(connection, item.Id, serverDocumentId, serverVersionId, null, null, syncedAt, serverReportId: savedReport.ReportId);
        RecordSyncHistory(connection, "server_sync.succeeded", "report", document.DocumentId, $"Server report synced: {savedReport.ReportId} / {serverDocumentId}", syncedAt);
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

    private DocumentServerMapping? TryGetDocumentVersionServerMapping(string documentId, int versionNo)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT document.server_document_id, version.server_version_id
            FROM document_versions AS version
            JOIN documents AS document ON document.document_id = version.document_id
            WHERE version.document_id = $document_id
              AND version.version_no = $version_no
              AND document.server_document_id IS NOT NULL
              AND version.server_version_id IS NOT NULL
              AND version.synced_at IS NOT NULL
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$document_id", documentId);
        command.Parameters.AddWithValue("$version_no", versionNo);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return TryGetServerIdMapping("document_version", documentId, versionNo);
        }

        return new DocumentServerMapping(
            reader.IsDBNull(0) ? null : reader.GetString(0),
            reader.IsDBNull(1) ? null : reader.GetString(1));
    }

    private DocumentServerMapping? TryGetServerIdMapping(string entityType, string localId, int localVersionNo)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT server_document_id, server_version_id
            FROM server_id_mappings
            WHERE entity_type = $entity_type
              AND local_id = $local_id
              AND local_version_no = $local_version_no
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$entity_type", entityType);
        command.Parameters.AddWithValue("$local_id", localId);
        command.Parameters.AddWithValue("$local_version_no", localVersionNo);
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

    private ReportServerMapping? TryGetReportServerMapping(string localReportDocumentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT server_report_id, server_document_id, server_version_id
            FROM documents
            WHERE document_id = $document_id
              AND server_report_id IS NOT NULL
              AND synced_at IS NOT NULL
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$document_id", localReportDocumentId);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return TryGetReportServerIdMapping(localReportDocumentId);
        }

        return new ReportServerMapping(
            reader.IsDBNull(0) ? null : reader.GetString(0),
            reader.IsDBNull(1) ? null : reader.GetString(1),
            reader.IsDBNull(2) ? null : reader.GetString(2));
    }

    private ReportServerMapping? TryGetReportServerIdMapping(string localReportDocumentId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT server_report_id, server_document_id, server_version_id
            FROM server_id_mappings
            WHERE entity_type = 'report'
              AND local_id = $local_id
              AND local_version_no = 0
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$local_id", localReportDocumentId);
        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return null;
        }

        return new ReportServerMapping(
            reader.IsDBNull(0) ? null : reader.GetString(0),
            reader.IsDBNull(1) ? null : reader.GetString(1),
            reader.IsDBNull(2) ? null : reader.GetString(2));
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

    private void MarkLatestFailure(string entityType, string entityId, string reason, bool countAttempt = false)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            UPDATE server_sync_queue
            SET status = CASE WHEN status = 'SYNCED' THEN status ELSE 'FAILED' END,
                last_error = CASE WHEN status = 'SYNCED' THEN last_error ELSE $last_error END,
                attempt_count = CASE
                    WHEN status = 'SYNCED' OR $count_attempt = 0 THEN attempt_count
                    ELSE attempt_count + 1
                END,
                last_attempt_at = CASE
                    WHEN status = 'SYNCED' OR $count_attempt = 0 THEN last_attempt_at
                    ELSE $last_attempt_at
                END
            WHERE id = (
                SELECT id
                FROM server_sync_queue
                WHERE entity_type = $entity_type AND entity_id = $entity_id
                ORDER BY id DESC
                LIMIT 1
            );
            """;
        command.Parameters.AddWithValue("$last_error", reason);
        command.Parameters.AddWithValue("$count_attempt", countAttempt ? 1 : 0);
        command.Parameters.AddWithValue("$last_attempt_at", DateTime.UtcNow.ToString("O"));
        command.Parameters.AddWithValue("$entity_type", entityType);
        command.Parameters.AddWithValue("$entity_id", entityId);
        command.ExecuteNonQuery();
        RecordSyncHistory(connection, "server_sync.failed", entityType, entityId, reason, DateTime.UtcNow);
    }

    private void MarkDependencyHold(QueueItem item, string reason)
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
        string? serverAttachmentId = null,
        string? serverReportId = null)
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
            serverAttachmentId,
            serverReportId);
    }

    private static void MarkQueueSynced(
        SqliteConnection connection,
        long queueId,
        string? serverDocumentId,
        string? serverVersionId,
        string? serverCommentId,
        string? serverLogId,
        DateTime syncedAt,
        string? serverAttachmentId = null,
        string? serverReportId = null)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            UPDATE server_sync_queue
            SET status = 'SYNCED',
                last_error = NULL,
                synced_at = $synced_at,
                server_document_id = $server_document_id,
                server_version_id = $server_version_id,
                server_report_id = $server_report_id,
                server_comment_id = $server_comment_id,
                server_attachment_id = $server_attachment_id,
                server_log_id = $server_log_id
            WHERE id = $id;
            """;
        command.Parameters.AddWithValue("$synced_at", syncedAt.ToString("O"));
        command.Parameters.AddWithValue("$server_document_id", string.IsNullOrWhiteSpace(serverDocumentId) ? DBNull.Value : serverDocumentId);
        command.Parameters.AddWithValue("$server_version_id", string.IsNullOrWhiteSpace(serverVersionId) ? DBNull.Value : serverVersionId);
        command.Parameters.AddWithValue("$server_report_id", string.IsNullOrWhiteSpace(serverReportId) ? DBNull.Value : serverReportId);
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
        string? serverAttachmentId,
        string? serverReportId = null)
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
            serverAttachmentId,
            serverReportId);
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
        DateTime syncedAt,
        string? serverReportId = null)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            INSERT INTO server_id_mappings (
                entity_type,
                local_id,
                local_version_no,
                server_document_id,
                server_version_id,
                server_report_id,
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
                $server_report_id,
                $server_comment_id,
                $server_attachment_id,
                $server_log_id,
                $synced_at
            )
            ON CONFLICT(entity_type, local_id, local_version_no) DO UPDATE SET
                server_document_id = excluded.server_document_id,
                server_version_id = excluded.server_version_id,
                server_report_id = excluded.server_report_id,
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
        command.Parameters.AddWithValue("$server_report_id", string.IsNullOrWhiteSpace(serverReportId) ? DBNull.Value : serverReportId);
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
            FlowNoteServerAuthenticationException => SyncFailureMessages.AuthenticationExpired,
            TaskCanceledException => SyncFailureMessages.ServerTimeout,
            HttpRequestException => SyncFailureMessages.ServerConnectionFailed,
            InvalidOperationException invalidOperation => TranslateFailureReason(invalidOperation.Message),
            _ => TranslateFailureReason(exception.Message)
        };

        if (string.IsNullOrWhiteSpace(message))
        {
            message = exception.GetType().Name;
        }

        message = message.Replace(Environment.NewLine, " ");
        const int maxLength = 300;
        return message.Length <= maxLength ? message : $"{message[..maxLength]}...";
    }

    private static string TranslateFailureReason(string? message)
    {
        if (string.IsNullOrWhiteSpace(message))
        {
            return "서버 전송 실패 사유를 확인할 수 없습니다. 서버 URL, 로그인 상태, 네트워크 상태를 확인한 뒤 재시도하세요.";
        }

        if (message.Contains("Server URL is not configured", StringComparison.OrdinalIgnoreCase))
        {
            return SyncFailureMessages.ServerUrlNotConfigured;
        }

        if (message.Contains("Server login expired", StringComparison.OrdinalIgnoreCase) ||
            message.Contains("Sign in again", StringComparison.OrdinalIgnoreCase) ||
            message.Contains("Unauthorized", StringComparison.OrdinalIgnoreCase))
        {
            return SyncFailureMessages.AuthenticationExpired;
        }

        if (message.Contains("Server response timeout", StringComparison.OrdinalIgnoreCase) ||
            message.Contains("timed out", StringComparison.OrdinalIgnoreCase))
        {
            return SyncFailureMessages.ServerTimeout;
        }

        if (message.Contains("Server connection failed", StringComparison.OrdinalIgnoreCase) ||
            message.Contains("connection", StringComparison.OrdinalIgnoreCase))
        {
            return SyncFailureMessages.ServerConnectionFailed;
        }

        if (message.Contains("Local document is not synced to server yet", StringComparison.OrdinalIgnoreCase))
        {
            return SyncFailureMessages.DocumentDependencyNotSynced;
        }

        if (message.Contains("Local document version is not synced to server yet", StringComparison.OrdinalIgnoreCase))
        {
            return SyncFailureMessages.DocumentVersionDependencyNotSynced;
        }

        if (message.Contains("Local document publish version server id is not confirmed yet", StringComparison.OrdinalIgnoreCase))
        {
            return SyncFailureMessages.DocumentPublishVersionNotConfirmed;
        }

        if (message.Contains("Local document status is PUBLISHED but no published version is selected", StringComparison.OrdinalIgnoreCase) ||
            message.Contains("Document cannot be set to PUBLISHED without a published version", StringComparison.OrdinalIgnoreCase))
        {
            return SyncFailureMessages.PublishedStatusMissingPublishedVersion;
        }

        if (message.Contains("Local document status is PUBLISHED but published version mapping is not synced to server yet", StringComparison.OrdinalIgnoreCase))
        {
            return SyncFailureMessages.PublishedStatusPublishMappingNotSynced;
        }

        if (message.Contains("Local field comment is not synced to server yet", StringComparison.OrdinalIgnoreCase))
        {
            return SyncFailureMessages.FieldCommentDependencyNotSynced;
        }

        if (message.Contains("No selected report source is linked to a server id", StringComparison.OrdinalIgnoreCase))
        {
            return SyncFailureMessages.ReportSourceDependencyNotSynced;
        }

        if (message.Contains("Unsupported sync action: register_field_note_attachment", StringComparison.OrdinalIgnoreCase))
        {
            return SyncFailureMessages.LegacyFieldNoteAttachmentUnsupported;
        }

        if (message.Contains("Unsupported sync action: register_field_note", StringComparison.OrdinalIgnoreCase))
        {
            return SyncFailureMessages.LegacyFieldNoteUnsupported;
        }

        if (message.Contains("Unsupported legacy create sync action", StringComparison.OrdinalIgnoreCase))
        {
            return SyncFailureMessages.LegacyCreateActionUnsupported;
        }

        if (message.Contains("Local document file not found", StringComparison.OrdinalIgnoreCase) ||
            message.Contains("Local field comment attachment file not found", StringComparison.OrdinalIgnoreCase) ||
            message.Contains("Local report document file not found", StringComparison.OrdinalIgnoreCase))
        {
            return SyncFailureMessages.LocalFileMissing;
        }

        return message.Replace(Environment.NewLine, " ").Trim();
    }

    private static bool IsServerVersionConflict(InvalidOperationException exception)
    {
        var message = exception.Message;
        return message.Contains("409", StringComparison.OrdinalIgnoreCase) &&
            (message.Contains("Document version could not be saved", StringComparison.OrdinalIgnoreCase) ||
             message.Contains("database constraint", StringComparison.OrdinalIgnoreCase) ||
             message.Contains("uq_document_versions_document_version", StringComparison.OrdinalIgnoreCase));
    }

    private static class SyncFailureMessages
    {
        public const string ServerUrlNotConfigured = "서버 URL이 설정되지 않아 전송하지 못했습니다. 설정 화면에서 서버 URL을 입력한 뒤 동기화 큐에서 재시도하세요. 로컬 데이터는 삭제되지 않습니다.";
        public const string ServerConnectionFailed = "서버에 연결하지 못했습니다. 서버 PC가 실행 중인지, 서버 URL과 네트워크 연결이 올바른지 확인한 뒤 재시도하세요. 로컬 데이터는 삭제되지 않습니다.";
        public const string ServerTimeout = "서버 응답 시간이 초과되었습니다. 네트워크 상태와 서버 부하를 확인한 뒤 동기화 큐에서 재시도하세요. 로컬 데이터는 삭제되지 않습니다.";
        public const string AuthenticationExpired = "로그인이 만료되었거나 서버 인증이 해제되었습니다. 다시 로그인하세요. 로컬 데이터는 삭제되지 않습니다.";
        public const string DocumentDependencyNotSynced = "선행 문서가 아직 서버에 전송되지 않았습니다. 같은 문서의 문서 등록 항목을 먼저 동기화한 뒤 재시도하세요. 로컬 데이터는 삭제되지 않습니다.";
        public const string DocumentVersionDependencyNotSynced = "선행 문서 버전이 아직 서버에 전송되지 않았습니다. 같은 문서의 버전 전송 항목을 먼저 동기화한 뒤 재시도하세요. 로컬 데이터는 삭제되지 않습니다.";
        public const string DocumentPublishVersionNotConfirmed = "공개할 서버 버전 ID가 아직 확인되지 않아 공개 전송을 실행하지 않았습니다. 같은 문서의 버전 전송 항목을 먼저 동기화한 뒤 공개 큐를 재시도하세요. 로컬 데이터는 삭제되지 않습니다.";
        public const string PublishedStatusMissingPublishedVersion = "문서 상태가 PUBLISHED이지만 로컬 공개 버전이 지정되지 않았습니다. 먼저 공개할 버전을 선택하고 공개 큐를 동기화한 뒤 상태 변경을 재시도하세요. 로컬 데이터는 삭제되지 않습니다.";
        public const string PublishedStatusPublishMappingNotSynced = "문서 상태가 PUBLISHED이지만 공개 버전의 서버 매핑이 없습니다. 공개 큐가 SYNCED가 된 뒤 상태 변경 큐를 재시도하세요. 로컬 데이터는 삭제되지 않습니다.";
        public const string FieldCommentDependencyNotSynced = "선행 FieldComment가 아직 서버에 전송되지 않았습니다. FieldComment 항목을 먼저 동기화한 뒤 첨부 전송을 재시도하세요. 로컬 데이터는 삭제되지 않습니다.";
        public const string ReportSourceDependencyNotSynced = "보고서 근거 중 서버 ID가 확인되지 않은 항목이 있어 서버 보고서를 저장하지 못했습니다. 근거 문서, FieldComment, 작업순서 이력을 먼저 서버에 등록한 뒤 재시도하세요. 로컬 보고서 문서는 삭제되지 않습니다.";
        public const string LocalFileMissing = "로컬 파일을 찾을 수 없어 서버로 전송하지 못했습니다. 문서 파일 위치를 확인한 뒤 재시도하세요. 로컬 데이터는 삭제되지 않습니다.";
        public const string LegacyFieldNoteUnsupported = "구 FieldNote 큐는 현재 FieldComment 동기화 대상이 아니어서 자동 전송하지 않았습니다. 관리자 검토 후 FieldComment 전환 또는 별도 마이그레이션으로 정리하세요. 로컬 데이터는 삭제되지 않습니다.";
        public const string LegacyFieldNoteAttachmentUnsupported = "구 FieldNote 첨부 큐는 현재 FieldComment 첨부 동기화 대상이 아니어서 자동 전송하지 않았습니다. 관리자 검토 후 FieldComment 첨부로 전환하거나 별도 마이그레이션으로 정리하세요. 로컬 데이터는 삭제되지 않습니다.";
        public const string LegacyCreateActionUnsupported = "구 형식 create 큐는 현재 서버 동기화 계약의 자동 전송 대상이 아닙니다. 원본 이력은 보존하고 관리자 검토 후 현재 action으로 별도 마이그레이션하세요. 서버 호출과 시도 횟수 증가는 수행하지 않았으며 로컬 데이터는 삭제되지 않습니다.";
    }

    private string? GetDependencyHoldReason(QueueItem item)
    {
        if (string.Equals(item.Action, "create", StringComparison.OrdinalIgnoreCase))
        {
            return SyncFailureMessages.LegacyCreateActionUnsupported;
        }

        switch (item.Action)
        {
            case "register_document":
                return GetDocumentFileHoldReason(item.EntityId, null);

            case "register_document_version":
                if (TryGetDocumentServerMapping(item.EntityId)?.ServerDocumentId is null)
                {
                    return SyncFailureMessages.DocumentDependencyNotSynced;
                }

                return GetDocumentFileHoldReason(item.EntityId, item.LocalVersionNo);

            case "publish_document_version":
                if (TryGetDocumentServerMapping(item.EntityId)?.ServerDocumentId is null)
                {
                    return SyncFailureMessages.DocumentDependencyNotSynced;
                }

                return item.LocalVersionNo is null ||
                    TryGetDocumentVersionServerMapping(item.EntityId, item.LocalVersionNo.Value)?.ServerVersionId is null
                    ? SyncFailureMessages.DocumentPublishVersionNotConfirmed
                    : null;

            case "update_document_status":
                var document = LoadDocument(item.EntityId);
                if (document is null)
                {
                    return null;
                }

                if (TryGetDocumentServerMapping(item.EntityId)?.ServerDocumentId is null)
                {
                    return SyncFailureMessages.DocumentDependencyNotSynced;
                }

                if (!string.Equals(document.Status, "PUBLISHED", StringComparison.Ordinal))
                {
                    return null;
                }

                if (document.PublishedVersionNo is null)
                {
                    return SyncFailureMessages.PublishedStatusMissingPublishedVersion;
                }

                return TryGetServerIdMapping("document_publish", item.EntityId, document.PublishedVersionNo.Value)?.ServerVersionId is null
                    ? SyncFailureMessages.PublishedStatusPublishMappingNotSynced
                    : null;

            case "register_field_comment":
                var fieldComment = LoadFieldComment(item.EntityId);
                if (fieldComment?.DocumentId is null)
                {
                    return null;
                }

                var fieldCommentDocumentMapping = fieldComment.DocumentVersionNo is null
                    ? TryGetDocumentServerMapping(fieldComment.DocumentId)
                    : TryGetDocumentVersionServerMapping(fieldComment.DocumentId, fieldComment.DocumentVersionNo.Value)
                      ?? TryGetDocumentServerMapping(fieldComment.DocumentId);
                return fieldCommentDocumentMapping?.ServerDocumentId is null
                    ? SyncFailureMessages.DocumentDependencyNotSynced
                    : null;

            case "update_field_comment_review":
                return string.IsNullOrWhiteSpace(TryGetFieldCommentServerId(item.EntityId))
                    ? SyncFailureMessages.FieldCommentDependencyNotSynced
                    : null;

            case "register_field_comment_attachment":
                var attachment = LoadFieldCommentAttachment(item.EntityId);
                if (attachment is not null && string.IsNullOrWhiteSpace(TryGetFieldCommentServerId(attachment.CommentId)))
                {
                    return SyncFailureMessages.FieldCommentDependencyNotSynced;
                }

                return attachment is not null && !File.Exists(FlowNoteLocalDatabase.ResolveLocalContentPath(attachment.LocalPath))
                    ? SyncFailureMessages.LocalFileMissing
                    : null;

            case "register_access_log_started":
            case "register_access_log_closed":
            case "register_access_log_auto_closed":
            case "register_access_log_download_blocked":
                var accessLog = LoadAccessLog(item.EntityId);
                if (accessLog is null)
                {
                    return null;
                }

                var accessLogDocumentMapping = TryGetDocumentVersionServerMapping(accessLog.DocumentId, accessLog.VersionNo)
                    ?? TryGetDocumentServerMapping(accessLog.DocumentId);
                return accessLogDocumentMapping?.ServerDocumentId is null
                    ? SyncFailureMessages.DocumentDependencyNotSynced
                    : null;

            case "register_report":
                var reportSourceCount = CountQueuedReportSources(item.EntityId);
                if (reportSourceCount == 0)
                {
                    return SyncFailureMessages.ReportSourceDependencyNotSynced;
                }

                if (MapQueuedReportSources(item.EntityId).Count < reportSourceCount)
                {
                    return SyncFailureMessages.ReportSourceDependencyNotSynced;
                }

                return GetDocumentFileHoldReason(item.EntityId, null);

            case "register_field_note":
                return SyncFailureMessages.LegacyFieldNoteUnsupported;

            case "register_field_note_attachment":
                return SyncFailureMessages.LegacyFieldNoteAttachmentUnsupported;

            default:
                return null;
        }
    }

    private string? GetDocumentFileHoldReason(string documentId, int? versionNo)
    {
        var storedPath = versionNo is null
            ? LoadDocument(documentId)?.LocalPath
            : LoadDocumentVersion(documentId, versionNo.Value)?.LocalPath;
        if (string.IsNullOrWhiteSpace(storedPath))
        {
            return SyncFailureMessages.LocalFileMissing;
        }

        return File.Exists(FlowNoteLocalDatabase.ResolveLocalContentPath(storedPath))
            ? null
            : SyncFailureMessages.LocalFileMissing;
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

    private sealed record ReportServerMapping(string? ServerReportId, string? ServerDocumentId, string? ServerVersionId);

    private sealed record LocalReportSource(
        string SourceType,
        string LocalSourceId,
        string? SourceVersionId,
        string? RelationType);
}
