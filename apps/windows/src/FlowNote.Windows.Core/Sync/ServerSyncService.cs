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

public sealed partial class ServerSyncService(FlowNoteLocalDatabase database)
{
    private readonly ServerEpochGuardService epochGuard = new(database);
    private const string Pending = "PENDING";
    private const string Failed = "FAILED";
    private const string Synced = "SYNCED";
    private const string Conflict = "CONFLICT";
    private const string Discarded = "DISCARDED";

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

    public async Task<ServerSyncResult> QueueAndTrySyncDocumentTagsAsync(
        DocumentRecord document,
        FlowNoteServerDocumentClient? serverClient,
        string? serverUserId = null,
        CancellationToken cancellationToken = default)
    {
        EnqueueDocumentTags(document, null);
        if (serverClient is null)
        {
            MarkLatestFailure("document_tags", document.DocumentId, SyncFailureMessages.ServerUrlNotConfigured);
            return new ServerSyncResult(false, "서버 URL이 설정되지 않아 문서 태그 전송을 큐에 보관했습니다. 서버 설정 후 동기화 큐에서 재시도하세요.");
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
        string? reason = null,
        CancellationToken cancellationToken = default)
    {
        EnqueueAccessLog(accessLog, action, null, reason);
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
        ReportWorkflowContext? workflow = null,
        CancellationToken cancellationToken = default)
    {
        EnqueueReport(reportDocument, workflow, null);
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
        try
        {
            await epochGuard.EnsureReadyAsync(serverClient, cancellationToken: cancellationToken);
        }
        catch (ServerReconciliationRequiredException exception)
        {
            return new ServerSyncResult(
                false,
                $"서버 복구 경계가 감지되어 자동 전송을 중지했습니다. {exception.Message} 관리자 reconciliation 승인 전에는 서버 데이터가 변경되지 않습니다. 로컬 mapping, cursor, message_id와 큐는 보존됩니다.",
                Failed: 1);
        }
        catch (Exception exception) when (exception is HttpRequestException or TaskCanceledException or InvalidOperationException)
        {
            var reason = $"서버 sync manifest를 확인하지 못해 전송을 중지했습니다: {SummarizeFailure(exception)}";
            using var connection = database.OpenConnection();
            using var command = connection.CreateCommand();
            command.CommandText = """
                UPDATE server_sync_queue
                SET status = 'FAILED', last_error = $reason, last_attempt_at = $now
                WHERE status = 'PENDING';
                """;
            command.Parameters.AddWithValue("$reason", reason);
            command.Parameters.AddWithValue("$now", DateTime.UtcNow.ToString("O"));
            command.ExecuteNonQuery();
            return new ServerSyncResult(false, $"{reason} 로컬 데이터와 큐는 보존됩니다.", Failed: 1);
        }

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

            if (GetOperationalHoldReason(item) is { } operationalHoldReason)
            {
                held++;
                firstFailureReason ??= operationalHoldReason;
                MarkDependencyHold(item, operationalHoldReason);
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
                    case "replace_document_tags":
                        await SyncDocumentTagsAsync(item, serverClient, cancellationToken);
                        break;
                    case "register_field_comment":
                        await SyncFieldCommentAsync(item, serverClient, serverUserId, cancellationToken);
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
                    case "register_access_log_preview_failed":
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
            catch (FlowNoteServerConflictException exception)
            {
                failed++;
                var reason = $"{TranslateConflictCode(exception.ConflictCode)}: {exception.Message}";
                firstFailureReason ??= reason;
                var readBack = await TryReadConflictServerAuthorityAsync(
                    item,
                    serverClient,
                    cancellationToken);
                RecordConflict(item, exception, reason, readBack);
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
        var success = failed == 0 && held == 0 && metrics.QueueDepth == 0;
        var message = success
            ? $"서버 동기화 완료: 성공 {synced}건, 이미 처리 {skipped}건, 시도 {attempted}건. 남은 큐 {metrics.QueueDepth}건, 최장 대기 {metrics.OldestWaitingText}, 최근 1시간 처리 {metrics.SyncedLastHour}건."
            : $"서버 확인이 끝나지 않은 항목이 있습니다: 성공 {synced}건, 이미 처리 {skipped}건, 보류 {held}건, 실패/충돌 {failed}건, 시도 {attempted}건. 남은 큐 {metrics.QueueDepth}건, 최장 대기 {metrics.OldestWaitingText}, 실패 분포 {metrics.FailureDistributionText}. 첫 사유: {firstFailureReason ?? "기존 충돌 작업함을 확인하세요."} 동기화 큐 또는 충돌 작업함에서 조치한 뒤 재시도하세요. 서버 확인 전에는 동기화 완료가 아닙니다. 로컬 데이터는 삭제되지 않습니다.";
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
                   server_attachment_id, server_log_id, base_server_revision,
                   expected_server_version_id, expected_published_version_id,
                   local_file_hash_sha256, base_domain_revision, intent_hash, source_set_hash,
                   payload_json, conflict_code, conflict_details,
                   resolution_action, resolution_reason, resolved_by, resolved_at
                   ,server_conflict_hash_sha256, base_snapshot_hash_sha256,
                   server_read_back_json, allowed_actions_json,
                   source_preserved_path, retry_not_before
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
                reader.IsDBNull(19) ? null : reader.GetString(19),
                reader.IsDBNull(20) ? null : reader.GetInt32(20),
                reader.IsDBNull(21) ? null : reader.GetString(21),
                reader.IsDBNull(22) ? null : reader.GetString(22),
                reader.IsDBNull(23) ? null : reader.GetString(23),
                reader.IsDBNull(24) ? null : reader.GetInt32(24),
                reader.IsDBNull(25) ? null : reader.GetString(25),
                reader.IsDBNull(26) ? null : reader.GetString(26),
                reader.IsDBNull(27) ? null : reader.GetString(27),
                reader.IsDBNull(28) ? null : reader.GetString(28),
                reader.IsDBNull(29) ? null : reader.GetString(29),
                reader.IsDBNull(30) ? null : reader.GetString(30),
                reader.IsDBNull(31) ? null : reader.GetString(31),
                reader.IsDBNull(32) ? null : reader.GetString(32),
                reader.IsDBNull(33) ? null : DateTime.Parse(reader.GetString(33)),
                reader.IsDBNull(34) ? null : reader.GetString(34),
                reader.IsDBNull(35) ? null : reader.GetString(35),
                reader.IsDBNull(36) ? null : reader.GetString(36),
                reader.IsDBNull(37) ? null : reader.GetString(37),
                reader.IsDBNull(38) ? null : reader.GetString(38),
                reader.IsDBNull(39) ? null : DateTime.Parse(reader.GetString(39))));
        }

        return records;
    }

