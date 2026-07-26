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
        var baseServerRevision = ReadCurrentBaseServerRevision(item);
        if (baseServerRevision is null)
        {
            throw LegacyBaseConflict("구 태그 큐에는 서버 기준 revision이 없어 자동 교체할 수 없습니다.");
        }

        var document = LoadDocument(item.EntityId)
            ?? throw new InvalidOperationException($"Local document not found: {item.EntityId}");
        var mapping = TryGetDocumentServerMapping(item.EntityId);
        if (mapping?.ServerDocumentId is null)
        {
            throw new InvalidOperationException(SyncFailureMessages.DocumentDependencyNotSynced);
        }

        var tags = ReadTagsPayload(item.PayloadJson)
            ?? TagService.CleanTags(document.TagList)
                .OrderBy(value => value, StringComparer.Ordinal)
                .ToList();
        var response = await serverClient.ReplaceDocumentTagsAsync(
            mapping.ServerDocumentId,
            tags,
            baseServerRevision.Value,
            item.IdempotencyKey,
            cancellationToken);
        var authoritative = await ReadBackDocumentAuthorityAsync(
            serverClient,
            response.DocumentId,
            expectedStatus: null,
            expectedPublishedVersionId: null,
            expectedTags: tags,
            cancellationToken);
        var now = DateTime.UtcNow;

        using var connection = database.OpenConnection();
        UpdateDocumentServerState(connection, document.DocumentId, authoritative);
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
            serverRevision: authoritative.Revision);
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
            serverRevision: authoritative.Revision);
        MarkQueueSynced(
            connection,
            item.Id,
            authoritative.DocumentId,
            authoritative.LatestVersionId,
            null,
            null,
            now);
        AdvanceDependentDocumentBases(connection, document.DocumentId, authoritative);
        RecordSyncHistory(
            connection,
            "server_sync.succeeded",
            "document_tags",
            document.DocumentId,
            $"Server document tags synced and read back: {authoritative.DocumentId} revision {authoritative.Revision}",
            now);
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

    private static IReadOnlyList<string>? ReadTagsPayload(string? payloadJson)
    {
        if (string.IsNullOrWhiteSpace(payloadJson))
        {
            return null;
        }

        try
        {
            return JsonSerializer.Deserialize<DocumentTagsSyncPayload>(payloadJson)?.Tags;
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
        ServerDocumentResponse response) =>
        AdvanceDependentDocumentBases(
            connection,
            localDocumentId,
            response.Revision,
            response.LatestVersionId,
            response.PublishedVersionId);

    private static void AdvanceDependentDocumentBases(
        SqliteConnection connection,
        string localDocumentId,
        int serverRevision,
        string? latestVersionId,
        string? publishedVersionId)
    {
        using var command = connection.CreateCommand();
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
                  'update_document_status',
                  'replace_document_tags'
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
