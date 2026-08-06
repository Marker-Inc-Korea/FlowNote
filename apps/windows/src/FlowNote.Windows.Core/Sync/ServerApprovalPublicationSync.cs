using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Tags;
using Microsoft.Data.Sqlite;
using System.Text.Json;

namespace FlowNote.Windows.Core.Sync;

public sealed partial class ServerSyncService
{
    public ApprovalPublicationLocalSyncResult ApplyApprovalPublicationReadBack(
        ServerApprovalDocumentResponse authority,
        string approvalId,
        string serverMutationKey)
    {
        if (!string.Equals(authority.Status, "PUBLISHED", StringComparison.Ordinal) ||
            string.IsNullOrWhiteSpace(authority.PublishedVersionId) ||
            authority.PublishedVersion is not { IsPublished: true } published ||
            !string.Equals(published.VersionId, authority.PublishedVersionId, StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                "서버 상세 read-back에서 공개 상태·공개 포인터·version flag가 일치하지 않습니다.");
        }

        using var connection = database.OpenConnection();
        var localDocument = FindLocalDocument(connection, authority.DocumentId);
        if (localDocument is null)
        {
            return new ApprovalPublicationLocalSyncResult(
                false,
                false,
                authority.DocumentId,
                authority.PublishedVersionId,
                authority.Revision,
                "서버 공개는 확인했지만 연결된 로컬 문서 mapping이 없어 로컬 원천과 큐를 변경하지 않았습니다.");
        }

        var publishedVersionNo = FindLocalVersionNo(
            connection, localDocument.DocumentId, authority.PublishedVersionId);
        if (publishedVersionNo is null)
        {
            return new ApprovalPublicationLocalSyncResult(
                false,
                true,
                authority.DocumentId,
                authority.PublishedVersionId,
                authority.Revision,
                "서버 공개는 확인했지만 공개 version의 로컬 mapping이 없어 로컬 원천과 큐를 변경하지 않았습니다.");
        }

        var receiptKey = $"wpf:approval-publication-readback:{approvalId}";
        var alreadyApplied = HasAppliedPublicationReceipt(
            connection, receiptKey, authority.Revision, authority.PublishedVersionId);
        var now = DateTime.UtcNow;
        using var transaction = connection.BeginTransaction();
        UpdateLocalPublication(
            connection,
            transaction,
            localDocument.DocumentId,
            publishedVersionNo.Value,
            authority,
            now);
        TagService.ReplaceDocumentTags(
            connection, localDocument.DocumentId, authority.Tags, transaction);

        var latestHash = authority.LatestVersion?.File.HashSha256;
        var publishedHash = published.File.HashSha256;
        UpsertMapping(
            connection,
            "document",
            localDocument.DocumentId,
            0,
            authority.DocumentId,
            authority.LatestVersionId,
            null,
            null,
            null,
            now,
            serverRevision: authority.Revision,
            serverFileHashSha256: latestHash,
            serverPublishedVersionId: authority.PublishedVersionId,
            transaction: transaction);
        UpsertMapping(
            connection,
            "document_version",
            localDocument.DocumentId,
            publishedVersionNo.Value,
            authority.DocumentId,
            authority.PublishedVersionId,
            null,
            null,
            null,
            now,
            serverRevision: authority.Revision,
            serverFileHashSha256: publishedHash,
            serverPublishedVersionId: authority.PublishedVersionId,
            transaction: transaction);
        UpsertApprovalPublicationReceipt(
            connection,
            transaction,
            receiptKey,
            serverMutationKey,
            approvalId,
            localDocument.DocumentId,
            publishedVersionNo.Value,
            authority,
            now);
        AdvanceDependentDocumentBases(
            connection,
            localDocument.DocumentId,
            authority.Revision,
            authority.LatestVersionId,
            authority.PublishedVersionId,
            transaction);
        if (!alreadyApplied)
        {
            RecordSyncHistory(
                connection,
                "server_sync.approval_publication_read_back_applied",
                "document",
                localDocument.DocumentId,
                $"승인 {approvalId} 공개본을 서버 read-back과 일치시켰습니다: revision {authority.Revision}, version {authority.PublishedVersionId}",
                now,
                transaction);
        }
        transaction.Commit();

        return new ApprovalPublicationLocalSyncResult(
            !alreadyApplied,
            true,
            authority.DocumentId,
            authority.PublishedVersionId,
            authority.Revision,
            alreadyApplied
                ? "서버 공개본과 로컬 공개 포인터가 이미 일치합니다."
                : "서버 공개본, 로컬 문서·version flag·mapping·태그 snapshot·큐·이력을 함께 반영했습니다.");
    }

