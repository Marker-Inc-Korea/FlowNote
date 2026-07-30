using FlowNote.Windows.Core.Notifications;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Storage;

namespace FlowNote.Windows.Core.Sync;

public sealed class ServerReconciliationService(
    FlowNoteLocalDatabase database,
    ServerEpochGuardService epochGuard)
{
    public ServerBindingRecord? GetBinding(FlowNoteServerDocumentClient client) =>
        epochGuard.Get(
            ServerNotificationCursorService.NormalizeServerScope(client.BaseAddress));

    public async Task<ServerReconciliationRun> CreateRunAsync(
        FlowNoteServerDocumentClient client,
        string administratorUserId,
        CancellationToken cancellationToken = default)
    {
        var scope = ServerNotificationCursorService.NormalizeServerScope(client.BaseAddress);
        var binding = epochGuard.Get(scope)
            ?? throw new InvalidOperationException("먼저 서버 manifest를 확인해야 합니다.");
        if (!binding.ReconciliationRequired)
        {
            throw new InvalidOperationException("현재 서버는 reconciliation 필요 상태가 아닙니다.");
        }
        var cursor = GetHighestCursor(scope);
        var inventory = LoadInventory();
        var trigger = DetermineTrigger(binding, cursor);
        var run = await client.CreateReconciliationRunAsync(
            new ReconciliationRunCreateRequest
            {
                ClientId = $"wpf-{Environment.MachineName}",
                PreviousServerInstanceId = binding.ServerInstanceId,
                PreviousServerEpoch = binding.ServerEpoch,
                TriggerReason = trigger,
                ClientCursor = cursor,
                Items = inventory
            },
            cancellationToken);
        PersistRun(scope, administratorUserId, binding, run);
        return run;
    }

    public async Task<ServerReconciliationRun> ApplyRunAsync(
        FlowNoteServerDocumentClient client,
        string runId,
        string administratorUserId,
        string approvalReason,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(approvalReason))
        {
            throw new InvalidOperationException("reconciliation 승인 사유를 입력하세요.");
        }
        var items = ListItems(runId);
        var approved = await client.ApplyReconciliationRunAsync(
            runId,
            new ReconciliationApplyRequest
            {
                ApprovalReason = approvalReason.Trim(),
                Resolutions = items.Select(item => new ReconciliationResolutionRequest
                {
                    ItemId = item.ItemId,
                    Action = item.ProposedAction,
                    Reason = item.Details ?? "관리자 판정 확인"
                }).ToList()
            },
            cancellationToken);
        ApplyLocally(
            ServerNotificationCursorService.NormalizeServerScope(client.BaseAddress),
            approved,
            administratorUserId,
            approvalReason.Trim());
        return approved;
    }

    public IReadOnlyList<LocalReconciliationItem> ListItems(string? runId = null)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = runId is null
            ? """
              SELECT item_id, run_id, entity_type, local_id, local_version_no,
                     verdict, proposed_action, server_document_id, server_version_id,
                     server_revision, server_hash_sha256, details, resolution_action
                     ,resolution_status
              FROM reconciliation_items
              ORDER BY id DESC LIMIT 1000;
              """
            : """
              SELECT item_id, run_id, entity_type, local_id, local_version_no,
                     verdict, proposed_action, server_document_id, server_version_id,
                     server_revision, server_hash_sha256, details, resolution_action
                     ,resolution_status
              FROM reconciliation_items
              WHERE run_id = $run_id ORDER BY id;
              """;
        if (runId is not null)
        {
            command.Parameters.AddWithValue("$run_id", runId);
        }
        using var reader = command.ExecuteReader();
        var items = new List<LocalReconciliationItem>();
        while (reader.Read())
        {
            items.Add(new LocalReconciliationItem(
                reader.GetString(0), reader.GetString(1), reader.GetString(2), reader.GetString(3),
                reader.GetInt32(4), reader.GetString(5), reader.GetString(6),
                reader.IsDBNull(7) ? null : reader.GetString(7),
                reader.IsDBNull(8) ? null : reader.GetString(8),
                reader.IsDBNull(9) ? null : reader.GetInt32(9),
                reader.IsDBNull(10) ? null : reader.GetString(10),
                reader.IsDBNull(11) ? null : reader.GetString(11),
                reader.IsDBNull(12) ? null : reader.GetString(12),
                reader.IsDBNull(13) ? null : reader.GetString(13)));
        }
        return items;
    }

    public string? GetLatestReviewRunId()
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT run_id FROM reconciliation_runs WHERE status = 'REVIEW_REQUIRED' ORDER BY id DESC LIMIT 1;";
        return command.ExecuteScalar() as string;
    }

    private IReadOnlyList<ReconciliationInventoryItemRequest> LoadInventory()
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT queue.sync_id, queue.entity_type,
                   COALESCE(queue.local_document_id, queue.entity_id),
                   COALESCE(queue.local_version_no, 0), queue.idempotency_key,
                   queue.local_file_hash_sha256,
                   COALESCE(mapping.server_document_id, queue.server_document_id),
                   COALESCE(mapping.server_version_id, queue.server_version_id)
            FROM server_sync_queue AS queue
            LEFT JOIN server_id_mappings AS mapping
              ON mapping.entity_type = queue.entity_type
             AND mapping.local_id = COALESCE(queue.local_document_id, queue.entity_id)
             AND mapping.local_version_no = COALESCE(queue.local_version_no, 0)
            ORDER BY queue.id;
            """;
        using var reader = command.ExecuteReader();
        var items = new List<ReconciliationInventoryItemRequest>();
        while (reader.Read())
        {
            items.Add(new ReconciliationInventoryItemRequest
            {
                ClientItemId = reader.GetString(0),
                EntityType = reader.GetString(1),
                LocalId = reader.GetString(2),
                LocalVersionNo = reader.GetInt32(3),
                IdempotencyKey = reader.GetString(4),
                LocalHashSha256 = reader.IsDBNull(5) ? null : reader.GetString(5),
                PreviousServerDocumentId = reader.IsDBNull(6) ? null : reader.GetString(6),
                PreviousServerVersionId = reader.IsDBNull(7) ? null : reader.GetString(7)
            });
        }
        return items;
    }

    private long GetHighestCursor(string scope)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT COALESCE(MAX(last_success_cursor), 0) FROM server_notification_cursors WHERE server_scope = $scope;";
        command.Parameters.AddWithValue("$scope", scope);
        return Convert.ToInt64(command.ExecuteScalar());
    }

    private static string DetermineTrigger(ServerBindingRecord binding, long cursor)
    {
        if (!string.Equals(binding.ServerInstanceId, binding.ObservedServerInstanceId, StringComparison.Ordinal))
        {
            return "INSTANCE_CHANGED";
        }
        if (binding.ServerEpoch != binding.ObservedServerEpoch)
        {
            return "EPOCH_CHANGED";
        }
        var faultCode = string.IsNullOrWhiteSpace(binding.RestoreFaultCode)
            ? ServerRecoveryGuidance.InferFaultCode(binding.BlockReason)
            : binding.RestoreFaultCode.Trim().ToLowerInvariant();
        if (faultCode is "partial_restore" or "old_database_new_files" or "missing_file" or "wrong_server_epoch")
        {
            return faultCode.ToUpperInvariant();
        }
        return cursor > 0 ? "CURSOR_REGRESSED" : "SERVER_URL_CHANGED";
    }

    private void PersistRun(
        string scope,
        string createdBy,
        ServerBindingRecord binding,
        ServerReconciliationRun run)
    {
        using var connection = database.OpenConnection();
        using var transaction = connection.BeginTransaction();
        using (var command = connection.CreateCommand())
        {
            command.Transaction = transaction;
            command.CommandText = """
                INSERT OR IGNORE INTO reconciliation_runs (
                    run_id, server_scope, previous_server_instance_id, previous_server_epoch,
                    server_instance_id, server_epoch, trigger_reason, status, client_cursor,
                    server_cursor, created_by, created_at)
                VALUES ($run, $scope, $previous_instance, $previous_epoch, $instance, $epoch,
                        $trigger, $status, $client_cursor, $server_cursor, $created_by, $created_at);
                """;
            command.Parameters.AddWithValue("$run", run.RunId);
            command.Parameters.AddWithValue("$scope", scope);
            command.Parameters.AddWithValue("$previous_instance", binding.ServerInstanceId);
            command.Parameters.AddWithValue("$previous_epoch", binding.ServerEpoch);
            command.Parameters.AddWithValue("$instance", run.ServerInstanceId);
            command.Parameters.AddWithValue("$epoch", run.ServerEpoch);
            command.Parameters.AddWithValue("$trigger", run.TriggerReason);
            command.Parameters.AddWithValue("$status", run.Status);
            command.Parameters.AddWithValue("$client_cursor", run.ClientCursor);
            command.Parameters.AddWithValue("$server_cursor", run.ServerCursor);
            command.Parameters.AddWithValue("$created_by", createdBy);
            command.Parameters.AddWithValue("$created_at", DateTimeOffset.UtcNow.ToString("O"));
            command.ExecuteNonQuery();
        }
        foreach (var item in run.Items)
        {
            using var command = connection.CreateCommand();
            command.Transaction = transaction;
            command.CommandText = """
                INSERT OR IGNORE INTO reconciliation_items (
                    item_id, run_id, client_item_id, entity_type, local_id, local_version_no,
                    idempotency_key, local_hash_sha256, verdict, proposed_action,
                    server_document_id, server_version_id, server_revision, server_hash_sha256,
                    details, created_at)
                VALUES ($item, $run, $client_item, $entity, $local, $version, $key, $local_hash,
                        $verdict, $action, $document, $server_version, $revision, $server_hash,
                        $details, $created_at);
                """;
            command.Parameters.AddWithValue("$item", item.ItemId);
            command.Parameters.AddWithValue("$run", run.RunId);
            command.Parameters.AddWithValue("$client_item", item.ClientItemId);
            command.Parameters.AddWithValue("$entity", item.EntityType);
            command.Parameters.AddWithValue("$local", item.LocalId);
            command.Parameters.AddWithValue("$version", item.LocalVersionNo);
            command.Parameters.AddWithValue("$key", item.IdempotencyKey);
            command.Parameters.AddWithValue("$local_hash", (object?)item.LocalHashSha256 ?? DBNull.Value);
            command.Parameters.AddWithValue("$verdict", item.Verdict);
            command.Parameters.AddWithValue("$action", item.ProposedAction);
            command.Parameters.AddWithValue("$document", (object?)item.ServerDocumentId ?? DBNull.Value);
            command.Parameters.AddWithValue("$server_version", (object?)item.ServerVersionId ?? DBNull.Value);
            command.Parameters.AddWithValue("$revision", (object?)item.ServerRevision ?? DBNull.Value);
            command.Parameters.AddWithValue("$server_hash", (object?)item.ServerHashSha256 ?? DBNull.Value);
            command.Parameters.AddWithValue("$details", (object?)item.Details ?? DBNull.Value);
            command.Parameters.AddWithValue("$created_at", DateTimeOffset.UtcNow.ToString("O"));
            command.ExecuteNonQuery();
        }
        transaction.Commit();
    }

    private void ApplyLocally(
        string scope,
        ServerReconciliationRun run,
        string administratorUserId,
        string approvalReason)
    {
        using var connection = database.OpenConnection();
        using var transaction = connection.BeginTransaction();
        foreach (var item in run.Items)
        {
            ApplyItem(connection, transaction, item, administratorUserId);
        }
        using (var cursor = connection.CreateCommand())
        {
            cursor.Transaction = transaction;
            cursor.CommandText = """
                UPDATE server_notification_cursors
                SET last_success_cursor = 0, observed_server_cursor = 0, status = 'ACTIVE',
                    initial_sync_completed = 0, updated_at = $now,
                    reset_confirmed_by = $actor, reset_confirmed_at = $now
                WHERE server_scope = $scope;
                """;
            cursor.Parameters.AddWithValue("$scope", scope);
            cursor.Parameters.AddWithValue("$actor", administratorUserId);
            cursor.Parameters.AddWithValue("$now", DateTimeOffset.UtcNow.ToString("O"));
            cursor.ExecuteNonQuery();
        }
        using (var binding = connection.CreateCommand())
        {
            binding.Transaction = transaction;
            binding.CommandText = """
                UPDATE server_bindings
                SET server_instance_id = $instance, server_epoch = $epoch, status = 'ACTIVE',
                    observed_server_instance_id = $instance, observed_server_epoch = $epoch,
                    block_reason = NULL, updated_at = $now, approved_by = $actor, approved_at = $now,
                    convergence_status = 'POST_APPROVAL_RESTART_REQUIRED'
                WHERE server_scope = $scope;
                """;
            binding.Parameters.AddWithValue("$instance", run.ServerInstanceId);
            binding.Parameters.AddWithValue("$epoch", run.ServerEpoch);
            binding.Parameters.AddWithValue("$scope", scope);
            binding.Parameters.AddWithValue("$actor", administratorUserId);
            binding.Parameters.AddWithValue("$now", DateTimeOffset.UtcNow.ToString("O"));
            binding.ExecuteNonQuery();
        }
        using (var localRun = connection.CreateCommand())
        {
            localRun.Transaction = transaction;
            localRun.CommandText = """
                UPDATE reconciliation_runs SET status = 'APPLIED', approval_reason = $reason,
                    completed_at = $now WHERE run_id = $run;
                """;
            localRun.Parameters.AddWithValue("$reason", approvalReason);
            localRun.Parameters.AddWithValue("$now", DateTimeOffset.UtcNow.ToString("O"));
            localRun.Parameters.AddWithValue("$run", run.RunId);
            localRun.ExecuteNonQuery();
        }
        transaction.Commit();
    }

    private static void ApplyItem(
        Microsoft.Data.Sqlite.SqliteConnection connection,
        Microsoft.Data.Sqlite.SqliteTransaction transaction,
        ServerReconciliationItem item,
        string actor)
    {
        var now = DateTimeOffset.UtcNow.ToString("O");
        using (var audit = connection.CreateCommand())
        {
            audit.Transaction = transaction;
            audit.CommandText = """
                UPDATE reconciliation_items SET resolution_action = $action,
                    resolution_status = $status,
                    resolution_reason = $details, resolved_by = $actor, resolved_at = $now
                WHERE item_id = $item;
                """;
            audit.Parameters.AddWithValue("$action", item.ProposedAction);
            audit.Parameters.AddWithValue(
                "$status",
                item.ResolutionStatus ?? item.ProposedAction switch
                {
                    "REBOUND" => "REBOUND_CONFIRMED",
                    "REQUEUE" => "REQUEUED_FOR_RETRY",
                    _ => "APPROVED_CONFLICT"
                });
            audit.Parameters.AddWithValue("$details", (object?)item.Details ?? "관리자 판정 확인");
            audit.Parameters.AddWithValue("$actor", actor);
            audit.Parameters.AddWithValue("$now", now);
            audit.Parameters.AddWithValue("$item", item.ItemId);
            audit.ExecuteNonQuery();
        }
        using var queue = connection.CreateCommand();
        queue.Transaction = transaction;
        queue.CommandText = item.ProposedAction switch
        {
            "REBOUND" => """
                UPDATE server_sync_queue SET status = 'SYNCED', last_error = NULL, synced_at = $now,
                    server_document_id = $document, server_version_id = $version
                WHERE sync_id = $sync_id;
                """,
            "REQUEUE" => """
                UPDATE server_sync_queue SET status = 'PENDING', last_error = NULL,
                    conflict_code = NULL, conflict_details = NULL,
                    server_document_id = NULL, server_version_id = NULL
                WHERE sync_id = $sync_id;
                """,
            _ => """
                UPDATE server_sync_queue SET status = 'DISCARDED', conflict_code = 'RECONCILIATION_DIVERGED',
                    conflict_details = $details, resolution_action = 'CONFLICT',
                    resolution_reason = $details, resolved_by = $actor, resolved_at = $now
                WHERE sync_id = $sync_id;
                """
        };
        queue.Parameters.AddWithValue("$sync_id", item.ClientItemId);
        queue.Parameters.AddWithValue("$now", now);
        queue.Parameters.AddWithValue("$document", (object?)item.ServerDocumentId ?? DBNull.Value);
        queue.Parameters.AddWithValue("$version", (object?)item.ServerVersionId ?? DBNull.Value);
        queue.Parameters.AddWithValue("$details", (object?)item.Details ?? "payload/hash 불일치");
        queue.Parameters.AddWithValue("$actor", actor);
        queue.ExecuteNonQuery();

        if (item.ProposedAction == "REBOUND")
        {
            using var mapping = connection.CreateCommand();
            mapping.Transaction = transaction;
            mapping.CommandText = """
                INSERT INTO server_id_mappings (
                    entity_type, local_id, local_version_no, server_document_id,
                    server_version_id, server_revision, server_file_hash_sha256, synced_at)
                VALUES ($entity, $local, $local_version, $document, $version, $revision, $hash, $now)
                ON CONFLICT(entity_type, local_id, local_version_no) DO UPDATE SET
                    server_document_id = excluded.server_document_id,
                    server_version_id = excluded.server_version_id,
                    server_revision = excluded.server_revision,
                    server_file_hash_sha256 = excluded.server_file_hash_sha256,
                    synced_at = excluded.synced_at;
                """;
            mapping.Parameters.AddWithValue("$entity", item.EntityType);
            mapping.Parameters.AddWithValue("$local", item.LocalId);
            mapping.Parameters.AddWithValue("$local_version", item.LocalVersionNo);
            mapping.Parameters.AddWithValue("$document", (object?)item.ServerDocumentId ?? DBNull.Value);
            mapping.Parameters.AddWithValue("$version", (object?)item.ServerVersionId ?? DBNull.Value);
            mapping.Parameters.AddWithValue("$revision", (object?)item.ServerRevision ?? DBNull.Value);
            mapping.Parameters.AddWithValue("$hash", (object?)item.ServerHashSha256 ?? DBNull.Value);
            mapping.Parameters.AddWithValue("$now", now);
            mapping.ExecuteNonQuery();

            using var document = connection.CreateCommand();
            document.Transaction = transaction;
            document.CommandText = """
                UPDATE documents SET server_document_id = $document,
                    server_version_id = COALESCE($version, server_version_id),
                    server_revision = $revision, synced_at = $now
                WHERE document_id = $local;
                UPDATE document_versions SET server_version_id = $version, synced_at = $now
                WHERE document_id = $local AND version_no = $local_version AND $version IS NOT NULL;
                UPDATE server_sync_queue SET
                    server_document_id = COALESCE($document, server_document_id),
                    base_server_revision = COALESCE($revision, base_server_revision),
                    expected_server_version_id = COALESCE($version, expected_server_version_id)
                WHERE COALESCE(local_document_id, entity_id) = $local
                  AND status IN ('PENDING', 'FAILED');
                """;
            document.Parameters.AddWithValue("$document", (object?)item.ServerDocumentId ?? DBNull.Value);
            document.Parameters.AddWithValue("$version", (object?)item.ServerVersionId ?? DBNull.Value);
            document.Parameters.AddWithValue("$revision", (object?)item.ServerRevision ?? DBNull.Value);
            document.Parameters.AddWithValue("$local", item.LocalId);
            document.Parameters.AddWithValue("$local_version", item.LocalVersionNo);
            document.Parameters.AddWithValue("$now", now);
            document.ExecuteNonQuery();
        }
        else
        {
            using var orphan = connection.CreateCommand();
            orphan.Transaction = transaction;
            orphan.CommandText = """
                UPDATE server_id_mappings SET server_document_id = NULL, server_version_id = NULL,
                    server_report_id = NULL, server_comment_id = NULL, server_attachment_id = NULL,
                    server_log_id = NULL, server_revision = NULL, server_file_hash_sha256 = NULL,
                    synced_at = $now
                WHERE entity_type = $entity AND local_id = $local AND local_version_no = $local_version;
                UPDATE documents SET server_document_id = NULL, server_version_id = NULL,
                    server_revision = NULL, server_published_version_id = NULL, synced_at = NULL
                WHERE document_id = $local AND $entity = 'document';
                """;
            orphan.Parameters.AddWithValue("$entity", item.EntityType);
            orphan.Parameters.AddWithValue("$local", item.LocalId);
            orphan.Parameters.AddWithValue("$local_version", item.LocalVersionNo);
            orphan.Parameters.AddWithValue("$now", now);
            orphan.ExecuteNonQuery();
        }
    }
}
