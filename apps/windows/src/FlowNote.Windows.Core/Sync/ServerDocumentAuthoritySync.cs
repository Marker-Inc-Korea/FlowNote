using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Tags;
using Microsoft.Data.Sqlite;
using System.Text.Json;

namespace FlowNote.Windows.Core.Sync;

public sealed partial class ServerSyncService
{
    private async Task<string?> TryReadConflictServerHashAsync(
        QueueItem item,
        FlowNoteServerDocumentClient serverClient,
        CancellationToken cancellationToken)
    {
        var localDocumentId = item.LocalDocumentId ?? item.EntityId;
        var mapping = TryGetDocumentServerMapping(localDocumentId);
        if (mapping?.ServerDocumentId is null)
        {
            return null;
        }
        try
        {
            var document = await serverClient.GetDocumentAsync(
                mapping.ServerDocumentId,
                cancellationToken);
            var version = item.Action == "publish_document_version"
                ? document.PublishedVersion ?? document.LatestVersion
                : document.LatestVersion ?? document.PublishedVersion;
            return version?.File.HashSha256;
        }
        catch (Exception exception) when (
            exception is HttpRequestException or
            TaskCanceledException or
            InvalidOperationException)
        {
            return null;
        }
    }

    private async Task SyncDocumentTagsAsync(
        QueueItem item,
        FlowNoteServerDocumentClient serverClient,
        CancellationToken cancellationToken)
    {
        var document = LoadDocument(item.EntityId)
            ?? throw new InvalidOperationException($"Local document not found: {item.EntityId}");
        var mapping = TryGetDocumentServerMapping(item.EntityId);
        if (mapping?.ServerDocumentId is null)
        {
            throw new InvalidOperationException(SyncFailureMessages.DocumentDependencyNotSynced);
        }

        var payload = ReadTagsPayload(item.PayloadJson);
        if (payload is { BaseTagsKnown: false, CanResolveBaseAfterDocumentRegistration: true })
        {
            payload = ResolveDeferredDocumentTagPayload(item, mapping.ServerDocumentId);
        }
        var baseServerRevision = payload?.BaseRevision ?? ReadCurrentBaseServerRevision(item);
        if (baseServerRevision is null)
        {
            throw LegacyBaseConflict("구 태그 큐에는 서버 기준 revision이 없어 자동 교체할 수 없습니다.");
        }
        if (payload is null || !payload.BaseTagsKnown)
        {
            throw LegacyBaseConflict(
                "구 태그 큐에는 서버 기준 태그 집합이 없어 추가·제거 의도를 안전하게 계산할 수 없습니다.");
        }
        if (payload.BaseRevision != baseServerRevision.Value ||
            !string.Equals(
                payload.IntentHash,
                ReadCurrentIntentHash(item.Id),
                StringComparison.OrdinalIgnoreCase))
        {
            throw new FlowNoteServerConflictException(
                "TAG_INTENT_HASH_MISMATCH",
                "보존된 태그 요청의 baseRevision 또는 intent hash가 큐 메타데이터와 다릅니다.",
                baseServerRevision,
                mapping.ServerRevision,
                null,
                mapping.ServerVersionId,
                mapping.ServerPublishedVersionId,
                item.PayloadJson ?? "{}");
        }
        var response = await serverClient.MergeDocumentTagsAsync(
            mapping.ServerDocumentId,
            baseServerRevision.Value,
            payload.AddedTags,
            payload.RemovedTags,
            payload.IntentHash,
            item.IdempotencyKey,
            cancellationToken);
        var authoritative = await ReadBackDocumentAuthorityAsync(
            serverClient,
            response.DocumentId,
            expectedStatus: null,
            expectedPublishedVersionId: null,
            expectedTags: response.Tags,
            cancellationToken);
        var now = DateTime.UtcNow;
        var latestHash = authoritative.LatestVersion?.File.HashSha256;

        using var connection = database.OpenConnection();
        using var transaction = connection.BeginTransaction();
        UpdateDocumentServerState(connection, document.DocumentId, authoritative, transaction);
        TagService.ReplaceDocumentTags(
            connection, document.DocumentId, authoritative.Tags, transaction);
        UpsertMapping(
            connection,
            "document_tags",
            document.DocumentId,
            item.LocalVersionNo ?? document.VersionNo,
            authoritative.DocumentId,
            authoritative.LatestVersionId,
            null,
            null,
            null,
            now,
            serverRevision: authoritative.Revision,
            serverFileHashSha256: latestHash,
            transaction: transaction);
        UpsertMapping(
            connection,
            "document",
            document.DocumentId,
            0,
            authoritative.DocumentId,
            authoritative.LatestVersionId,
            null,
            null,
            null,
            now,
            serverRevision: authoritative.Revision,
            serverFileHashSha256: latestHash,
            transaction: transaction);
        MarkQueueSynced(
            connection,
            item.Id,
            authoritative.DocumentId,
            authoritative.LatestVersionId,
            null,
            null,
            now,
            transaction: transaction);
        AdvanceDependentDocumentBases(
            connection, document.DocumentId, authoritative, transaction);
        RecordSyncHistory(
            connection,
            "server_sync.succeeded",
            "document_tags",
            document.DocumentId,
            $"Server document tags synced and read back: {authoritative.DocumentId} revision {authoritative.Revision}",
            now,
            transaction);
        transaction.Commit();
    }