    private static LocalPublicationDocument? FindLocalDocument(
        SqliteConnection connection,
        string serverDocumentId)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT document_id, title
            FROM documents
            WHERE server_document_id = $server_document_id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$server_document_id", serverDocumentId);
        using var reader = command.ExecuteReader();
        return reader.Read()
            ? new LocalPublicationDocument(reader.GetString(0), reader.GetString(1))
            : null;
    }

    private static int? FindLocalVersionNo(
        SqliteConnection connection,
        string localDocumentId,
        string serverVersionId)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT version_no
            FROM document_versions
            WHERE document_id = $document_id AND server_version_id = $server_version_id
            UNION ALL
            SELECT local_version_no
            FROM server_id_mappings
            WHERE entity_type = 'document_version'
              AND local_id = $document_id
              AND server_version_id = $server_version_id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$document_id", localDocumentId);
        command.Parameters.AddWithValue("$server_version_id", serverVersionId);
        var value = command.ExecuteScalar();
        return value is null or DBNull ? null : Convert.ToInt32(value);
    }

    private static bool HasAppliedPublicationReceipt(
        SqliteConnection connection,
        string receiptKey,
        int revision,
        string publishedVersionId)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT COUNT(*)
            FROM server_sync_queue
            WHERE idempotency_key = $key
              AND status = 'SYNCED'
              AND base_server_revision = $revision
              AND server_version_id = $published_version_id;
            """;
        command.Parameters.AddWithValue("$key", receiptKey);
        command.Parameters.AddWithValue("$revision", revision);
        command.Parameters.AddWithValue("$published_version_id", publishedVersionId);
        return Convert.ToInt64(command.ExecuteScalar()) == 1;
    }

    private static void UpdateLocalPublication(
        SqliteConnection connection,
        SqliteTransaction transaction,
        string localDocumentId,
        int publishedVersionNo,
        ServerApprovalDocumentResponse authority,
        DateTime now)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            UPDATE document_versions
            SET is_published = CASE WHEN version_no = $published_version_no THEN 1 ELSE 0 END,
                published_at = CASE WHEN version_no = $published_version_no THEN $synced_at ELSE NULL END,
                version_status = CASE
                    WHEN version_no = $published_version_no THEN 'PUBLISHED'
                    WHEN is_published = 1 AND version_status = 'PUBLISHED' THEN 'SUPERSEDED'
                    ELSE version_status
                END,
                is_latest = CASE
                    WHEN server_version_id = $latest_version_id THEN 1
                    WHEN is_latest = 1 AND $latest_version_id IS NOT NULL THEN 0
                    ELSE is_latest
                END
            WHERE document_id = $document_id;

            UPDATE documents
            SET status = 'PUBLISHED',
                published_version_no = $published_version_no,
                server_document_id = $server_document_id,
                server_version_id = $latest_version_id,
                server_revision = $server_revision,
                server_published_version_id = $published_version_id,
                server_tags_json = $server_tags_json,
                synced_at = $synced_at
            WHERE document_id = $document_id;
            """;
        command.Parameters.AddWithValue("$document_id", localDocumentId);
        command.Parameters.AddWithValue("$published_version_no", publishedVersionNo);
        command.Parameters.AddWithValue("$server_document_id", authority.DocumentId);
        command.Parameters.AddWithValue("$latest_version_id", (object?)authority.LatestVersionId ?? DBNull.Value);
        command.Parameters.AddWithValue("$server_revision", authority.Revision);
        command.Parameters.AddWithValue("$published_version_id", authority.PublishedVersionId!);
        command.Parameters.AddWithValue("$server_tags_json", JsonSerializer.Serialize(authority.Tags));
        command.Parameters.AddWithValue("$synced_at", now.ToString("O"));
        command.ExecuteNonQuery();
    }

    private static void UpsertApprovalPublicationReceipt(
        SqliteConnection connection,
        SqliteTransaction transaction,
        string receiptKey,
        string serverMutationKey,
        string approvalId,
        string localDocumentId,
        int localVersionNo,
        ServerApprovalDocumentResponse authority,
        DateTime now)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            INSERT INTO server_sync_queue (
                sync_id, entity_type, entity_id, action, local_document_id,
                local_version_no, idempotency_key, status, attempt_count,
                created_at, last_attempt_at, synced_at, server_document_id,
                server_version_id, base_server_revision,
                expected_server_version_id, expected_published_version_id,
                payload_json)
            VALUES (
                $sync_id, 'document_publish', $entity_id,
                'apply_approval_publication_read_back', $local_document_id,
                $local_version_no, $idempotency_key, 'SYNCED', 1,
                $created_at, $created_at, $created_at, $server_document_id,
                $server_version_id, $server_revision,
                $latest_version_id, $published_version_id, $payload_json)
            ON CONFLICT(idempotency_key) DO UPDATE SET
                status = 'SYNCED',
                last_error = NULL,
                last_attempt_at = excluded.last_attempt_at,
                synced_at = excluded.synced_at,
                server_document_id = excluded.server_document_id,
                server_version_id = excluded.server_version_id,
                base_server_revision = excluded.base_server_revision,
                expected_server_version_id = excluded.expected_server_version_id,
                expected_published_version_id = excluded.expected_published_version_id,
                payload_json = excluded.payload_json;
            """;
        command.Parameters.AddWithValue("$sync_id", $"sync-approval-publication-{Guid.NewGuid():N}");
        command.Parameters.AddWithValue("$entity_id", localDocumentId);
        command.Parameters.AddWithValue("$local_document_id", localDocumentId);
        command.Parameters.AddWithValue("$local_version_no", localVersionNo);
        command.Parameters.AddWithValue("$idempotency_key", receiptKey);
        command.Parameters.AddWithValue("$created_at", now.ToString("O"));
        command.Parameters.AddWithValue("$server_document_id", authority.DocumentId);
        command.Parameters.AddWithValue("$server_version_id", authority.PublishedVersionId!);
        command.Parameters.AddWithValue("$server_revision", authority.Revision);
        command.Parameters.AddWithValue("$latest_version_id", (object?)authority.LatestVersionId ?? DBNull.Value);
        command.Parameters.AddWithValue("$published_version_id", authority.PublishedVersionId!);
        command.Parameters.AddWithValue("$payload_json", JsonSerializer.Serialize(new
        {
            approvalId,
            serverMutationKey,
            authority.DocumentId,
            authority.Revision,
            authority.LatestVersionId,
            authority.PublishedVersionId,
            authority.Status,
            authority.Tags
        }));
        command.ExecuteNonQuery();
    }

    private sealed record LocalPublicationDocument(string DocumentId, string Title);
}

public sealed record ApprovalPublicationLocalSyncResult(
    bool Applied,
    bool LocalMappingFound,
    string ServerDocumentId,
    string ServerPublishedVersionId,
    int ServerRevision,
    string Message);
