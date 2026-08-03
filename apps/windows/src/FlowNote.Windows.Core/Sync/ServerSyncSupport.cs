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
    private static FlowNoteServerConflictException LegacyBaseConflict(string message)
    {
        return new FlowNoteServerConflictException(
            "LEGACY_BASE_MISSING",
            message,
            null,
            null,
            null,
            null,
            null,
            $"{{\"detail\":{{\"code\":\"LEGACY_BASE_MISSING\",\"message\":\"{message}\"}}}}");
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
        string? serverReportId = null,
        SqliteTransaction? transaction = null)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
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
        string? serverReportId = null,
        int? serverRevision = null,
        string? serverFileHashSha256 = null,
        SqliteTransaction? transaction = null)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
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
                server_revision,
                server_file_hash_sha256,
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
                $server_revision,
                $server_file_hash_sha256,
                $synced_at
            )
            ON CONFLICT(entity_type, local_id, local_version_no) DO UPDATE SET
                server_document_id = excluded.server_document_id,
                server_version_id = excluded.server_version_id,
                server_report_id = excluded.server_report_id,
                server_comment_id = excluded.server_comment_id,
                server_attachment_id = excluded.server_attachment_id,
                server_log_id = excluded.server_log_id,
                server_revision = COALESCE(excluded.server_revision, server_id_mappings.server_revision),
                server_file_hash_sha256 = COALESCE(
                    excluded.server_file_hash_sha256,
                    server_id_mappings.server_file_hash_sha256),
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
        command.Parameters.AddWithValue("$server_revision", serverRevision is null ? DBNull.Value : serverRevision.Value);
        command.Parameters.AddWithValue("$server_file_hash_sha256", string.IsNullOrWhiteSpace(serverFileHashSha256) ? DBNull.Value : serverFileHashSha256);
        command.Parameters.AddWithValue("$synced_at", syncedAt.ToString("O"));
        command.ExecuteNonQuery();
    }

    private static void RecordSyncHistory(
        SqliteConnection connection,
        string eventType,
        string targetType,
        string targetId,
        string message,
        DateTime createdAt,
        SqliteTransaction? transaction = null)
    {
        HistoryService.Record(
            connection,
            eventType,
            "server-sync",
            targetType,
            targetId,
            null,
            message,
            createdAt,
            transaction);
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

            case "replace_document_tags":
                return TryGetDocumentServerMapping(item.EntityId)?.ServerDocumentId is null
                    ? SyncFailureMessages.DocumentDependencyNotSynced
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
            case "register_access_log_preview_failed":
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

    private static string? GetOperationalHoldReason(QueueItem item)
    {
        var diagnosis = ServerSyncQueueDiagnostics.Classify(
            Failed,
            item.EntityType,
            item.Action,
            item.LastError);
        if (diagnosis.Category == "서버 검증 거부")
        {
            return item.LastError;
        }

        return diagnosis.OperationalState == "재시도 가능" &&
            item.AttemptCount >= diagnosis.AutoRetryLimit
            ? $"자동 재시도 한도 {diagnosis.AutoRetryLimit}회에 도달했습니다. 마지막 오류를 확인하고 운영자가 수동 재시도 또는 승인 종결을 선택하세요. 기존 큐와 원천 데이터는 보존됩니다. 마지막 오류: {item.LastError}"
            : null;
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
            "preview_failed" or "register_access_log_preview_failed" => "register_access_log_preview_failed",
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
        string IdempotencyKey,
        int? BaseServerRevision,
        string? ExpectedServerVersionId,
        string? ExpectedPublishedVersionId,
        string? LocalFileHashSha256,
        int? BaseDomainRevision,
        string? IntentHash,
        string? SourceSetHash,
        string? PayloadJson,
        int AttemptCount,
        string? LastError);

    private sealed record DocumentStatusSyncPayload(string Status);

    private sealed record AccessLogSyncPayload(string Reason);

    private sealed record DocumentTagsSyncPayload(
        int BaseRevision,
        IReadOnlyList<string> AddedTags,
        IReadOnlyList<string> RemovedTags,
        string IntentHash,
        bool BaseTagsKnown,
        IReadOnlyList<string> DesiredTags,
        bool CanResolveBaseAfterDocumentRegistration);

    private sealed record FieldCommentReviewSyncPayload(
        string Status,
        string? NormalizedContent,
        string? AnalysisContent,
        string? AssignedTo,
        DateTime? ReviewDueAt,
        string? LastTransitionReason,
        bool ConflictFlag,
        string? ConflictBasis)
    {
        public static FieldCommentReviewSyncPayload From(FieldCommentRecord fieldComment) =>
            new(
                fieldComment.Status,
                fieldComment.NormalizedContent,
                fieldComment.AnalysisContent,
                fieldComment.AssignedTo,
                fieldComment.ReviewDueAt,
                fieldComment.LastTransitionReason,
                fieldComment.ConflictFlag,
                fieldComment.ConflictBasis);
    }

    private sealed record DocumentServerMapping(
        string? ServerDocumentId,
        string? ServerVersionId,
        int? ServerRevision = null,
        string? ServerPublishedVersionId = null,
        string? ServerFileHashSha256 = null);

    private sealed record DocumentSyncSnapshot(
        int? ServerRevision,
        string? ServerVersionId,
        string? ServerPublishedVersionId,
        string? LocalFileHashSha256);

    private sealed record DocumentTagBase(
        string? ServerDocumentId,
        int? ServerRevision,
        IReadOnlyList<string>? Tags);

    private sealed record ReportServerMapping(string? ServerReportId, string? ServerDocumentId, string? ServerVersionId);

    private sealed record LocalReportSource(
        string SourceType,
        string LocalSourceId,
        string? SourceVersionId,
        string? RelationType,
        int? SourceRevision,
        string? SourceHashSha256,
        bool SnapshotVerified);
}
