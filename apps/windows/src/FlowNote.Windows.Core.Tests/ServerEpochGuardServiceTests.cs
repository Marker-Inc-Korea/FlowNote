using FlowNote.Windows.Core.Storage;
using FlowNote.Windows.Core.Sync;
using FlowNote.Windows.Core.ServerApi;
using System.Net;
using System.Text;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class ServerEpochGuardServiceTests
{
    [Theory]
    [InlineData("partial_restore", "부분 복구")]
    [InlineData("old_database_new_files", "이전 시점 DB")]
    [InlineData("missing_file", "원천 파일")]
    [InlineData("wrong_server_epoch", "서버 epoch")]
    public void EachRestoreFaultShowsCausePreservationProhibitionAndNextStep(
        string faultCode,
        string expectedCause)
    {
        var guidance = ServerRecoveryGuidance.ForFault(
            faultCode, "장애 주입 증거를 보존했습니다.");

        Assert.Contains(expectedCause, guidance.BlockCause);
        Assert.Contains("동기화 큐", guidance.PreservedSources);
        Assert.Contains("message_id", guidance.PreservedSources);
        Assert.Contains("자동 전송", guidance.ProhibitedActions);
        Assert.Contains("polling", guidance.ProhibitedActions);
        Assert.Contains("삭제·덮어쓰기", guidance.ProhibitedActions);
        Assert.Contains("backup-set-id", guidance.NextStep);
        Assert.Contains("restore-approval-id", guidance.NextStep);
        Assert.Contains("승인 적용", guidance.NextStep);
    }

    [Theory]
    [InlineData("partial_restore")]
    [InlineData("old_database_new_files")]
    [InlineData("missing_file")]
    [InlineData("wrong_server_epoch")]
    public void ExplicitRestoreFaultManifestBlocksFirstSendAndPollingObservation(
        string faultCode)
    {
        var artifactDirectory = Path.Combine(
            Path.GetTempPath(),
            "flownote-restore-fault-guard-tests",
            Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(artifactDirectory);
        var database = new FlowNoteLocalDatabase(
            Path.Combine(artifactDirectory, "flownote.local.sqlite"));
        database.Initialize();
        var service = new ServerEpochGuardService(database);
        var manifest = FaultManifest(faultCode, "자동 장애 주입 검증");

        var binding = service.Observe(
            "https://factory-restore.example/", manifest, clientCursor: 0);

        Assert.True(binding.ReconciliationRequired);
        Assert.Contains("자동 장애 주입 검증", binding.BlockReason);
        Assert.Equal("PILOT-20260730-FAULT-001", binding.RestorePilotRunId);
        Assert.Equal("BACKUP-RESTORE-001", binding.RestoreBackupSetId);
        Assert.Equal("RESTORE-APPROVAL-001", binding.RestoreApprovalId);
        Assert.Equal("data-owner-01", binding.RestoreResponsibleOwner);
        Assert.Equal(faultCode, binding.RestoreFaultCode);
        Assert.Equal("APPROVAL_REQUIRED", binding.ConvergenceStatus);
        var guidance = ServerRecoveryGuidance.FromBinding(binding);
        Assert.Contains("안전 수렴", guidance.ConnectionStatus);
        Assert.Equal("data-owner-01", guidance.ResponsibleOwner);
        Assert.Contains("BACKUP-RESTORE-001", guidance.EvidenceBinding);
        Assert.Contains("FLOWNOTE_RESTORE_*", guidance.NextStep);
        Assert.Throws<ServerReconciliationRequiredException>(() =>
            service.Observe(
                "https://factory-restore.example/",
                manifest,
                clientCursor: 0,
                throwWhenBlocked: true));
    }

    [Theory]
    [InlineData("partial_restore")]
    [InlineData("old_database_new_files")]
    [InlineData("missing_file")]
    [InlineData("wrong_server_epoch")]
    public async Task EachRestoreFaultRequiresApprovalBeforeNormalOperationResumes(
        string faultCode)
    {
        var artifactDirectory = Path.Combine(
            Path.GetTempPath(),
            "flownote-restore-rejoin-tests",
            Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(artifactDirectory);
        var database = new FlowNoteLocalDatabase(
            Path.Combine(artifactDirectory, "flownote.local.sqlite"));
        database.Initialize();
        var guard = new ServerEpochGuardService(database);
        const string scope = "https://factory-fault-rejoin.example/";
        var faultManifest = FaultManifest(faultCode, "복구 장애 주입");
        Assert.True(guard.Observe(scope, faultManifest, 0).ReconciliationRequired);
        SeedReconciliationState(database, scope);

        using var http = new HttpClient(
            new ReconciliationHandler(faultCode.ToUpperInvariant()))
        {
            BaseAddress = new Uri(scope)
        };
        var client = new FlowNoteServerDocumentClient(http);
        var service = new ServerReconciliationService(database, guard);
        var run = await service.CreateRunAsync(client, "user-admin");
        Assert.Equal(faultCode.ToUpperInvariant(), run.TriggerReason);
        Assert.True(guard.Get(scope)?.ReconciliationRequired);

        await service.ApplyRunAsync(
            client, run.RunId, "user-admin", $"{faultCode} 원천 대조 승인");
        var awaitingRestart = guard.Get(scope);
        Assert.NotNull(awaitingRestart);
        Assert.False(awaitingRestart.ReconciliationRequired);
        Assert.True(awaitingRestart.TrafficBlocked);
        Assert.Equal(
            "POST_APPROVAL_RESTART_REQUIRED",
            awaitingRestart.ConvergenceStatus);
        var markerStillPresent = guard.Observe(scope, faultManifest, clientCursor: 0);
        Assert.False(markerStillPresent.ReconciliationRequired);
        Assert.True(markerStillPresent.TrafficBlocked);

        var resumed = guard.Observe(
            scope,
            Manifest("srv-new", 2, 0),
            clientCursor: 0);

        Assert.False(resumed.ReconciliationRequired);
        Assert.False(resumed.TrafficBlocked);
        using var connection = database.OpenConnection();
        Assert.Equal(
            "ACTIVE",
            ScalarText(
                connection,
                "SELECT status FROM server_bindings " +
                "WHERE server_scope='https://factory-fault-rejoin.example/';"));
        Assert.Equal(
            "POST_APPROVAL_VERIFICATION_REQUIRED",
            ScalarText(
                connection,
                "SELECT convergence_status FROM server_bindings " +
                "WHERE server_scope='https://factory-fault-rejoin.example/';"));
        Assert.Equal(
            1L,
            Scalar(
                connection,
                "SELECT COUNT(*) FROM reconciliation_runs " +
                "WHERE status='APPLIED';"));
    }

    [Fact]
    public void EpochChangeAndCursorRegressionBlockWithoutDeletingSyncState()
    {
        var artifactDirectory = Path.Combine(
            Path.GetTempPath(),
            "flownote-epoch-guard-tests",
            Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(artifactDirectory);
        var database = new FlowNoteLocalDatabase(Path.Combine(artifactDirectory, "flownote.local.sqlite"));
        database.Initialize();
        var service = new ServerEpochGuardService(database);
        const string scope = "https://factory-server.example/";

        var active = service.Observe(scope, Manifest("srv-a", 4, 20), clientCursor: 12);
        Assert.False(active.ReconciliationRequired);

        using (var connection = database.OpenConnection())
        using (var queue = connection.CreateCommand())
        {
            queue.CommandText = """
                INSERT INTO server_sync_queue (
                    sync_id, entity_type, entity_id, action, idempotency_key, status, created_at)
                VALUES ('sync-preserved', 'document', 'doc-local', 'register_document',
                        'wpf:document:doc-local:v1', 'PENDING', $now);
                """;
            queue.Parameters.AddWithValue("$now", DateTimeOffset.UtcNow.ToString("O"));
            queue.ExecuteNonQuery();
        }

        var epochChanged = service.Observe(scope, Manifest("srv-a", 5, 20), clientCursor: 12);
        Assert.True(epochChanged.ReconciliationRequired);
        Assert.Contains("epoch", epochChanged.BlockReason);

        var stillBlocked = service.Observe(scope, Manifest("srv-a", 4, 10), clientCursor: 12);
        Assert.True(stillBlocked.ReconciliationRequired);
        using var verification = database.OpenConnection();
        using var command = verification.CreateCommand();
        command.CommandText = "SELECT COUNT(*) FROM server_sync_queue WHERE sync_id = 'sync-preserved';";
        Assert.Equal(1L, Convert.ToInt64(command.ExecuteScalar()));
    }

    [Fact]
    public void DifferentNormalizedUrlRequiresAdministratorReconciliation()
    {
        var artifactDirectory = Path.Combine(
            Path.GetTempPath(),
            "flownote-epoch-guard-tests",
            Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(artifactDirectory);
        var database = new FlowNoteLocalDatabase(Path.Combine(artifactDirectory, "flownote.local.sqlite"));
        database.Initialize();
        var service = new ServerEpochGuardService(database);

        Assert.False(service.Observe("https://SERVER-A.example", Manifest("srv-a", 1, 0), 0).ReconciliationRequired);
        var wrongUrl = service.Observe("https://server-b.example/api", Manifest("srv-b", 1, 0), 0);

        Assert.True(wrongUrl.ReconciliationRequired);
        Assert.Contains("다른 주소", wrongUrl.BlockReason);
    }

    private static ServerSyncManifest Manifest(string instanceId, int epoch, long cursor) => new()
    {
        ServerInstanceId = instanceId,
        ServerEpoch = epoch,
        SchemaContract = 1,
        ApiContractMin = 1,
        ApiContractMax = 1,
        ServerCursor = cursor
    };

    private static ServerSyncManifest FaultManifest(string faultCode, string reason) =>
        Manifest("srv-new", 2, 0) with
        {
            RestoreFaultCode = faultCode,
            RestoreBlockReason = reason,
            RestorePilotRunId = "PILOT-20260730-FAULT-001",
            RestoreBackupSetId = "BACKUP-RESTORE-001",
            RestoreApprovalId = "RESTORE-APPROVAL-001",
            RestoreResponsibleOwner = "data-owner-01",
            SafeConvergence = false
        };

    [Fact]
    public async Task AdministratorApplyRebindsWithoutDeletingQueueOrProcessedMessages()
    {
        var artifactDirectory = Path.Combine(
            Path.GetTempPath(), "flownote-reconciliation-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(artifactDirectory);
        var database = new FlowNoteLocalDatabase(Path.Combine(artifactDirectory, "flownote.local.sqlite"));
        database.Initialize();
        var guard = new ServerEpochGuardService(database);
        const string scope = "https://factory-recovery.example/";
        guard.Observe(scope, Manifest("srv-old", 1, 10), 10);
        guard.Observe(scope, Manifest("srv-new", 2, 0), 10);
        SeedReconciliationState(database, scope);

        using var http = new HttpClient(new ReconciliationHandler()) { BaseAddress = new Uri(scope) };
        var client = new FlowNoteServerDocumentClient(http);
        var service = new ServerReconciliationService(database, guard);
        var run = await service.CreateRunAsync(client, "user-admin");
        Assert.Equal("REVIEW_REQUIRED", run.Status);

        await service.ApplyRunAsync(client, run.RunId, "user-admin", "복구 원천 대조 완료");

        using var connection = database.OpenConnection();
        Assert.Equal(1L, Scalar(connection, "SELECT COUNT(*) FROM server_sync_queue WHERE sync_id='sync-doc' AND status='SYNCED';"));
        Assert.Equal(1L, Scalar(connection, "SELECT COUNT(*) FROM server_sync_queue WHERE sync_id='sync-doc';"));
        Assert.Equal(1L, Scalar(connection, "SELECT COUNT(*) FROM server_notification_messages WHERE message_id='message-preserved';"));
        Assert.Equal(0L, Scalar(connection, "SELECT last_success_cursor FROM server_notification_cursors WHERE server_scope='https://factory-recovery.example/';"));
        Assert.Equal("server-doc-new", ScalarText(connection, "SELECT server_document_id FROM server_id_mappings WHERE entity_type='document' AND local_id='doc-local';"));
        Assert.Equal("ACTIVE", ScalarText(connection, "SELECT status FROM server_bindings WHERE server_scope='https://factory-recovery.example/';"));
        Assert.Equal(1L, Scalar(connection, "SELECT COUNT(*) FROM reconciliation_items WHERE verdict='CONFIRMED' AND resolution_action='REBOUND';"));
    }

    private static void SeedReconciliationState(FlowNoteLocalDatabase database, string scope)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            INSERT INTO server_sync_queue (
                sync_id, entity_type, entity_id, action, local_document_id, local_version_no,
                idempotency_key, status, created_at, local_file_hash_sha256)
            VALUES ('sync-doc', 'document', 'doc-local', 'register_document', 'doc-local', 1,
                    'wpf:document:doc-local:v1', 'SYNCED', $now,
                    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');
            INSERT INTO server_id_mappings (
                entity_type, local_id, local_version_no, server_document_id, server_version_id,
                server_revision, server_file_hash_sha256, synced_at)
            VALUES ('document', 'doc-local', 1, 'server-doc-old', 'server-ver-old', 1,
                    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', $now);
            INSERT INTO server_notification_cursors (
                server_scope, user_id, last_success_cursor, observed_server_cursor,
                status, initial_sync_completed, updated_at)
            VALUES ($scope, 'user-admin', 10, 10, 'ACTIVE', 1, $now);
            INSERT INTO server_notification_messages (
                server_scope, user_id, message_id, cursor, processed_at)
            VALUES ($scope, 'user-admin', 'message-preserved', 7, $now);
            """;
        command.Parameters.AddWithValue("$scope", scope);
        command.Parameters.AddWithValue("$now", DateTimeOffset.UtcNow.ToString("O"));
        command.ExecuteNonQuery();
    }

    private static long Scalar(Microsoft.Data.Sqlite.SqliteConnection connection, string sql)
    {
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        return Convert.ToInt64(command.ExecuteScalar());
    }

    private static string ScalarText(Microsoft.Data.Sqlite.SqliteConnection connection, string sql)
    {
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        return Convert.ToString(command.ExecuteScalar())!;
    }

    private sealed class ReconciliationHandler(
        string triggerReason = "INSTANCE_CHANGED") : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            var applied = request.RequestUri?.AbsolutePath.EndsWith("/apply", StringComparison.Ordinal) == true;
            var status = applied ? "APPLIED" : "REVIEW_REQUIRED";
            var json = $$"""
                {
                  "run_id":"recon-test-run",
                  "server_instance_id":"srv-new",
                  "server_epoch":2,
                  "trigger_reason":"{{triggerReason}}",
                  "status":"{{status}}",
                  "client_cursor":10,
                  "server_cursor":0,
                  "items":[{
                    "item_id":"recon-item-test",
                    "client_item_id":"sync-doc",
                    "entity_type":"document",
                    "local_id":"doc-local",
                    "local_version_no":1,
                    "idempotency_key":"wpf:document:doc-local:v1",
                    "local_hash_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "verdict":"CONFIRMED",
                    "proposed_action":"REBOUND",
                    "server_document_id":"server-doc-new",
                    "server_version_id":"server-ver-new",
                    "server_revision":3,
                    "server_hash_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "details":"동일 key/hash 원천을 확인했습니다."
                  }]
                }
                """;
            return Task.FromResult(new HttpResponseMessage(
                request.Method == HttpMethod.Post ? HttpStatusCode.OK : HttpStatusCode.NotFound)
            {
                Content = new StringContent(json, Encoding.UTF8, "application/json")
            });
        }
    }
}
