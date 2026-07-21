using FlowNote.Windows.Core.Storage;
using FlowNote.Windows.Core.Sync;
using FlowNote.Windows.Core.ServerApi;
using Microsoft.Data.Sqlite;
using System.Net;
using System.Text;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class DocumentSyncConflictPersistenceTests
{
    private static readonly string DatabasePath = Path.Combine(
        FlowNoteLocalDatabase.DefaultDataDirectory,
        "flownote.core-tests.sqlite");

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

        new FlowNoteLocalDatabase(DatabasePath).Initialize();

        using var verify = database.OpenConnection();
        Assert.Equal(
            1L,
            ScalarLong(verify, "SELECT COUNT(*) FROM field_notes WHERE note_id = $value;", legacyId));
        Assert.True(ColumnExists(verify, "documents", "server_revision"));
        Assert.True(ColumnExists(verify, "server_sync_queue", "conflict_code"));
        Assert.True(ColumnExists(verify, "server_sync_queue", "resolution_reason"));
        Assert.True(ColumnExists(verify, "server_sync_queue", "base_domain_revision"));
        Assert.True(ColumnExists(verify, "server_sync_queue", "intent_hash"));
        Assert.True(ColumnExists(verify, "server_sync_queue", "source_set_hash"));
        Assert.True(ColumnExists(verify, "field_comments", "review_revision"));
        Assert.True(ColumnExists(verify, "server_id_mappings", "server_file_hash_sha256"));
    }

    [Fact]
    public void ConflictAndAdministratorDiscardAuditSurviveServiceRestart()
    {
        var database = CreateDatabase();
        var suffix = Guid.NewGuid().ToString("N");
        var documentId = $"doc-conflict-{suffix}";
        var queueId = InsertConflict(database, documentId, suffix);

        var restarted = new ServerSyncService(new FlowNoteLocalDatabase(DatabasePath));
        var conflict = Assert.Single(restarted.ListQueueItems(), item => item.Id == queueId);
        Assert.Equal("CONFLICT", conflict.Status);
        Assert.Equal("STALE_REVISION", conflict.ConflictCode);
        Assert.Equal(3, conflict.BaseServerRevision);

        restarted.DiscardConflict(queueId, "user-admin", "서버 공개본을 유지하기로 확인");

        var afterSecondRestart = new ServerSyncService(new FlowNoteLocalDatabase(DatabasePath));
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
        var restarted = new ServerSyncService(new FlowNoteLocalDatabase(DatabasePath));
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

    private static FlowNoteLocalDatabase CreateDatabase()
    {
        var database = new FlowNoteLocalDatabase(DatabasePath);
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
                    {"detail":{"code":"STALE_REVISION","message":"stale","documentId":"server-document","expectedRevision":7,"currentRevision":8,"currentStatus":"PUBLISHED","currentLatestVersionId":"ver-latest","currentPublishedVersionId":"ver-public"}}
                    """,
                    Encoding.UTF8,
                    "application/json")
            };
        }
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
}