    private DocumentTagsSyncPayload ResolveDeferredDocumentTagPayload(
        QueueItem item,
        string serverDocumentId)
    {
        var original = ReadTagsPayload(item.PayloadJson)
            ?? throw LegacyBaseConflict("보존된 태그 요청 본문을 읽을 수 없습니다.");
        using var connection = database.OpenConnection();
        using var select = connection.CreateCommand();
        select.CommandText = """
            SELECT server_revision, server_tags_json
            FROM documents
            WHERE document_id = $document_id
            LIMIT 1;
            """;
        select.Parameters.AddWithValue("$document_id", item.EntityId);
        using var reader = select.ExecuteReader();
        if (!reader.Read() || reader.IsDBNull(0) || reader.IsDBNull(1))
        {
            throw LegacyBaseConflict(
                "문서 등록 응답의 서버 revision과 태그 기준 집합이 없어 태그 의도를 확정할 수 없습니다.");
        }
        var baseRevision = reader.GetInt32(0);
        IReadOnlyList<string> baseTags;
        try
        {
            baseTags = JsonSerializer.Deserialize<List<string>>(reader.GetString(1)) ?? [];
        }
        catch (JsonException)
        {
            throw LegacyBaseConflict("문서 등록 응답의 서버 태그 기준 집합을 읽을 수 없습니다.");
        }
        reader.Close();

        var addedTags = original.DesiredTags
            .Except(baseTags, StringComparer.OrdinalIgnoreCase)
            .OrderBy(value => value, StringComparer.Ordinal)
            .ToList();
        var removedTags = baseTags
            .Except(original.DesiredTags, StringComparer.OrdinalIgnoreCase)
            .OrderBy(value => value, StringComparer.Ordinal)
            .ToList();
        var intentHash = CreateDocumentTagIntentHash(
            serverDocumentId, baseRevision, addedTags, removedTags);
        var resolved = new DocumentTagsSyncPayload(
            baseRevision,
            addedTags,
            removedTags,
            intentHash,
            true,
            original.DesiredTags,
            false);
        using var update = connection.CreateCommand();
        update.CommandText = """
            UPDATE server_sync_queue
            SET base_server_revision = $base_revision,
                intent_hash = $intent_hash,
                payload_json = $payload_json
            WHERE id = $id
              AND status IN ('PENDING', 'FAILED');
            """;
        update.Parameters.AddWithValue("$base_revision", baseRevision);
        update.Parameters.AddWithValue("$intent_hash", intentHash);
        update.Parameters.AddWithValue("$payload_json", JsonSerializer.Serialize(resolved));
        update.Parameters.AddWithValue("$id", item.Id);
        if (update.ExecuteNonQuery() != 1)
        {
            throw new InvalidOperationException("태그 큐 기준 상태가 변경되어 요청 의도를 확정하지 못했습니다.");
        }
        return resolved;
    }

    private static string? ReadStatusPayload(string? payloadJson)
    {
        if (string.IsNullOrWhiteSpace(payloadJson))
        {
            return null;
        }

        try
        {
            return JsonSerializer.Deserialize<DocumentStatusSyncPayload>(payloadJson)?.Status;
        }
        catch (JsonException)
        {
            return null;
        }
    }

    private static DocumentTagsSyncPayload? ReadTagsPayload(string? payloadJson)
    {
        if (string.IsNullOrWhiteSpace(payloadJson))
        {
            return null;
        }

        try
        {
            return JsonSerializer.Deserialize<DocumentTagsSyncPayload>(payloadJson);
        }
        catch (JsonException)
        {
            return null;
        }
    }

    private static FieldCommentReviewSyncPayload? ParseFieldCommentReviewPayload(string? payloadJson)
    {
        if (string.IsNullOrWhiteSpace(payloadJson))
        {
            return null;
        }

        try
        {
            return JsonSerializer.Deserialize<FieldCommentReviewSyncPayload>(payloadJson);
        }
        catch (JsonException)
        {
            return null;
        }
    }

