using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Storage;
using System.Security.Cryptography;
using System.Text.Json;

namespace FlowNote.Windows.Core.Sync;

public sealed partial class ServerSyncService
{
    public async Task<ServerSyncResult> ResolveConflictAsNewVersionAsync(
        long queueId,
        FlowNoteServerDocumentClient serverClient,
        string resolvedBy,
        string reason,
        string resolvedRole,
        string? serverUserId = null,
        CancellationToken cancellationToken = default)
    {
        DocumentConflictResolutionPolicy.ValidateResolution(resolvedBy, reason, resolvedRole);

        ConflictVersionSource source;
        using (var connection = database.OpenConnection())
        using (var command = connection.CreateCommand())
        {
            command.CommandText = """
                SELECT queue.entity_id, queue.action, queue.local_document_id,
                       queue.local_version_no, queue.idempotency_key,
                       queue.local_file_hash_sha256, queue.source_preserved_path,
                       queue.allowed_actions_json, document.server_document_id
                FROM server_sync_queue AS queue
                JOIN documents AS document
                  ON document.document_id = COALESCE(queue.local_document_id, queue.entity_id)
                WHERE queue.id = $id AND queue.status = 'CONFLICT'
                LIMIT 1;
                """;
            command.Parameters.AddWithValue("$id", queueId);
            using var reader = command.ExecuteReader();
            if (!reader.Read())
            {
                throw new InvalidOperationException("새 버전으로 종결할 충돌 항목을 찾을 수 없습니다.");
            }
            source = new ConflictVersionSource(
                reader.GetString(0),
                reader.GetString(1),
                reader.IsDBNull(2) ? reader.GetString(0) : reader.GetString(2),
                reader.IsDBNull(3) ? null : reader.GetInt32(3),
                reader.GetString(4),
                reader.IsDBNull(5) ? null : reader.GetString(5),
                reader.IsDBNull(6) ? null : reader.GetString(6),
                reader.IsDBNull(7) ? null : reader.GetString(7),
                reader.IsDBNull(8) ? null : reader.GetString(8));
        }

        if (source.Action != "register_document_version" ||
            !DocumentConflictResolutionPolicy.Contains(
                source.AllowedActionsJson,
                DocumentConflictResolutionPolicy.RegisterNewVersion))
        {
            throw new InvalidOperationException("이 충돌은 새 버전 등록으로 종결할 수 없습니다.");
        }
        if (source.LocalVersionNo is null || string.IsNullOrWhiteSpace(source.ServerDocumentId))
        {
            throw new InvalidOperationException("새 버전 등록에 필요한 문서·버전 매핑이 없습니다.");
        }
        if (string.IsNullOrWhiteSpace(source.SourcePreservedPath))
        {
            throw new InvalidOperationException("보존된 원본 파일 위치를 확인할 수 없습니다.");
        }

        var sourcePath = FlowNoteLocalDatabase.ResolveLocalContentPath(source.SourcePreservedPath);
        if (!File.Exists(sourcePath))
        {
            throw new InvalidOperationException("보존된 원본 파일이 없어 새 버전을 만들 수 없습니다.");
        }
        string actualHash;
        using (var stream = File.OpenRead(sourcePath))
        {
            actualHash = Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
        }
        if (!string.IsNullOrWhiteSpace(source.LocalFileHashSha256) &&
            !string.Equals(source.LocalFileHashSha256, actualHash, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("보존된 원본 파일 hash가 충돌 발생 당시와 달라 새 mutation을 만들지 않았습니다.");
        }

        var authority = await serverClient.GetDocumentAsync(
            source.ServerDocumentId,
            cancellationToken);
        var now = DateTime.UtcNow;
        var newKey = $"{source.IdempotencyKey}:new-version:{Guid.NewGuid():N}";
        var baseSnapshotHash = ComputeSha256(JsonSerializer.Serialize(new
        {
            authority.Revision,
            authority.LatestVersionId,
            authority.PublishedVersionId,
            authority.Status,
            authority.Tags
        }));

        using (var connection = database.OpenConnection())
        using (var transaction = connection.BeginTransaction())
        {
            UpdateDocumentServerState(connection, source.LocalDocumentId, authority, transaction);
            using var resolve = connection.CreateCommand();
            resolve.Transaction = transaction;
            resolve.CommandText = """
                UPDATE server_sync_queue
                SET status = 'DISCARDED',
                    resolution_action = 'REGISTER_NEW_VERSION',
                    resolution_reason = $reason,
                    resolved_by = $resolved_by,
                    resolved_at = $resolved_at
                WHERE id = $id AND status = 'CONFLICT';
                """;
            resolve.Parameters.AddWithValue("$reason", reason.Trim());
            resolve.Parameters.AddWithValue("$resolved_by", resolvedBy.Trim());
            resolve.Parameters.AddWithValue("$resolved_at", now.ToString("O"));
            resolve.Parameters.AddWithValue("$id", queueId);
            if (resolve.ExecuteNonQuery() != 1)
            {
                throw new InvalidOperationException("충돌 상태가 변경되어 최신 목록을 다시 확인해야 합니다.");
            }

            using var enqueue = connection.CreateCommand();
            enqueue.Transaction = transaction;
            enqueue.CommandText = """
                INSERT INTO server_sync_queue (
                    sync_id, entity_type, entity_id, action, local_document_id,
                    local_version_no, idempotency_key, status, attempt_count,
                    created_at, base_server_revision, expected_server_version_id,
                    expected_published_version_id, local_file_hash_sha256,
                    intent_hash, base_snapshot_hash_sha256, source_preserved_path)
                VALUES (
                    $sync_id, 'document_version', $entity_id, 'register_document_version',
                    $local_document_id, $local_version_no, $idempotency_key,
                    'PENDING', 0, $created_at, $base_server_revision,
                    $expected_server_version_id, $expected_published_version_id,
                    $local_file_hash_sha256, $intent_hash,
                    $base_snapshot_hash_sha256, $source_preserved_path);
                """;
            enqueue.Parameters.AddWithValue("$sync_id", $"sync-{Guid.NewGuid():N}");
            enqueue.Parameters.AddWithValue("$entity_id", source.EntityId);
            enqueue.Parameters.AddWithValue("$local_document_id", source.LocalDocumentId);
            enqueue.Parameters.AddWithValue("$local_version_no", source.LocalVersionNo.Value);
            enqueue.Parameters.AddWithValue("$idempotency_key", newKey);
            enqueue.Parameters.AddWithValue("$created_at", now.ToString("O"));
            enqueue.Parameters.AddWithValue("$base_server_revision", authority.Revision);
            enqueue.Parameters.AddWithValue("$expected_server_version_id", (object?)authority.LatestVersionId ?? DBNull.Value);
            enqueue.Parameters.AddWithValue("$expected_published_version_id", (object?)authority.PublishedVersionId ?? DBNull.Value);
            enqueue.Parameters.AddWithValue("$local_file_hash_sha256", actualHash);
            enqueue.Parameters.AddWithValue("$intent_hash", ComputeSha256(newKey));
            enqueue.Parameters.AddWithValue("$base_snapshot_hash_sha256", baseSnapshotHash);
            enqueue.Parameters.AddWithValue("$source_preserved_path", source.SourcePreservedPath);
            enqueue.ExecuteNonQuery();

            RecordSyncHistory(
                connection,
                "server_sync.conflict_new_version_selected",
                "server_sync_queue",
                queueId.ToString(),
                $"원본을 복사·덮어쓰지 않고 서버 revision {authority.Revision} 기준의 새 mutation을 만들었습니다. 사유: {reason.Trim()}",
                now,
                transaction);
            transaction.Commit();
        }

        return await RetryPendingAsync(serverClient, serverUserId, cancellationToken);
    }

    private sealed record ConflictVersionSource(
        string EntityId,
        string Action,
        string LocalDocumentId,
        int? LocalVersionNo,
        string IdempotencyKey,
        string? LocalFileHashSha256,
        string? SourcePreservedPath,
        string? AllowedActionsJson,
        string? ServerDocumentId);
}
