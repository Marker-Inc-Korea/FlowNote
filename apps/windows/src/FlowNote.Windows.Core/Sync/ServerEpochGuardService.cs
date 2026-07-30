using FlowNote.Windows.Core.Notifications;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Storage;
using Microsoft.Data.Sqlite;

namespace FlowNote.Windows.Core.Sync;

public sealed class ServerEpochGuardService(FlowNoteLocalDatabase database)
{
    public const string ActiveStatus = "ACTIVE";
    public const string ReconciliationRequiredStatus = "RECONCILIATION_REQUIRED";
    public const int SupportedApiContract = 1;
    private static readonly HashSet<string> RestoreFaultCodes =
    [
        "partial_restore",
        "old_database_new_files",
        "missing_file",
        "wrong_server_epoch"
    ];

    public async Task<ServerBindingRecord> EnsureReadyAsync(
        FlowNoteServerDocumentClient client,
        long clientCursor = 0,
        CancellationToken cancellationToken = default)
    {
        var manifest = await client.GetSyncManifestAsync(cancellationToken);
        var scope = ServerNotificationCursorService.NormalizeServerScope(client.BaseAddress);
        return Observe(scope, manifest, clientCursor, throwWhenBlocked: true);
    }

    public ServerBindingRecord Observe(
        string serverScope,
        ServerSyncManifest manifest,
        long clientCursor,
        bool throwWhenBlocked = false)
    {
        var scope = ServerNotificationCursorService.NormalizeServerScope(new Uri(serverScope));
        ValidateManifest(manifest);
        using var connection = database.OpenConnection();
        using var transaction = connection.BeginTransaction();
        var existing = Get(connection, transaction, scope);
        if (existing is null)
        {
            var hasOtherBinding = HasOtherBinding(connection, transaction, scope);
            var manifestFaultReason = DetermineManifestFaultReason(manifest);
            var reason = manifestFaultReason ??
                (hasOtherBinding ? "저장된 서버 URL과 다른 주소가 감지되었습니다." : null);
            Insert(
                connection,
                transaction,
                scope,
                manifest,
                reason is null ? ActiveStatus : ReconciliationRequiredStatus,
                reason);
        }
        else
        {
            var sameApprovedFaultMarker =
                existing.ConvergenceStatus == "POST_APPROVAL_RESTART_REQUIRED" &&
                !string.IsNullOrWhiteSpace(manifest.RestoreFaultCode) &&
                string.Equals(
                    existing.RestorePilotRunId,
                    manifest.RestorePilotRunId,
                    StringComparison.Ordinal);
            var markerClearedAfterApproval =
                existing.ConvergenceStatus == "POST_APPROVAL_RESTART_REQUIRED" &&
                string.IsNullOrWhiteSpace(manifest.RestoreFaultCode);
            var reason = sameApprovedFaultMarker
                ? null
                : DetermineBlockReason(existing, manifest, clientCursor);
            UpdateObservation(
                connection,
                transaction,
                scope,
                manifest,
                reason,
                markerClearedAfterApproval);
        }
        transaction.Commit();
        var binding = Get(scope) ?? throw new InvalidOperationException("서버 binding 저장에 실패했습니다.");
        if (throwWhenBlocked && binding.TrafficBlocked)
        {
            throw new ServerReconciliationRequiredException(
                binding.BlockReason ??
                "재결합 승인은 적용됐지만 복구 장애 표지가 남아 있어 서버 재시작이 필요합니다.");
        }
        return binding;
    }

    public ServerBindingRecord? Get(string serverScope)
    {
        var scope = ServerNotificationCursorService.NormalizeServerScope(new Uri(serverScope));
        using var connection = database.OpenConnection();
        return Get(connection, null, scope);
    }

