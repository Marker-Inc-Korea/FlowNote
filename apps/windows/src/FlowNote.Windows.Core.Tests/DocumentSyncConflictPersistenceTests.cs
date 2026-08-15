using FlowNote.Windows.Core.Storage;
using FlowNote.Windows.Core.Sync;
using FlowNote.Windows.Core.ServerApi;
using Microsoft.Data.Sqlite;
using System.Net;
using System.Text;
using System.Text.Json;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class DocumentSyncConflictPersistenceTests
{
    private readonly string databasePath = Path.Combine(
        FlowNoteLocalDatabase.DefaultDataDirectory,
        $"flownote.core-tests-{Guid.NewGuid():N}.sqlite");

    [Fact]
    public void ExistingDatabaseMigrationPreservesLegacyFieldNotesAndAddsConflictColumns()
    {
        var database = CreateDatabase();
        var legacyId = $"legacy-{Guid.NewGuid():N}";
        using (var connection = database.OpenConnection())
        using (var command = connection.CreateCommand())
        {
            command.CommandText = """
                CREATE TABLE IF NOT EXISTS field_notes (
                    note_id TEXT PRIMARY KEY,
                    raw_content TEXT NOT NULL
                );
                INSERT INTO field_notes (note_id, raw_content)
                VALUES ($note_id, '보존 원천')
                ON CONFLICT(note_id) DO NOTHING;
                """;
            command.Parameters.AddWithValue("$note_id", legacyId);
            command.ExecuteNonQuery();
        }

        new FlowNoteLocalDatabase(databasePath).Initialize();

        using var verify = database.OpenConnection();
        Assert.Equal(
            1L,
            ScalarLong(verify, "SELECT COUNT(*) FROM field_notes WHERE note_id = $value;", legacyId));
        Assert.True(ColumnExists(verify, "documents", "server_revision"));
        Assert.True(ColumnExists(verify, "documents", "server_tags_json"));
        Assert.True(ColumnExists(verify, "server_sync_queue", "conflict_code"));
        Assert.True(ColumnExists(verify, "server_sync_queue", "resolution_reason"));
        Assert.True(ColumnExists(verify, "server_sync_queue", "base_domain_revision"));
        Assert.True(ColumnExists(verify, "server_sync_queue", "intent_hash"));
        Assert.True(ColumnExists(verify, "server_sync_queue", "source_set_hash"));
        Assert.True(ColumnExists(verify, "server_sync_queue", "base_snapshot_hash_sha256"));
        Assert.True(ColumnExists(verify, "server_sync_queue", "server_read_back_json"));
        Assert.True(ColumnExists(verify, "server_sync_queue", "allowed_actions_json"));
        Assert.True(ColumnExists(verify, "server_sync_queue", "source_preserved_path"));
        Assert.True(ColumnExists(verify, "server_sync_queue", "retry_not_before"));
        Assert.True(ColumnExists(verify, "field_comments", "review_revision"));
        Assert.True(ColumnExists(verify, "server_id_mappings", "server_file_hash_sha256"));
        Assert.True(ColumnExists(verify, "server_id_mappings", "server_published_version_id"));
    }

    [Fact]
    public void ConflictAndAdministratorDiscardAuditSurviveServiceRestart()
    {
        var database = CreateDatabase();
        var suffix = Guid.NewGuid().ToString("N");
        var documentId = $"doc-conflict-{suffix}";
        var queueId = InsertConflict(database, documentId, suffix);

        var restarted = new ServerSyncService(new FlowNoteLocalDatabase(databasePath));
        var conflict = Assert.Single(restarted.ListQueueItems(), item => item.Id == queueId);
        Assert.Equal("CONFLICT", conflict.Status);
        Assert.Equal("STALE_REVISION", conflict.ConflictCode);
        Assert.Equal(3, conflict.BaseServerRevision);

        restarted.DiscardConflict(
            queueId,
            "user-admin",
            "서버 공개본을 유지하기로 확인",
            "document-admin");

        var afterSecondRestart = new ServerSyncService(new FlowNoteLocalDatabase(databasePath));
        var discarded = Assert.Single(afterSecondRestart.ListQueueItems(), item => item.Id == queueId);
        Assert.Equal("DISCARDED", discarded.Status);
        Assert.Equal("KEEP_SERVER", discarded.ResolutionAction);
        Assert.Equal("서버 공개본을 유지하기로 확인", discarded.ResolutionReason);
        Assert.Equal("user-admin", discarded.ResolvedBy);
        Assert.NotNull(discarded.ResolvedAt);

        using var connection = database.OpenConnection();
        Assert.Equal(
            1L,
            ScalarLong(
                connection,
                "SELECT COUNT(*) FROM activity_history WHERE event_type = 'server_sync.conflict_discarded' AND target_id = $value;",
                queueId.ToString()));
    }

    [Fact]
    public async Task ClientSendsBaseRevisionAndParsesStructuredConflict()
    {
        var handler = new ConflictHandler();
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://sync.example/") };
        var client = new FlowNoteServerDocumentClient(http);

        var exception = await Assert.ThrowsAsync<FlowNoteServerConflictException>(() =>
            client.UpdateDocumentStatusAsync(
                "server-document",
                "ARCHIVED",
                "관리자 보관",
                baseRevision: 7));

        Assert.Contains("\"baseRevision\":7", handler.RequestBody, StringComparison.Ordinal);
        Assert.Equal("STALE_REVISION", exception.ConflictCode);
        Assert.Equal(7, exception.ExpectedRevision);
        Assert.Equal(8, exception.CurrentRevision);
        Assert.Equal("PUBLISHED", exception.CurrentStatus);
        Assert.Equal("ver-public", exception.CurrentPublishedVersionId);
        Assert.Equal("document-conflict-v1", exception.SchemaVersion);
        Assert.Equal("DOCUMENT_STATE", exception.ConflictKind);
        Assert.Equal(["KEEP_SERVER", "RETRY_WITH_LATEST"], exception.AllowedActions);
        Assert.False(exception.AutoMergeAllowed);
        Assert.Equal(300, exception.RetryNotBeforeSeconds);
    }

    [Fact]
    public async Task ClientPreservesUnstructuredConflictReason()
    {
        using var http = new HttpClient(new StringConflictHandler())
        {
            BaseAddress = new Uri("https://sync.example/")
        };
        var client = new FlowNoteServerDocumentClient(http);

        var exception = await Assert.ThrowsAsync<FlowNoteServerConflictException>(() =>
            client.UpdateDocumentStatusAsync(
                "server-document",
                "ARCHIVED",
                "관리자 보관",
                baseRevision: 7,
                mutationKey: "status-conflict-test"));

        Assert.Equal("SERVER_CONFLICT", exception.ConflictCode);
        Assert.Equal("Transition PUBLISHED -> ARCHIVED is not allowed.", exception.Message);
        Assert.Contains("Transition PUBLISHED -> ARCHIVED", exception.ResponseBody, StringComparison.Ordinal);
    }

    [Fact]
    public async Task NetworkFailureRestartAndDuplicateRetryPreserveOneQueueAndMapping()
    {
        var database = CreateDatabase();
        var suffix = Guid.NewGuid().ToString("N");
        var documentId = $"doc-network-{suffix}";
        var relativePath = Path.Combine("Files", "CoreSyncTests", $"network-{suffix}.txt");
        var absolutePath = Path.Combine(FlowNoteLocalDatabase.DefaultDataDirectory, relativePath);
        Directory.CreateDirectory(Path.GetDirectoryName(absolutePath)!);
        await File.WriteAllTextAsync(absolutePath, $"network retry evidence {suffix}");
        InsertPendingDocument(database, documentId, relativePath);
        var record = new FlowNote.Windows.Core.Documents.DocumentRecord(
            0,
            documentId,
            0,
            "네트워크 재시도 문서",
            Path.GetFileName(absolutePath),
            "Text",
            "WORKING",
            "user-admin",
            DateTime.UtcNow,
            DateTime.UtcNow,
            relativePath,
            1,
            "네트워크 재연결 검증");

        using var unavailableHttp = new HttpClient(new UnavailableHandler())
        {
            BaseAddress = new Uri("https://offline.example/")
        };
        var firstService = new ServerSyncService(database);
        var offlineResult = await firstService.QueueAndTrySyncDocumentAsync(
            record,
            new FlowNoteServerDocumentClient(unavailableHttp),
            "user-admin");
        Assert.False(offlineResult.Success);
        Assert.Equal(1, firstService.CountQueuedForEntity("document", documentId, "FAILED"));

        using var recoveredHttp = new HttpClient(new DocumentSuccessHandler(documentId, absolutePath))
        {
            BaseAddress = new Uri("https://recovered.example/")
        };
        var restarted = new ServerSyncService(new FlowNoteLocalDatabase(databasePath));
        await restarted.RetryPendingAsync(
            new FlowNoteServerDocumentClient(recoveredHttp),
            "user-admin");
        Assert.Equal(1, restarted.CountQueuedForEntity("document", documentId, "SYNCED"));
        Assert.Equal(1, restarted.CountQueuedForEntity("document", documentId));

        await restarted.RetryPendingAsync(
            new FlowNoteServerDocumentClient(recoveredHttp),
            "user-admin");
        using var connection = database.OpenConnection();
        Assert.Equal(
            1L,
            ScalarLong(
                connection,
                "SELECT COUNT(*) FROM server_id_mappings WHERE entity_type = 'document' AND local_id = $value;",
                documentId));
        Assert.Equal(
            1L,
            ScalarLong(
                connection,
                "SELECT COUNT(*) FROM server_id_mappings WHERE entity_type = 'document_version' AND local_id = $value;",
                documentId));
    }

    [Fact]
    public async Task DocumentTagsUseMutationReceiptKeyAndReadBackBeforeQueueIsSynced()
    {
        var database = CreateDatabase();
        var suffix = Guid.NewGuid().ToString("N");
        var documentId = $"doc-tags-{suffix}";
        var relativePath = Path.Combine("Files", "CoreSyncTests", $"tags-{suffix}.txt");
        var absolutePath = Path.Combine(FlowNoteLocalDatabase.DefaultDataDirectory, relativePath);
        var serverScope = $"https://tag-authority-{suffix}.example/";
        Directory.CreateDirectory(Path.GetDirectoryName(absolutePath)!);
        await File.WriteAllTextAsync(absolutePath, $"tag authority evidence {suffix}");
        InsertPendingDocument(database, documentId, relativePath);
        var updatedAt = DateTime.UtcNow;
        using (var connection = database.OpenConnection())
        using (var command = connection.CreateCommand())
        {
            command.CommandText = """
                UPDATE documents
                SET server_document_id = $server_document_id,
                    server_version_id = $server_version_id,
                    server_revision = 5,
                    server_tags_json = '[]',
                    synced_at = $now
                WHERE document_id = $document_id;
                INSERT INTO server_id_mappings (
                    entity_type, local_id, local_version_no, server_document_id,
                    server_version_id, server_revision, synced_at)
                VALUES (
                    'document', $document_id, 0, $server_document_id,
                    $server_version_id, 5, $now);
                INSERT INTO server_bindings (
                    server_scope, server_instance_id, server_epoch, schema_contract,
                    api_contract_min, api_contract_max, status,
                    observed_server_instance_id, observed_server_epoch, updated_at)
                VALUES (
                    $server_scope, 'srv-tag-authority', 1, 1,
                    1, 1, 'ACTIVE', 'srv-tag-authority', 1, $now);
                """;
            command.Parameters.AddWithValue("$document_id", documentId);
            command.Parameters.AddWithValue("$server_document_id", $"server-{documentId}");
            command.Parameters.AddWithValue("$server_version_id", $"version-{documentId}");
            command.Parameters.AddWithValue("$now", updatedAt.ToString("O"));
            command.Parameters.AddWithValue("$server_scope", serverScope);
            command.ExecuteNonQuery();
        }
        var record = new FlowNote.Windows.Core.Documents.DocumentRecord(
            0,
            documentId,
            0,
            "태그 권위 문서",
            Path.GetFileName(absolutePath),
            "Text",
            "WORKING",
            "user-admin",
            updatedAt,
            updatedAt,
            relativePath,
            1,
            null,
            ["line-a", "press-a"]);
        var handler = new TagAuthorityHandler(
            $"server-{documentId}",
            $"version-{documentId}",
            ["line-a", "press-a"]);
        using var http = new HttpClient(handler)
        {
            BaseAddress = new Uri(serverScope)
        };

        var result = await new ServerSyncService(database).QueueAndTrySyncDocumentTagsAsync(
            record,
            new FlowNoteServerDocumentClient(http),
            "user-admin");

        Assert.Equal(1, result.Synced);
        Assert.Equal(1, handler.PutCount);
        Assert.Equal(1, handler.ReadBackCount);
        Assert.DoesNotContain("mutationKey=", handler.PutRequestUri);
        using (var request = JsonDocument.Parse(handler.PutBody))
        {
            Assert.Equal(5, request.RootElement.GetProperty("baseRevision").GetInt32());
            Assert.Equal(
                ["line-a", "press-a"],
                request.RootElement.GetProperty("addedTags").EnumerateArray()
                    .Select(value => value.GetString()!).ToArray());
            Assert.Empty(request.RootElement.GetProperty("removedTags").EnumerateArray());
            Assert.StartsWith(
                "wpf:document-tags:",
                request.RootElement.GetProperty("mutationKey").GetString());
            Assert.Equal(
                64,
                request.RootElement.GetProperty("intentHash").GetString()!.Length);
        }
        using var verify = database.OpenConnection();
        Assert.Equal(
            1L,
            ScalarLong(
                verify,
                "SELECT COUNT(*) FROM server_sync_queue WHERE entity_type = 'document_tags' AND entity_id = $value AND status = 'SYNCED';",
                documentId));
        Assert.Equal(
            6L,
            ScalarLong(
                verify,
                "SELECT server_revision FROM documents WHERE document_id = $value;",
                documentId));
        Assert.Equal(
            "[\"line-a\",\"press-a\"]",
            ScalarString(
                verify,
                "SELECT server_tags_json FROM documents WHERE document_id = $value;",
                documentId));
        var queueRecord = Assert.Single(
            new ServerSyncService(database).ListQueueItems(),
            item => item.EntityId == documentId && item.EntityType == "document_tags");
        Assert.Equal(64, queueRecord.BaseSnapshotHashSha256?.Length);
        Assert.Equal(relativePath, queueRecord.SourcePreservedPath);
    }

    [Theory]
    [InlineData("replace_document_tags", "TAG_MERGE_CONFLICT", true, true, false)]
    [InlineData("publish_document_version", "PUBLISHED_VERSION_CHANGED", true, false, false)]
    [InlineData("register_document_version", "STALE_BASE_VERSION", false, false, true)]
    [InlineData("register_document_version", "DOCUMENT_DELETED", false, false, false)]
    public void ConflictPolicyAllowsOnlyExplicitDocumentResolutionActions(
        string action,
        string code,
        bool retryLatest,
        bool reapplyTagDelta,
        bool newVersion)
    {
        var allowed = DocumentConflictResolutionPolicy.AllowedActions(action, code);

        Assert.Contains(DocumentConflictResolutionPolicy.KeepServer, allowed);
        Assert.Equal(retryLatest, allowed.Contains(DocumentConflictResolutionPolicy.RetryWithLatest));
        Assert.Equal(reapplyTagDelta, allowed.Contains(DocumentConflictResolutionPolicy.ReapplyTagDelta));
        Assert.Equal(newVersion, allowed.Contains(DocumentConflictResolutionPolicy.RegisterNewVersion));
    }

    [Fact]
    public async Task NewVersionResolutionPreservesSourceAndCreatesSeparateMutation()
    {
        var database = CreateDatabase();
        var suffix = Guid.NewGuid().ToString("N");
        var documentId = $"doc-new-version-{suffix}";
        var relativePath = Path.Combine("Files", "CoreSyncTests", $"new-version-{suffix}.txt");
        var absolutePath = Path.Combine(FlowNoteLocalDatabase.DefaultDataDirectory, relativePath);
        Directory.CreateDirectory(Path.GetDirectoryName(absolutePath)!);
        await File.WriteAllTextAsync(absolutePath, $"new version source {suffix}");
        var hashBefore = Convert.ToHexString(
            System.Security.Cryptography.SHA256.HashData(await File.ReadAllBytesAsync(absolutePath)))
            .ToLowerInvariant();
        InsertPendingDocument(database, documentId, relativePath);

        long conflictId;
        var originalKey = $"version-conflict-{suffix}";
        using (var connection = database.OpenConnection())
        using (var transaction = connection.BeginTransaction())
        {
            using var setup = connection.CreateCommand();
            setup.Transaction = transaction;
            setup.CommandText = """
                UPDATE documents
                SET server_document_id = $server_document_id,
                    server_version_id = $server_version_id,
                    server_revision = 4,
                    synced_at = $now
                WHERE document_id = $document_id;
                INSERT INTO server_id_mappings (
                    entity_type, local_id, local_version_no, server_document_id,
                    server_version_id, server_revision, synced_at)
                VALUES ('document', $document_id, 0, $server_document_id,
                        $server_version_id, 4, $now);
                INSERT INTO server_sync_queue (
                    sync_id, entity_type, entity_id, action, local_document_id,
                    local_version_no, idempotency_key, status, attempt_count,
                    created_at, base_server_revision, local_file_hash_sha256,
                    conflict_code, conflict_details, allowed_actions_json,
                    source_preserved_path)
                VALUES (
                    $sync_id, 'document_version', $document_id,
                    'register_document_version', $document_id, 1,
                    $idempotency_key, 'CONFLICT', 1, $now, 4,
                    $local_file_hash, 'STALE_BASE_VERSION', '{}',
                    '["KEEP_SERVER","REGISTER_NEW_VERSION"]', $source_path);
                SELECT last_insert_rowid();
                """;
            setup.Parameters.AddWithValue("$server_document_id", $"server-{documentId}");
            setup.Parameters.AddWithValue("$server_version_id", $"version-{documentId}");
            setup.Parameters.AddWithValue("$document_id", documentId);
            setup.Parameters.AddWithValue("$now", DateTime.UtcNow.ToString("O"));
            setup.Parameters.AddWithValue("$sync_id", $"sync-conflict-{suffix}");
            setup.Parameters.AddWithValue("$idempotency_key", originalKey);
            setup.Parameters.AddWithValue("$local_file_hash", hashBefore);
            setup.Parameters.AddWithValue("$source_path", relativePath);
            conflictId = Convert.ToInt64(setup.ExecuteScalar());
            transaction.Commit();
        }

        using var http = new HttpClient(new NewVersionResolutionHandler($"server-{documentId}"))
        {
            BaseAddress = new Uri($"https://new-version-{suffix}.example/")
        };
        var service = new ServerSyncService(database);
        await service.ResolveConflictAsNewVersionAsync(
            conflictId,
            new FlowNoteServerDocumentClient(http),
            "user-admin",
            "서버 최신본 기준으로 새 버전 등록",
            "document-admin",
            "user-admin");

        var records = service.ListQueueItems()
            .Where(item => item.EntityId == documentId)
            .ToList();
        var original = Assert.Single(records, item => item.Id == conflictId);
        var created = Assert.Single(records, item => item.Id != conflictId);
        Assert.Equal("DISCARDED", original.Status);
        Assert.Equal("REGISTER_NEW_VERSION", original.ResolutionAction);
        Assert.NotEqual(originalKey, created.IdempotencyKey);
        Assert.Equal(5, created.BaseServerRevision);
        Assert.Equal(relativePath, created.SourcePreservedPath);
        Assert.Equal(hashBefore, created.LocalFileHashSha256);
        var hashAfter = Convert.ToHexString(
            System.Security.Cryptography.SHA256.HashData(await File.ReadAllBytesAsync(absolutePath)))
            .ToLowerInvariant();
        Assert.Equal(hashBefore, hashAfter);
    }

    [Fact]
    public async Task TagResponseLossLeavesLocalTransactionUntouchedAndRetryConverges()
    {
        var database = CreateDatabase();
        var suffix = Guid.NewGuid().ToString("N");
        var documentId = $"doc-tags-loss-{suffix}";
        var relativePath = Path.Combine("Files", "CoreSyncTests", $"tags-loss-{suffix}.txt");
        var absolutePath = Path.Combine(FlowNoteLocalDatabase.DefaultDataDirectory, relativePath);
        var serverScope = $"https://tag-loss-{suffix}.example/";
        Directory.CreateDirectory(Path.GetDirectoryName(absolutePath)!);
        await File.WriteAllTextAsync(absolutePath, $"tag response loss evidence {suffix}");
        InsertPendingDocument(database, documentId, relativePath);
        var now = DateTime.UtcNow;
        using (var connection = database.OpenConnection())
        using (var command = connection.CreateCommand())
        {
            command.CommandText = """
                UPDATE documents
                SET server_document_id = $server_document_id,
                    server_version_id = $server_version_id,
                    server_revision = 5,
                    server_tags_json = '[]',
                    synced_at = $now
                WHERE document_id = $document_id;
                INSERT INTO server_id_mappings (
                    entity_type, local_id, local_version_no, server_document_id,
                    server_version_id, server_revision, synced_at)
                VALUES ('document', $document_id, 0, $server_document_id,
                        $server_version_id, 5, $now);
                INSERT INTO server_bindings (
                    server_scope, server_instance_id, server_epoch, schema_contract,
                    api_contract_min, api_contract_max, status,
                    observed_server_instance_id, observed_server_epoch, updated_at)
                VALUES ($server_scope, 'srv-tag-authority', 1, 1, 1, 1, 'ACTIVE',
                        'srv-tag-authority', 1, $now);
                """;
            command.Parameters.AddWithValue("$document_id", documentId);
            command.Parameters.AddWithValue("$server_document_id", $"server-{documentId}");
            command.Parameters.AddWithValue("$server_version_id", $"version-{documentId}");
            command.Parameters.AddWithValue("$now", now.ToString("O"));
            command.Parameters.AddWithValue("$server_scope", serverScope);
            command.ExecuteNonQuery();
        }
        var record = new FlowNote.Windows.Core.Documents.DocumentRecord(
            0, documentId, 0, "태그 응답 유실", Path.GetFileName(absolutePath), "Text",
            "WORKING", "user-admin", now, now, relativePath, 1, null, ["line-a"]);
        var handler = new TagAuthorityHandler(
            $"server-{documentId}", $"version-{documentId}", ["line-a"],
            loseFirstReadBack: true);
        using var http = new HttpClient(handler) { BaseAddress = new Uri(serverScope) };
        var client = new FlowNoteServerDocumentClient(http);

        var first = await new ServerSyncService(database).QueueAndTrySyncDocumentTagsAsync(
            record, client, "user-admin");
        Assert.False(first.Success);
        using (var verify = database.OpenConnection())
        {
            Assert.Equal(
                5L,
                ScalarLong(
                    verify,
                    "SELECT server_revision FROM documents WHERE document_id = $value;",
                    documentId));
            Assert.Equal(
                1L,
                ScalarLong(
                    verify,
                    "SELECT COUNT(*) FROM server_sync_queue WHERE entity_id = $value AND status = 'FAILED';",
                    documentId));
        }

        var second = await new ServerSyncService(database).RetryPendingAsync(client, "user-admin");
        Assert.True(second.Synced >= 1, second.Message);
        Assert.Equal(2, handler.PutCount);
        Assert.Equal(2, handler.PutBodies.Count);
        Assert.Equal(handler.PutBodies[0], handler.PutBodies[1]);
        using var converged = database.OpenConnection();
        Assert.Equal(
            6L,
            ScalarLong(
                converged,
                "SELECT server_revision FROM documents WHERE document_id = $value;",
                documentId));
        Assert.Equal(
            1L,
            ScalarLong(
                converged,
                "SELECT COUNT(*) FROM server_sync_queue WHERE entity_id = $value AND status = 'SYNCED';",
                documentId));
    }

    [Fact]
    public void ApprovalPublicationReadBackAtomicallyUpdatesLocalPointersMappingsTagsQueueAndHistory()
    {
        var database = CreateDatabase();
        var suffix = Guid.NewGuid().ToString("N");
        var localDocumentId = $"doc-approval-publish-{suffix}";
        var serverDocumentId = $"server-approval-publish-{suffix}";
        var serverVersionId = $"version-approval-publish-{suffix}";
        InsertPendingDocument(database, localDocumentId, Path.Combine("Files", $"{suffix}.txt"));
        using (var connection = database.OpenConnection())
        using (var command = connection.CreateCommand())
        {
            command.CommandText = """
                UPDATE documents
                SET server_document_id = $server_document_id,
                    server_version_id = $server_version_id,
                    server_revision = 4,
                    synced_at = $now
                WHERE document_id = $document_id;
                UPDATE document_versions
                SET server_version_id = $server_version_id,
                    synced_at = $now
                WHERE document_id = $document_id AND version_no = 1;
                """;
            command.Parameters.AddWithValue("$document_id", localDocumentId);
            command.Parameters.AddWithValue("$server_document_id", serverDocumentId);
            command.Parameters.AddWithValue("$server_version_id", serverVersionId);
            command.Parameters.AddWithValue("$now", DateTime.UtcNow.ToString("O"));
            command.ExecuteNonQuery();
        }

        var file = new ServerApprovalFileResponse(new string('a', 64));
        var version = new ServerApprovalVersionResponse(serverVersionId, file)
        {
            VersionNo = 1,
            VersionStatus = "PUBLISHED",
            IsLatest = true,
            IsPublished = true
        };
        var approvalId = $"approval-{suffix}";
        var authority = new ServerApprovalDocumentResponse(
            serverDocumentId, "승인 공개 문서", 5, serverVersionId, version)
        {
            Status = "PUBLISHED",
            PublishedVersionId = serverVersionId,
            PublicationApprovalId = approvalId,
            PublishedVersion = version,
            Tags = ["line-a", "press-a"]
        };
        var first = new ServerSyncService(database).ApplyApprovalPublicationReadBack(
            authority, approvalId, $"server-mutation-{suffix}");
        var replay = new ServerSyncService(database).ApplyApprovalPublicationReadBack(
            authority, approvalId, $"server-recovery-{suffix}");

        Assert.True(first.Applied);
        Assert.False(replay.Applied);
        using var verify = database.OpenConnection();
        Assert.Equal(
            "PUBLISHED",
            ScalarString(verify, "SELECT status FROM documents WHERE document_id = $value;", localDocumentId));
        Assert.Equal(
            serverVersionId,
            ScalarString(verify, "SELECT server_published_version_id FROM documents WHERE document_id = $value;", localDocumentId));
        Assert.Equal(
            1L,
            ScalarLong(verify, "SELECT is_published FROM document_versions WHERE document_id = $value AND version_no = 1;", localDocumentId));
        Assert.Equal(
            2L,
            ScalarLong(verify, "SELECT COUNT(*) FROM server_id_mappings WHERE local_id = $value AND server_published_version_id IS NOT NULL;", localDocumentId));
        Assert.Equal(
            1L,
            ScalarLong(verify, "SELECT COUNT(*) FROM server_sync_queue WHERE entity_id = $value AND action = 'apply_approval_publication_read_back';", localDocumentId));
        Assert.Equal(
            1L,
            ScalarLong(verify, "SELECT COUNT(*) FROM activity_history WHERE target_id = $value AND event_type = 'server_sync.approval_publication_read_back_applied';", localDocumentId));
        Assert.Equal(
            2L,
            ScalarLong(verify, "SELECT COUNT(*) FROM document_tags WHERE document_id = $value;", localDocumentId));
    }

    private FlowNoteLocalDatabase CreateDatabase()
    {
        var database = new FlowNoteLocalDatabase(databasePath);
        database.Initialize();
        return database;
    }

    private static long InsertConflict(FlowNoteLocalDatabase database, string documentId, string suffix)
    {
        using var connection = database.OpenConnection();
        using var transaction = connection.BeginTransaction();
        long folderRowId;
        using (var folder = connection.CreateCommand())
        {
            folder.Transaction = transaction;
            folder.CommandText = "SELECT id FROM document_folders ORDER BY id LIMIT 1;";
            folderRowId = Convert.ToInt64(folder.ExecuteScalar());
        }
        using (var document = connection.CreateCommand())
        {
            document.Transaction = transaction;
            document.CommandText = """
                INSERT INTO documents (
                    document_id, folder_id, title, file_name, document_type, status,
                    created_by, created_at, updated_at, version_no, server_document_id,
                    server_version_id, server_revision, synced_at
                ) VALUES (
                    $document_id, $folder_id, '충돌 테스트', 'conflict.txt', 'Text', 'WORKING',
                    'user-admin', $now, $now, 2, $server_document_id,
                    $server_version_id, 3, $now
                );
                """;
            document.Parameters.AddWithValue("$document_id", documentId);
            document.Parameters.AddWithValue("$folder_id", folderRowId);
            document.Parameters.AddWithValue("$server_document_id", $"server-{suffix}");
            document.Parameters.AddWithValue("$server_version_id", $"version-{suffix}");
            document.Parameters.AddWithValue("$now", DateTime.UtcNow.ToString("O"));
            document.ExecuteNonQuery();
        }
        using var queue = connection.CreateCommand();
        queue.Transaction = transaction;
        queue.CommandText = """
            INSERT INTO server_sync_queue (
                sync_id, entity_type, entity_id, action, local_document_id,
                local_version_no, idempotency_key, status, attempt_count,
                last_error, created_at, base_server_revision, conflict_code,
                conflict_details
            ) VALUES (
                $sync_id, 'document_version', $document_id, 'register_document_version',
                $document_id, 2, $idempotency_key, 'CONFLICT', 1,
                '서버 revision 변경 충돌', $now, 3, 'STALE_REVISION', '{}'
            );
            SELECT last_insert_rowid();
            """;
        queue.Parameters.AddWithValue("$sync_id", $"sync-{suffix}");
        queue.Parameters.AddWithValue("$document_id", documentId);
        queue.Parameters.AddWithValue("$idempotency_key", $"test-conflict-{suffix}");
        queue.Parameters.AddWithValue("$now", DateTime.UtcNow.ToString("O"));
        var queueId = Convert.ToInt64(queue.ExecuteScalar());
        transaction.Commit();
        return queueId;
    }

    private static void InsertPendingDocument(
        FlowNoteLocalDatabase database,
        string documentId,
        string relativePath)
    {
        using var connection = database.OpenConnection();
        using var transaction = connection.BeginTransaction();
        long folderRowId;
        using (var folder = connection.CreateCommand())
        {
            folder.Transaction = transaction;
            folder.CommandText = "SELECT id FROM document_folders ORDER BY id LIMIT 1;";
            folderRowId = Convert.ToInt64(folder.ExecuteScalar());
        }
        var now = DateTime.UtcNow.ToString("O");
        using (var document = connection.CreateCommand())
        {
            document.Transaction = transaction;
            document.CommandText = """
                INSERT INTO documents (
                    document_id, folder_id, title, file_name, document_type, status,
                    created_by, created_at, updated_at, local_path, version_no
                ) VALUES (
                    $document_id, $folder_id, '네트워크 재시도 문서', $file_name, 'Text',
                    'WORKING', 'user-admin', $now, $now, $local_path, 1
                );
                """;
            document.Parameters.AddWithValue("$document_id", documentId);
            document.Parameters.AddWithValue("$folder_id", folderRowId);
            document.Parameters.AddWithValue("$file_name", Path.GetFileName(relativePath));
            document.Parameters.AddWithValue("$local_path", relativePath);
            document.Parameters.AddWithValue("$now", now);
            document.ExecuteNonQuery();
        }
        using (var version = connection.CreateCommand())
        {
            version.Transaction = transaction;
            version.CommandText = """
                INSERT INTO document_versions (
                    document_id, version_no, file_name, local_path, comment, created_by,
                    created_at, version_status, is_latest, is_published
                ) VALUES (
                    $document_id, 1, $file_name, $local_path, '네트워크 재연결 검증',
                    'user-admin', $now, 'WORKING', 1, 0
                );
                """;
            version.Parameters.AddWithValue("$document_id", documentId);
            version.Parameters.AddWithValue("$file_name", Path.GetFileName(relativePath));
            version.Parameters.AddWithValue("$local_path", relativePath);
            version.Parameters.AddWithValue("$now", now);
            version.ExecuteNonQuery();
        }
        transaction.Commit();
    }

    private static bool ColumnExists(SqliteConnection connection, string tableName, string columnName)
    {
        using var command = connection.CreateCommand();
        command.CommandText = $"PRAGMA table_info({tableName});";
        using var reader = command.ExecuteReader();
        while (reader.Read())
        {
            if (string.Equals(reader.GetString(1), columnName, StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }
        return false;
    }

    private static long ScalarLong(SqliteConnection connection, string sql, string value)
    {
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        command.Parameters.AddWithValue("$value", value);
        return Convert.ToInt64(command.ExecuteScalar());
    }

    private static string ScalarString(SqliteConnection connection, string sql, string value)
    {
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        command.Parameters.AddWithValue("$value", value);
        return Convert.ToString(command.ExecuteScalar()) ?? string.Empty;
    }

    private sealed class ConflictHandler : HttpMessageHandler
    {
        public string RequestBody { get; private set; } = string.Empty;

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            RequestBody = request.Content is null
                ? string.Empty
                : await request.Content.ReadAsStringAsync(cancellationToken);
            return new HttpResponseMessage(HttpStatusCode.Conflict)
            {
                Content = new StringContent(
                    """
                    {"detail":{"schemaVersion":"document-conflict-v1","code":"STALE_REVISION","conflictKind":"DOCUMENT_STATE","message":"stale","documentId":"server-document","expectedRevision":7,"currentRevision":8,"currentStatus":"PUBLISHED","currentLatestVersionId":"ver-latest","currentPublishedVersionId":"ver-public","allowedActions":["KEEP_SERVER","RETRY_WITH_LATEST"],"autoMergeAllowed":false,"retryPolicy":{"automatic":false,"retryNotBeforeSeconds":300}}}
                    """,
                    Encoding.UTF8,
                    "application/json")
            };
        }
    }

    private sealed class StringConflictHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.Conflict)
            {
                Content = new StringContent(
                    "{\"detail\":\"Transition PUBLISHED -> ARCHIVED is not allowed.\"}",
                    Encoding.UTF8,
                    "application/json")
            });
    }

    private sealed class UnavailableHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.ServiceUnavailable)
            {
                Content = new StringContent("{\"detail\":\"offline\"}", Encoding.UTF8, "application/json")
            });
    }

    private sealed class NewVersionResolutionHandler(string serverDocumentId) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            if (request.RequestUri?.AbsolutePath.EndsWith("/api/v1/sync/manifest", StringComparison.Ordinal) == true)
            {
                return Task.FromResult(new HttpResponseMessage(HttpStatusCode.ServiceUnavailable)
                {
                    Content = new StringContent("{\"detail\":\"retry deferred\"}", Encoding.UTF8, "application/json")
                });
            }
            var json = JsonSerializer.Serialize(new
            {
                document_id = serverDocumentId,
                title = "서버 최신 문서",
                description = (string?)null,
                document_type = "Text",
                owner_id = (string?)null,
                category_id = (string?)null,
                status = "WORKING",
                revision = 5,
                latest_version_id = $"latest-{serverDocumentId}",
                published_version_id = (string?)null,
                created_at = DateTime.UtcNow,
                updated_at = DateTime.UtcNow,
                tags = Array.Empty<string>(),
                latest_version = (object?)null,
                published_version = (object?)null
            });
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(json, Encoding.UTF8, "application/json")
            });
        }
    }

    private sealed class DocumentSuccessHandler(string localDocumentId, string filePath) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            if (request.RequestUri?.AbsolutePath.EndsWith("/api/v1/sync/manifest", StringComparison.Ordinal) == true)
            {
                return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(
                        "{\"server_instance_id\":\"srv-test-recovered\",\"server_epoch\":1,\"schema_contract\":1,\"api_contract_min\":1,\"api_contract_max\":1,\"server_cursor\":0}",
                        Encoding.UTF8,
                        "application/json")
                });
            }
            var hash = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(filePath))).ToLowerInvariant();
            var now = DateTime.UtcNow.ToString("O");
            var serverDocumentId = $"server-{localDocumentId}";
            var serverVersionId = $"version-{localDocumentId}";
            var json = $$"""
                {
                  "document_id":"{{serverDocumentId}}",
                  "title":"네트워크 재시도 문서",
                  "description":null,
                  "document_type":"Text",
                  "owner_id":null,
                  "category_id":null,
                  "status":"WORKING",
                  "revision":1,
                  "latest_version_id":"{{serverVersionId}}",
                  "published_version_id":null,
                  "created_at":"{{now}}",
                  "updated_at":"{{now}}",
                  "tags":[],
                  "latest_version":{
                    "version_id":"{{serverVersionId}}",
                    "document_id":"{{serverDocumentId}}",
                    "version_no":1,
                    "version_label":"v1",
                    "change_reason":"network retry",
                    "version_status":"WORKING",
                    "is_latest":true,
                    "is_published":false,
                    "created_by":"user-admin",
                    "created_at":"{{now}}",
                    "file":{"storage_type":"local","storage_key":"test","original_filename":"network.txt","extension":".txt","mime_type":"text/plain","file_family":"text","size_bytes":1,"hash_sha256":"{{hash}}"}
                  },
                  "published_version":null
                }
                """;
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.Created)
            {
                Content = new StringContent(json, Encoding.UTF8, "application/json")
            });
        }
    }

    private sealed class TagAuthorityHandler(
        string serverDocumentId,
        string serverVersionId,
        IReadOnlyList<string> tags,
        bool loseFirstReadBack = false) : HttpMessageHandler
    {
        public int PutCount { get; private set; }
        public int ReadBackCount { get; private set; }
        public string PutRequestUri { get; private set; } = string.Empty;
        public string PutBody { get; private set; } = string.Empty;
        public List<string> PutBodies { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            if (request.RequestUri?.AbsolutePath.EndsWith("/api/v1/sync/manifest", StringComparison.Ordinal) == true)
            {
                return JsonResponse(
                    "{\"server_instance_id\":\"srv-tag-authority\",\"server_epoch\":1,\"schema_contract\":1,\"api_contract_min\":1,\"api_contract_max\":1,\"server_cursor\":0}");
            }
            if (request.Method == HttpMethod.Put)
            {
                PutCount++;
                PutRequestUri = request.RequestUri?.ToString() ?? string.Empty;
                PutBody = request.Content is null
                    ? string.Empty
                    : await request.Content.ReadAsStringAsync(cancellationToken);
                PutBodies.Add(PutBody);
                return JsonResponse(DocumentJson());
            }
            if (request.Method == HttpMethod.Get)
            {
                ReadBackCount++;
                if (loseFirstReadBack && ReadBackCount == 1)
                {
                    return new HttpResponseMessage(HttpStatusCode.ServiceUnavailable)
                    {
                        Content = new StringContent("{\"detail\":\"simulated response loss\"}")
                    };
                }
                return JsonResponse(DocumentJson());
            }
            return new HttpResponseMessage(HttpStatusCode.NotFound);
        }

        private string DocumentJson() => JsonSerializer.Serialize(new
        {
            document_id = serverDocumentId,
            title = "태그 권위 문서",
            description = (string?)null,
            document_type = "Text",
            owner_id = (string?)null,
            category_id = (string?)null,
            status = "WORKING",
            revision = 6,
            latest_version_id = serverVersionId,
            published_version_id = (string?)null,
            created_at = DateTime.UtcNow,
            updated_at = DateTime.UtcNow,
            tags,
            latest_version = (object?)null,
            published_version = (object?)null
        });

        private static HttpResponseMessage JsonResponse(string json) =>
            new(HttpStatusCode.OK)
            {
                Content = new StringContent(json, Encoding.UTF8, "application/json")
            };
    }
}
