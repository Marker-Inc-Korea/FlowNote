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
            Insert(
                connection,
                transaction,
                scope,
                manifest,
                hasOtherBinding ? ReconciliationRequiredStatus : ActiveStatus,
                hasOtherBinding ? "저장된 서버 URL과 다른 주소가 감지되었습니다." : null);
        }
        else
        {
            var reason = DetermineBlockReason(existing, manifest, clientCursor);
            UpdateObservation(connection, transaction, scope, manifest, reason);
        }
        transaction.Commit();
        var binding = Get(scope) ?? throw new InvalidOperationException("서버 binding 저장에 실패했습니다.");
        if (throwWhenBlocked && binding.ReconciliationRequired)
        {
            throw new ServerReconciliationRequiredException(
                binding.BlockReason ?? "서버 복구 경계가 감지되어 reconciliation이 필요합니다.");
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
    }

    private static string? DetermineBlockReason(
        ServerBindingRecord existing,
        ServerSyncManifest manifest,
        long clientCursor)
    {
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
                observed_server_instance_id, observed_server_epoch, block_reason, updated_at)
            VALUES ($scope, $instance, $epoch, $schema, $min, $max, $status,
                    $observed_instance, $observed_epoch, $reason, $updated_at);
            """;
        AddManifestParameters(command, scope, manifest, status, reason);
        command.ExecuteNonQuery();
    }

    private static void UpdateObservation(
        SqliteConnection connection,
        SqliteTransaction transaction,
        string scope,
        ServerSyncManifest manifest,
        string? reason)
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
                updated_at = $updated_at
            WHERE server_scope = $scope;
            """;
        AddManifestParameters(command, scope, manifest, ActiveStatus, reason);
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
                   observed_server_instance_id, observed_server_epoch, block_reason
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
                reader.IsDBNull(5) ? null : reader.GetString(5))
            : null;
    }
}

public sealed class ServerReconciliationRequiredException(string message) : InvalidOperationException(message);