    private static void ValidateManifest(ServerSyncManifest manifest)
    {
        if (string.IsNullOrWhiteSpace(manifest.ServerInstanceId) || manifest.ServerEpoch < 1)
        {
            throw new InvalidOperationException("서버 sync manifest의 instance/epoch 값이 유효하지 않습니다.");
        }
        if (manifest.ApiContractMin > SupportedApiContract || manifest.ApiContractMax < SupportedApiContract)
        {
            throw new InvalidOperationException(
                $"서버 API 계약 범위({manifest.ApiContractMin}~{manifest.ApiContractMax})가 이 WPF 계약({SupportedApiContract})과 호환되지 않습니다.");
        }
        if (!string.IsNullOrWhiteSpace(manifest.RestoreFaultCode) &&
            !RestoreFaultCodes.Contains(manifest.RestoreFaultCode.Trim().ToLowerInvariant()))
        {
            throw new InvalidOperationException(
                $"지원하지 않는 복구 장애 코드입니다: {manifest.RestoreFaultCode}");
        }
        if (!string.IsNullOrWhiteSpace(manifest.RestoreFaultCode) &&
            new[]
            {
                manifest.RestorePilotRunId,
                manifest.RestoreBackupSetId,
                manifest.RestoreApprovalId,
                manifest.RestoreResponsibleOwner
            }.Any(string.IsNullOrWhiteSpace))
        {
            throw new InvalidOperationException(
                "복구 장애 manifest에 run ID, backup set ID, 복구 승인 ID 또는 담당자가 없습니다.");
        }
    }

    private static string? DetermineBlockReason(
        ServerBindingRecord existing,
        ServerSyncManifest manifest,
        long clientCursor)
    {
        var manifestFaultReason = DetermineManifestFaultReason(manifest);
        if (manifestFaultReason is not null)
        {
            return manifestFaultReason;
        }
        if (!string.Equals(existing.ServerInstanceId, manifest.ServerInstanceId, StringComparison.Ordinal))
        {
            return "서버 instance ID가 변경되었습니다. 다른 서버 연결 또는 빈 DB 초기화 여부를 확인하세요.";
        }
        if (existing.ServerEpoch != manifest.ServerEpoch)
        {
            return $"서버 epoch가 {existing.ServerEpoch}에서 {manifest.ServerEpoch}(으)로 변경되었습니다. 복구 범위를 확인하세요.";
        }
        if (manifest.ServerCursor < clientCursor)
        {
            return $"서버 cursor({manifest.ServerCursor})가 로컬 cursor({clientCursor})보다 낮습니다. 이전 시점 복구 여부를 확인하세요.";
        }
        return existing.ReconciliationRequired
            ? existing.BlockReason ?? "관리자 reconciliation 승인이 필요합니다."
            : null;
    }

    private static string? DetermineManifestFaultReason(ServerSyncManifest manifest)
    {
        if (string.IsNullOrWhiteSpace(manifest.RestoreFaultCode))
        {
            return null;
        }
        return ServerRecoveryGuidance.ForFault(
            manifest.RestoreFaultCode.Trim().ToLowerInvariant(),
            manifest.RestoreBlockReason).BlockCause;
    }