    public void DiscardConflict(long queueId, string resolvedBy, string reason, string resolvedRole)
    {
        DocumentConflictResolutionPolicy.ValidateResolution(resolvedBy, reason, resolvedRole);

        var now = DateTime.UtcNow;
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            UPDATE server_sync_queue
            SET status = 'DISCARDED',
                resolution_action = 'KEEP_SERVER',
                resolution_reason = $reason,
                resolved_by = $resolved_by,
                resolved_at = $resolved_at
            WHERE id = $id AND status = 'CONFLICT';
            """;
        command.Parameters.AddWithValue("$reason", reason.Trim());
        command.Parameters.AddWithValue("$resolved_by", resolvedBy.Trim());
        command.Parameters.AddWithValue("$resolved_at", now.ToString("O"));
        command.Parameters.AddWithValue("$id", queueId);
        if (command.ExecuteNonQuery() != 1)
        {
            throw new InvalidOperationException("선택한 항목은 현재 해결 가능한 충돌 상태가 아닙니다.");
        }
        RecordSyncHistory(connection, "server_sync.conflict_discarded", "server_sync_queue", queueId.ToString(), $"서버본 유지로 로컬 요청을 폐기했습니다. 사유: {reason.Trim()}", now);
    }

    public async Task<ServerSyncResult> RetryConflictUsingLatestServerAsync(
        long queueId,
        FlowNoteServerDocumentClient serverClient,
        string resolvedBy,
        string reason,
        string resolvedRole,
        string? serverUserId = null,
        CancellationToken cancellationToken = default)
    {
        DocumentConflictResolutionPolicy.ValidateResolution(resolvedBy, reason, resolvedRole);

        string localDocumentId;
        string serverDocumentId;
        string action;
        string? payloadJson;
        string? allowedActionsJson;
        DateTime? retryNotBefore;
        using (var connection = database.OpenConnection())
        using (var lookup = connection.CreateCommand())
        {
            lookup.CommandText = """
                SELECT COALESCE(queue.local_document_id, queue.entity_id),
                       document.server_document_id, queue.action, queue.payload_json,
                       queue.allowed_actions_json, queue.retry_not_before
                FROM server_sync_queue AS queue
                JOIN documents AS document
                  ON document.document_id = COALESCE(queue.local_document_id, queue.entity_id)
                WHERE queue.id = $id AND queue.status = 'CONFLICT'
                LIMIT 1;
                """;
            lookup.Parameters.AddWithValue("$id", queueId);
            using var reader = lookup.ExecuteReader();
            if (!reader.Read() || reader.IsDBNull(1))
            {
                throw new InvalidOperationException("충돌 항목의 서버 문서 ID를 확인할 수 없습니다.");
            }
            localDocumentId = reader.GetString(0);
            serverDocumentId = reader.GetString(1);
            action = reader.GetString(2);
            payloadJson = reader.IsDBNull(3) ? null : reader.GetString(3);
            allowedActionsJson = reader.IsDBNull(4) ? null : reader.GetString(4);
            retryNotBefore = reader.IsDBNull(5) ? null : DateTime.Parse(reader.GetString(5));
        }

        if (!DocumentConflictResolutionPolicy.Contains(
                allowedActionsJson,
                DocumentConflictResolutionPolicy.RetryWithLatest))
        {
            throw new InvalidOperationException("이 충돌은 최신 서버값 기준 재요청이 허용되지 않습니다.");
        }
        if (retryNotBefore is not null && retryNotBefore > DateTime.UtcNow)
        {
            throw new InvalidOperationException(
                $"서버 read-back 불일치 보호 기간입니다. {retryNotBefore:yyyy-MM-dd HH:mm:ss} 이후 다시 확인하세요.");
        }

        var serverDocument = await serverClient.GetDocumentAsync(serverDocumentId, cancellationToken);
        string? rebasedIntentHash = null;
        string? rebasedPayloadJson = null;
        if (action == "replace_document_tags" && ReadTagsPayload(payloadJson) is { } tagPayload)
        {
            rebasedIntentHash = CreateDocumentTagIntentHash(
                serverDocumentId,
                serverDocument.Revision,
                tagPayload.AddedTags,
                tagPayload.RemovedTags);
            rebasedPayloadJson = JsonSerializer.Serialize(tagPayload with
            {
                BaseRevision = serverDocument.Revision,
                IntentHash = rebasedIntentHash,
                BaseTagsKnown = true,
                CanResolveBaseAfterDocumentRegistration = false
            });
        }
        var now = DateTime.UtcNow;
        using (var connection = database.OpenConnection())
        {
            using var transaction = connection.BeginTransaction();
            UpdateDocumentServerState(connection, localDocumentId, serverDocument, transaction);
            using var command = connection.CreateCommand();
            command.Transaction = transaction;
            command.CommandText = """
                UPDATE server_sync_queue
                SET status = 'PENDING',
                    last_error = NULL,
                    base_server_revision = $base_server_revision,
                    expected_server_version_id = $expected_server_version_id,
                    expected_published_version_id = $expected_published_version_id,
                    intent_hash = COALESCE($intent_hash, intent_hash),
                    payload_json = COALESCE($payload_json, payload_json),
                    resolution_action = 'RETRY_LOCAL_ON_LATEST',
                    resolution_reason = $reason,
                    resolved_by = $resolved_by,
                    resolved_at = $resolved_at
                WHERE id = $id AND status = 'CONFLICT';
                """;
            command.Parameters.AddWithValue("$base_server_revision", serverDocument.Revision);
            command.Parameters.AddWithValue("$expected_server_version_id", string.IsNullOrWhiteSpace(serverDocument.LatestVersionId) ? DBNull.Value : serverDocument.LatestVersionId);
            command.Parameters.AddWithValue("$expected_published_version_id", string.IsNullOrWhiteSpace(serverDocument.PublishedVersionId) ? DBNull.Value : serverDocument.PublishedVersionId);
            command.Parameters.AddWithValue("$intent_hash", string.IsNullOrWhiteSpace(rebasedIntentHash) ? DBNull.Value : rebasedIntentHash);
            command.Parameters.AddWithValue("$payload_json", string.IsNullOrWhiteSpace(rebasedPayloadJson) ? DBNull.Value : rebasedPayloadJson);
            command.Parameters.AddWithValue("$reason", reason.Trim());
            command.Parameters.AddWithValue("$resolved_by", resolvedBy.Trim());
            command.Parameters.AddWithValue("$resolved_at", now.ToString("O"));
            command.Parameters.AddWithValue("$id", queueId);
            if (command.ExecuteNonQuery() != 1)
            {
                throw new InvalidOperationException("충돌 상태가 변경되어 최신 목록을 다시 확인해야 합니다.");
            }
            RecordSyncHistory(connection, "server_sync.conflict_retry_selected", "server_sync_queue", queueId.ToString(), $"서버 revision {serverDocument.Revision}을 기준으로 로컬 변경 재시도를 선택했습니다. 사유: {reason.Trim()}", now, transaction);
            transaction.Commit();
        }

        return await RetryPendingAsync(serverClient, serverUserId, cancellationToken);
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
        var discarded = 0;
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
            failed += status is Failed or Conflict ? 1 : 0;
            synced += string.Equals(status, Synced, StringComparison.Ordinal) ? 1 : 0;
            discarded += string.Equals(status, Discarded, StringComparison.Ordinal) ? 1 : 0;
            held += diagnosis.IsDependencyHold && !string.Equals(status, Synced, StringComparison.Ordinal) ? 1 : 0;
        }

        return new ServerSyncQueueSummary(pending, failed, synced, held, discarded);
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
            if (status is Synced or Discarded)
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

            if (status is Failed or Conflict)
            {
                var diagnosis = ServerSyncQueueDiagnostics.Classify(
                    status,
                    reader.GetString(1),
                    reader.GetString(2),
                    reader.IsDBNull(3) ? null : TranslateFailureReason(reader.GetString(3)));
                failureReasons[diagnosis.Category] = failureReasons.GetValueOrDefault(diagnosis.Category) + 1;
            }
        }

        TimeSpan? oldestWaitingTime = oldestCreatedAt is null
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

}
