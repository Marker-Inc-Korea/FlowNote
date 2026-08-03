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
                server_revision = $server_revision,
                server_published_version_id = $server_published_version_id,
                server_tags_json = $server_tags_json,
                synced_at = $synced_at
            WHERE document_id = $document_id;

            UPDATE document_versions
            SET server_version_id = $server_version_id,
                synced_at = $synced_at
            WHERE document_id = $document_id AND version_no = 1;
            """;
        updateDocument.Parameters.AddWithValue("$server_document_id", response.DocumentId);
        updateDocument.Parameters.AddWithValue("$server_version_id", string.IsNullOrWhiteSpace(serverVersionId) ? DBNull.Value : serverVersionId);
        updateDocument.Parameters.AddWithValue("$server_revision", response.Revision);
        updateDocument.Parameters.AddWithValue("$server_published_version_id", string.IsNullOrWhiteSpace(response.PublishedVersionId) ? DBNull.Value : response.PublishedVersionId);
        updateDocument.Parameters.AddWithValue("$server_tags_json", JsonSerializer.Serialize(response.Tags));
        updateDocument.Parameters.AddWithValue("$synced_at", now.ToString("O"));
        updateDocument.Parameters.AddWithValue("$document_id", document.DocumentId);
        updateDocument.ExecuteNonQuery();

        var serverFileHash = response.LatestVersion?.File.HashSha256;
        UpsertMapping(connection, "document", document.DocumentId, 0, response.DocumentId, serverVersionId, null, null, null, now, serverRevision: response.Revision, serverFileHashSha256: serverFileHash);
        UpsertMapping(connection, "document_version", document.DocumentId, 1, response.DocumentId, serverVersionId, null, null, null, now, serverRevision: response.Revision, serverFileHashSha256: serverFileHash);
        MarkQueueSynced(connection, item.Id, response.DocumentId, serverVersionId, null, null, now);
        AdvanceDependentDocumentBases(connection, document.DocumentId, response);
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
        ServerDocumentVersionResponse? existingServerVersion = null;
        if (item.BaseServerRevision is null)
        {
            existingServerVersion = await TryFindServerVersionByNumberAsync(
                serverClient,
                documentMapping.ServerDocumentId,
                versionNo,
                cancellationToken);
        }
        if (existingServerVersion is not null)
        {
            if (!string.Equals(
                    existingServerVersion.File.HashSha256,
                    item.LocalFileHashSha256,
                    StringComparison.OrdinalIgnoreCase))
            {
                throw new FlowNoteServerConflictException(
                    "FILE_HASH_MISMATCH",
                    "같은 버전 번호의 서버 파일과 로컬 파일 SHA-256이 다릅니다.",
                    item.BaseServerRevision,
                    documentMapping.ServerRevision,
                    null,
                    existingServerVersion.VersionId,
                    documentMapping.ServerPublishedVersionId,
                    $"serverHash={existingServerVersion.File.HashSha256}; localHash={item.LocalFileHashSha256}");
            }
            var serverDocument = await serverClient.GetDocumentAsync(documentMapping.ServerDocumentId, cancellationToken);
            MarkDocumentVersionSynced(
                item,
                document,
                localVersion,
                documentMapping.ServerDocumentId,
                existingServerVersion.VersionId,
                serverDocument.Revision,
                serverDocument.PublishedVersionId,
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
                item.BaseServerRevision,
                item.ExpectedServerVersionId,
                item.LocalFileHashSha256,
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
                documentMapping.ServerRevision,
                documentMapping.ServerPublishedVersionId,
                DateTime.UtcNow);
            return;
        }

        var updatedServerDocument = await serverClient.GetDocumentAsync(response.DocumentId, cancellationToken);
        MarkDocumentVersionSynced(
            item,
            document,
            localVersion,
            response.DocumentId,
            response.VersionId,
            updatedServerDocument.Revision,
            updatedServerDocument.PublishedVersionId,
            DateTime.UtcNow);
    }

    private async Task SyncDocumentPublishAsync(
        QueueItem item,
        FlowNoteServerDocumentClient serverClient,
        CancellationToken cancellationToken)
    {
        var baseServerRevision = ReadCurrentBaseServerRevision(item);
        if (baseServerRevision is null)
        {
            throw LegacyBaseConflict("구 공개 큐에는 서버 기준 revision이 없어 자동 공개할 수 없습니다.");
        }
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
            baseServerRevision,
            item.ExpectedPublishedVersionId,
            item.IdempotencyKey,
            cancellationToken);
        var authoritative = await ReadBackDocumentAuthorityAsync(
            serverClient,
            response.DocumentId,
            expectedStatus: "PUBLISHED",
            expectedPublishedVersionId: versionMapping.ServerVersionId,
            expectedTags: null,
            cancellationToken);
        var publishedVersionId = authoritative.PublishedVersion?.VersionId
            ?? authoritative.PublishedVersionId
            ?? versionMapping.ServerVersionId;
        var now = DateTime.UtcNow;

        using var connection = database.OpenConnection();
        UpdateDocumentServerState(connection, document.DocumentId, authoritative);
        UpsertMapping(connection, "document_publish", document.DocumentId, versionNo, authoritative.DocumentId, publishedVersionId, null, null, null, now, serverRevision: authoritative.Revision);
        UpsertMapping(connection, "document", document.DocumentId, 0, authoritative.DocumentId, authoritative.LatestVersionId ?? documentMapping.ServerVersionId, null, null, null, now, serverRevision: authoritative.Revision);
        MarkQueueSynced(connection, item.Id, authoritative.DocumentId, publishedVersionId, null, null, now);
        AdvanceDependentDocumentBases(connection, document.DocumentId, authoritative);
        RecordSyncHistory(connection, "server_sync.succeeded", "document_publish", document.DocumentId, $"Server document publish synced and read back: {authoritative.DocumentId} v{versionNo} revision {authoritative.Revision}", now);
    }

    private async Task SyncDocumentStatusAsync(
        QueueItem item,
        FlowNoteServerDocumentClient serverClient,
        CancellationToken cancellationToken)
    {
        var baseServerRevision = ReadCurrentBaseServerRevision(item);
        if (baseServerRevision is null)
        {
            throw LegacyBaseConflict("구 상태 큐에는 서버 기준 revision이 없어 자동 상태 변경할 수 없습니다.");
        }
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

        var targetStatus = ReadStatusPayload(item.PayloadJson) ?? document.Status;
        var response = await serverClient.UpdateDocumentStatusAsync(
            documentMapping.ServerDocumentId,
            targetStatus,
            $"WPF local status sync: {targetStatus}",
            baseServerRevision,
            item.IdempotencyKey,
            cancellationToken);
        var authoritative = await ReadBackDocumentAuthorityAsync(
            serverClient,
            response.DocumentId,
            expectedStatus: targetStatus,
            expectedPublishedVersionId: targetStatus == "PUBLISHED"
                ? response.PublishedVersionId
                : null,
            expectedTags: null,
            cancellationToken);
        var now = DateTime.UtcNow;
        var serverVersionId = authoritative.LatestVersionId ?? documentMapping.ServerVersionId;

        using var connection = database.OpenConnection();
        UpdateDocumentServerState(connection, document.DocumentId, authoritative);
        UpsertMapping(connection, "document_status", document.DocumentId, item.LocalVersionNo ?? document.VersionNo, authoritative.DocumentId, serverVersionId, null, null, null, now, serverRevision: authoritative.Revision);
        UpsertMapping(connection, "document", document.DocumentId, 0, authoritative.DocumentId, serverVersionId, null, null, null, now, serverRevision: authoritative.Revision);
        MarkQueueSynced(connection, item.Id, authoritative.DocumentId, serverVersionId, null, null, now);
        AdvanceDependentDocumentBases(connection, document.DocumentId, authoritative);
        RecordSyncHistory(connection, "server_sync.succeeded", "document_status", document.DocumentId, $"Server document status synced and read back: {authoritative.DocumentId} {targetStatus} revision {authoritative.Revision}", now);
    }

    private async Task SyncFieldCommentAsync(
        QueueItem item,
        FlowNoteServerDocumentClient serverClient,
        string? serverUserId,
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
            cancellationToken,
            serverUserId);

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

        var serverComment = await serverClient.GetFieldCommentAsync(serverCommentId, cancellationToken);
        var baseRevision = ReadCurrentBaseDomainRevision(item) ?? serverComment.ReviewRevision;
        var payload = ParseFieldCommentReviewPayload(item.PayloadJson);
        var queuedFieldComment = payload is null
            ? fieldComment
            : fieldComment with
            {
                Status = payload.Status,
                NormalizedContent = payload.NormalizedContent,
                AnalysisContent = payload.AnalysisContent,
                AssignedTo = payload.AssignedTo,
                ReviewDueAt = payload.ReviewDueAt,
                LastTransitionReason = payload.LastTransitionReason,
                ConflictFlag = payload.ConflictFlag,
                ConflictBasis = payload.ConflictBasis
            };
        var request = ServerFieldCommentReviewRequest.FromLocal(
            queuedFieldComment,
            serverUserId,
            item.IdempotencyKey,
            baseRevision);
        var response = await serverClient.UpdateFieldCommentReviewAsync(
            serverCommentId,
            request,
            cancellationToken);

        var now = DateTime.UtcNow;
        using var connection = database.OpenConnection();
        using (var update = connection.CreateCommand())
        {
            update.CommandText = """
                UPDATE field_comments
                SET status = $status,
                    normalized_content = $normalized_content,
                    analysis_content = $analysis_content,
                    assigned_to = $assigned_to,
                    review_due_at = $review_due_at,
                    last_transition_reason = $transition_reason,
                    review_revision = $review_revision,
                    synced_at = $synced_at
                WHERE comment_id = $comment_id;
                """;
            update.Parameters.AddWithValue("$status", response.Status);
            update.Parameters.AddWithValue("$normalized_content", response.NormalizedContent ?? (object)DBNull.Value);
            update.Parameters.AddWithValue("$analysis_content", response.AnalysisContent ?? (object)DBNull.Value);
            update.Parameters.AddWithValue("$assigned_to", response.AssignedTo ?? (object)DBNull.Value);
            update.Parameters.AddWithValue("$review_due_at", response.ReviewDueAt?.ToString("O") ?? (object)DBNull.Value);
            update.Parameters.AddWithValue("$transition_reason", response.LastTransitionReason ?? (object)DBNull.Value);
            update.Parameters.AddWithValue("$review_revision", response.ReviewRevision);
            update.Parameters.AddWithValue("$synced_at", now.ToString("O"));
            update.Parameters.AddWithValue("$comment_id", fieldComment.CommentId);
            update.ExecuteNonQuery();
        }
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
        AdvanceDependentFieldCommentReviewBases(connection, fieldComment.CommentId, response.ReviewRevision);
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
            attachment.HashSha256,
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
                MutationKey = item.IdempotencyKey,
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

        VerifyReportReadBack(response);
        LinkReportDocumentToServer(item, document, response, DateTime.UtcNow);
    }

    private static void VerifyReportReadBack(ServerReportResponse response)
    {
        if (response.ReportRevision < 1 || string.IsNullOrWhiteSpace(response.ContentHashSha256) ||
            response.ContentHashSha256.Length != 64 || string.IsNullOrWhiteSpace(response.SourceSetHashSha256) ||
            response.SourceSetHashSha256.Length != 64)
        {
            throw new InvalidOperationException("서버 보고서 revision/content/source-set hash read-back이 불완전합니다.");
        }

        var normalized = response.Sources
            .Select(source => new SortedDictionary<string, object?>
            {
                ["relation_type"] = source.RelationType,
                ["source_hash_sha256"] = source.SourceHashSha256,
                ["source_id"] = source.SourceId,
                ["source_revision"] = source.SourceRevision,
                ["source_type"] = source.SourceType,
                ["source_version_id"] = source.SourceVersionId
            })
            .OrderBy(item => Convert.ToString(item["source_type"], System.Globalization.CultureInfo.InvariantCulture))
            .ThenBy(item => Convert.ToString(item["source_id"], System.Globalization.CultureInfo.InvariantCulture))
            .ThenBy(item => Convert.ToString(item["source_version_id"], System.Globalization.CultureInfo.InvariantCulture) ?? string.Empty)
            .ThenBy(item => Convert.ToString(item["relation_type"], System.Globalization.CultureInfo.InvariantCulture) ?? string.Empty)
            .ThenBy(item => Convert.ToString(item["source_hash_sha256"], System.Globalization.CultureInfo.InvariantCulture))
            .ToList();
        var canonical = JsonSerializer.Serialize(normalized, new JsonSerializerOptions
        {
            Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping
        });
        var readBackHash = ComputeSha256(canonical);
        if (!string.Equals(readBackHash, response.SourceSetHashSha256, StringComparison.OrdinalIgnoreCase))
        {
            throw new FlowNoteServerConflictException(
                "REPORT_SOURCE_SET_HASH_MISMATCH",
                "서버 보고서 source read-back hash가 aggregate hash와 다릅니다.",
                null, response.ReportRevision, response.Status, null, null,
                $"server={response.SourceSetHashSha256}; readBack={readBackHash}");
        }
    }


}