    private static bool HasOtherBinding(SqliteConnection connection, SqliteTransaction transaction, string scope)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = "SELECT COUNT(*) FROM server_bindings WHERE server_scope <> $scope;";
        command.Parameters.AddWithValue("$scope", scope);
        return Convert.ToInt64(command.ExecuteScalar()) > 0;
    }

    private static void Insert(
        SqliteConnection connection,
        SqliteTransaction transaction,
        string scope,
        ServerSyncManifest manifest,
        string status,
        string? reason)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            INSERT INTO server_bindings (
                server_scope, server_instance_id, server_epoch, schema_contract,
                api_contract_min, api_contract_max, status,
                observed_server_instance_id, observed_server_epoch, block_reason, updated_at,
                restore_pilot_run_id, restore_backup_set_id, restore_approval_id,
                restore_responsible_owner, restore_fault_code, convergence_status)
            VALUES ($scope, $instance, $epoch, $schema, $min, $max, $status,
                    $observed_instance, $observed_epoch, $reason, $updated_at,
                    $restore_run, $backup_set, $restore_approval, $restore_owner, $restore_fault,
                    $convergence);
            """;
        AddManifestParameters(command, scope, manifest, status, reason);
        command.ExecuteNonQuery();
    }

    private static void UpdateObservation(
        SqliteConnection connection,
        SqliteTransaction transaction,
        string scope,
        ServerSyncManifest manifest,
        string? reason,
        bool markerClearedAfterApproval)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            UPDATE server_bindings
            SET schema_contract = $schema,
                api_contract_min = $min,
                api_contract_max = $max,
                status = CASE WHEN $reason IS NULL AND status = 'ACTIVE' THEN 'ACTIVE' ELSE 'RECONCILIATION_REQUIRED' END,
                observed_server_instance_id = $observed_instance,
                observed_server_epoch = $observed_epoch,
                block_reason = COALESCE($reason, block_reason),
                restore_pilot_run_id = COALESCE($restore_run, restore_pilot_run_id),
                restore_backup_set_id = COALESCE($backup_set, restore_backup_set_id),
                restore_approval_id = COALESCE($restore_approval, restore_approval_id),
                restore_responsible_owner = COALESCE($restore_owner, restore_responsible_owner),
                restore_fault_code = CASE
                    WHEN $marker_cleared = 1 THEN NULL
                    ELSE COALESCE($restore_fault, restore_fault_code)
                END,
                convergence_status = CASE
                    WHEN $reason IS NOT NULL THEN 'APPROVAL_REQUIRED'
                    WHEN $marker_cleared = 1 THEN 'POST_APPROVAL_VERIFICATION_REQUIRED'
                    WHEN convergence_status = 'POST_APPROVAL_RESTART_REQUIRED'
                        THEN convergence_status
                    ELSE 'NORMAL_OPERATION'
                END,
                updated_at = $updated_at
            WHERE server_scope = $scope;
            """;
        AddManifestParameters(command, scope, manifest, ActiveStatus, reason);
        command.Parameters.AddWithValue(
            "$marker_cleared",
            markerClearedAfterApproval ? 1 : 0);
        command.ExecuteNonQuery();
    }

    private static void AddManifestParameters(
        SqliteCommand command,
        string scope,
        ServerSyncManifest manifest,
        string status,
        string? reason)
    {
        command.Parameters.AddWithValue("$scope", scope);
        command.Parameters.AddWithValue("$instance", manifest.ServerInstanceId);
        command.Parameters.AddWithValue("$epoch", manifest.ServerEpoch);
        command.Parameters.AddWithValue("$schema", manifest.SchemaContract);
        command.Parameters.AddWithValue("$min", manifest.ApiContractMin);
        command.Parameters.AddWithValue("$max", manifest.ApiContractMax);
        command.Parameters.AddWithValue("$status", status);
        command.Parameters.AddWithValue("$observed_instance", manifest.ServerInstanceId);
        command.Parameters.AddWithValue("$observed_epoch", manifest.ServerEpoch);
        command.Parameters.AddWithValue("$reason", (object?)reason ?? DBNull.Value);
        command.Parameters.AddWithValue("$updated_at", DateTimeOffset.UtcNow.ToString("O"));
        command.Parameters.AddWithValue(
            "$restore_run",
            (object?)manifest.RestorePilotRunId ?? DBNull.Value);
        command.Parameters.AddWithValue(
            "$backup_set",
            (object?)manifest.RestoreBackupSetId ?? DBNull.Value);
        command.Parameters.AddWithValue(
            "$restore_approval",
            (object?)manifest.RestoreApprovalId ?? DBNull.Value);
        command.Parameters.AddWithValue(
            "$restore_owner",
            (object?)manifest.RestoreResponsibleOwner ?? DBNull.Value);
        command.Parameters.AddWithValue(
            "$restore_fault",
            (object?)manifest.RestoreFaultCode ?? DBNull.Value);
        command.Parameters.AddWithValue(
            "$convergence",
            reason is null ? "NORMAL_OPERATION" : "APPROVAL_REQUIRED");
    }

    private static ServerBindingRecord? Get(
        SqliteConnection connection,
        SqliteTransaction? transaction,
        string scope)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            SELECT server_instance_id, server_epoch, status,
                   observed_server_instance_id, observed_server_epoch, block_reason,
                   restore_pilot_run_id, restore_backup_set_id, restore_approval_id,
                   restore_responsible_owner, restore_fault_code, convergence_status
            FROM server_bindings WHERE server_scope = $scope;
            """;
        command.Parameters.AddWithValue("$scope", scope);
        using var reader = command.ExecuteReader();
        return reader.Read()
            ? new ServerBindingRecord(
                scope,
                reader.GetString(0),
                reader.GetInt32(1),
                reader.GetString(2),
                reader.IsDBNull(3) ? null : reader.GetString(3),
                reader.IsDBNull(4) ? null : reader.GetInt32(4),
                reader.IsDBNull(5) ? null : reader.GetString(5),
                reader.IsDBNull(6) ? null : reader.GetString(6),
                reader.IsDBNull(7) ? null : reader.GetString(7),
                reader.IsDBNull(8) ? null : reader.GetString(8),
                reader.IsDBNull(9) ? null : reader.GetString(9),
                reader.IsDBNull(10) ? null : reader.GetString(10),
                reader.IsDBNull(11) ? "NORMAL_OPERATION" : reader.GetString(11))
            : null;
    }
}

public sealed class ServerReconciliationRequiredException(string message) : InvalidOperationException(message);