    private int? ReadCurrentBaseServerRevision(QueueItem item)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT base_server_revision FROM server_sync_queue WHERE id = $id;";
        command.Parameters.AddWithValue("$id", item.Id);
        var value = command.ExecuteScalar();
        return value is null or DBNull ? null : Convert.ToInt32(value);
    }

    private int? ReadCurrentBaseDomainRevision(QueueItem item)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT base_domain_revision FROM server_sync_queue WHERE id = $id;";
        command.Parameters.AddWithValue("$id", item.Id);
        var value = command.ExecuteScalar();
        return value is null or DBNull ? null : Convert.ToInt32(value);
    }

    private string? ReadCurrentIntentHash(long queueId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT intent_hash FROM server_sync_queue WHERE id = $id;";
        command.Parameters.AddWithValue("$id", queueId);
        return command.ExecuteScalar() as string;
    }

    private static void AdvanceDependentFieldCommentReviewBases(
        SqliteConnection connection,
        string commentId,
        int reviewRevision)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            UPDATE server_sync_queue
            SET base_domain_revision = $review_revision
            WHERE entity_type = 'field_comment_review'
              AND entity_id = $comment_id
              AND status IN ('PENDING', 'FAILED')
              AND intent_hash IS NOT NULL;
            """;
        command.Parameters.AddWithValue("$review_revision", reviewRevision);
        command.Parameters.AddWithValue("$comment_id", commentId);
        command.ExecuteNonQuery();
    }

    private static async Task<ServerDocumentResponse> ReadBackDocumentAuthorityAsync(
        FlowNoteServerDocumentClient serverClient,
        string serverDocumentId,
        string? expectedStatus,
        string? expectedPublishedVersionId,
        IReadOnlyList<string>? expectedTags,
        CancellationToken cancellationToken)
    {
        var readBack = await serverClient.GetDocumentAsync(serverDocumentId, cancellationToken);
        var statusMatches = expectedStatus is null ||
            string.Equals(readBack.Status, expectedStatus, StringComparison.Ordinal);
        var publishMatches = expectedPublishedVersionId is null ||
            string.Equals(
                readBack.PublishedVersionId,
                expectedPublishedVersionId,
                StringComparison.Ordinal);
        var tagsMatch = expectedTags is null ||
            expectedTags.OrderBy(value => value, StringComparer.OrdinalIgnoreCase).SequenceEqual(
                readBack.Tags.OrderBy(value => value, StringComparer.OrdinalIgnoreCase),
                StringComparer.OrdinalIgnoreCase);
        if (statusMatches && publishMatches && tagsMatch)
        {
            return readBack;
        }

        var details = JsonSerializer.Serialize(new
        {
            expectedStatus,
            currentStatus = readBack.Status,
            expectedPublishedVersionId,
            currentPublishedVersionId = readBack.PublishedVersionId,
            expectedTags,
            currentTags = readBack.Tags,
            currentRevision = readBack.Revision
        });
        throw new FlowNoteServerConflictException(
            "DOCUMENT_READ_BACK_MISMATCH",
            "서버 mutation 응답 뒤 read-back한 문서 권위 상태가 요청과 일치하지 않습니다.",
            null,
            readBack.Revision,
            readBack.Status,
            readBack.LatestVersionId,
            readBack.PublishedVersionId,
            details);
    }

    private static void AdvanceDependentDocumentBases(
        SqliteConnection connection,
        string localDocumentId,
        ServerDocumentResponse response,
        SqliteTransaction? transaction = null) =>
        AdvanceDependentDocumentBases(
            connection,
            localDocumentId,
            response.Revision,
            response.LatestVersionId,
            response.PublishedVersionId,
            transaction);

    private static void AdvanceDependentDocumentBases(
        SqliteConnection connection,
        string localDocumentId,
        int serverRevision,
        string? latestVersionId,
        string? publishedVersionId,
        SqliteTransaction? transaction = null)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            UPDATE server_sync_queue
            SET base_server_revision = $revision,
                expected_server_version_id = $latest_version_id,
                expected_published_version_id = $published_version_id
            WHERE COALESCE(local_document_id, entity_id) = $local_document_id
              AND status IN ('PENDING', 'FAILED')
              AND intent_hash IS NOT NULL
              AND action IN (
                  'register_document_version',
                  'publish_document_version',
                  'update_document_status'
              );
            """;
        command.Parameters.AddWithValue("$revision", serverRevision);
        command.Parameters.AddWithValue(
            "$latest_version_id",
            string.IsNullOrWhiteSpace(latestVersionId) ? DBNull.Value : latestVersionId);
        command.Parameters.AddWithValue(
            "$published_version_id",
            string.IsNullOrWhiteSpace(publishedVersionId) ? DBNull.Value : publishedVersionId);
        command.Parameters.AddWithValue("$local_document_id", localDocumentId);
        command.ExecuteNonQuery();
    }
}
