using System.Text.Json.Serialization;

namespace FlowNote.Windows.Core.Sync;

public sealed record ServerSyncManifest
{
    [JsonPropertyName("server_instance_id")]
    public string ServerInstanceId { get; init; } = string.Empty;

    [JsonPropertyName("server_epoch")]
    public int ServerEpoch { get; init; }

    [JsonPropertyName("schema_contract")]
    public int SchemaContract { get; init; }

    [JsonPropertyName("api_contract_min")]
    public int ApiContractMin { get; init; }

    [JsonPropertyName("api_contract_max")]
    public int ApiContractMax { get; init; }

    [JsonPropertyName("server_cursor")]
    public long ServerCursor { get; init; }

    [JsonPropertyName("restore_fault_code")]
    public string? RestoreFaultCode { get; init; }

    [JsonPropertyName("restore_block_reason")]
    public string? RestoreBlockReason { get; init; }

    [JsonPropertyName("restore_pilot_run_id")]
    public string? RestorePilotRunId { get; init; }

    [JsonPropertyName("restore_backup_set_id")]
    public string? RestoreBackupSetId { get; init; }

    [JsonPropertyName("restore_approval_id")]
    public string? RestoreApprovalId { get; init; }

    [JsonPropertyName("restore_responsible_owner")]
    public string? RestoreResponsibleOwner { get; init; }

    [JsonPropertyName("safe_convergence")]
    public bool? SafeConvergence { get; init; }
}

public sealed record ReconciliationInventoryItemRequest
{
    [JsonPropertyName("clientItemId")]
    public string ClientItemId { get; init; } = string.Empty;

    [JsonPropertyName("entityType")]
    public string EntityType { get; init; } = string.Empty;

    [JsonPropertyName("localId")]
    public string LocalId { get; init; } = string.Empty;

    [JsonPropertyName("localVersionNo")]
    public int LocalVersionNo { get; init; }

    [JsonPropertyName("idempotencyKey")]
    public string IdempotencyKey { get; init; } = string.Empty;

    [JsonPropertyName("localHashSha256")]
    public string? LocalHashSha256 { get; init; }

    [JsonPropertyName("previousServerDocumentId")]
    public string? PreviousServerDocumentId { get; init; }

    [JsonPropertyName("previousServerVersionId")]
    public string? PreviousServerVersionId { get; init; }
}

public sealed record ReconciliationRunCreateRequest
{
    [JsonPropertyName("clientId")]
    public string ClientId { get; init; } = string.Empty;

    [JsonPropertyName("previousServerInstanceId")]
    public string? PreviousServerInstanceId { get; init; }

    [JsonPropertyName("previousServerEpoch")]
    public int? PreviousServerEpoch { get; init; }

    [JsonPropertyName("triggerReason")]
    public string TriggerReason { get; init; } = string.Empty;

    [JsonPropertyName("clientCursor")]
    public long ClientCursor { get; init; }

    [JsonPropertyName("items")]
    public IReadOnlyList<ReconciliationInventoryItemRequest> Items { get; init; } = [];
}

public sealed record ServerReconciliationItem
{
    [JsonPropertyName("item_id")]
    public string ItemId { get; init; } = string.Empty;

    [JsonPropertyName("client_item_id")]
    public string ClientItemId { get; init; } = string.Empty;

    [JsonPropertyName("entity_type")]
    public string EntityType { get; init; } = string.Empty;

    [JsonPropertyName("local_id")]
    public string LocalId { get; init; } = string.Empty;

    [JsonPropertyName("local_version_no")]
    public int LocalVersionNo { get; init; }

    [JsonPropertyName("idempotency_key")]
    public string IdempotencyKey { get; init; } = string.Empty;

    [JsonPropertyName("local_hash_sha256")]
    public string? LocalHashSha256 { get; init; }

    [JsonPropertyName("verdict")]
    public string Verdict { get; init; } = string.Empty;

    [JsonPropertyName("proposed_action")]
    public string ProposedAction { get; init; } = string.Empty;

    [JsonPropertyName("server_document_id")]
    public string? ServerDocumentId { get; init; }

    [JsonPropertyName("server_version_id")]
    public string? ServerVersionId { get; init; }

    [JsonPropertyName("server_revision")]
    public int? ServerRevision { get; init; }

    [JsonPropertyName("server_hash_sha256")]
    public string? ServerHashSha256 { get; init; }

    [JsonPropertyName("details")]
    public string? Details { get; init; }

    [JsonPropertyName("resolution_status")]
    public string? ResolutionStatus { get; init; }
}

public sealed record ServerReconciliationRun
{
    [JsonPropertyName("run_id")]
    public string RunId { get; init; } = string.Empty;

    [JsonPropertyName("server_instance_id")]
    public string ServerInstanceId { get; init; } = string.Empty;

    [JsonPropertyName("server_epoch")]
    public int ServerEpoch { get; init; }

    [JsonPropertyName("trigger_reason")]
    public string TriggerReason { get; init; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("client_cursor")]
    public long ClientCursor { get; init; }

    [JsonPropertyName("server_cursor")]
    public long ServerCursor { get; init; }

    [JsonPropertyName("items")]
    public IReadOnlyList<ServerReconciliationItem> Items { get; init; } = [];
}

public sealed record ReconciliationResolutionRequest
{
    [JsonPropertyName("itemId")]
    public string ItemId { get; init; } = string.Empty;

    [JsonPropertyName("action")]
    public string Action { get; init; } = string.Empty;

    [JsonPropertyName("reason")]
    public string Reason { get; init; } = string.Empty;
}

public sealed record ReconciliationApplyRequest
{
    [JsonPropertyName("approvalReason")]
    public string ApprovalReason { get; init; } = string.Empty;

    [JsonPropertyName("resolutions")]
    public IReadOnlyList<ReconciliationResolutionRequest> Resolutions { get; init; } = [];
}

public sealed record ServerBindingRecord(
    string ServerScope,
    string ServerInstanceId,
    int ServerEpoch,
    string Status,
    string? ObservedServerInstanceId,
    int? ObservedServerEpoch,
    string? BlockReason,
    string? RestorePilotRunId,
    string? RestoreBackupSetId,
    string? RestoreApprovalId,
    string? RestoreResponsibleOwner,
    string? RestoreFaultCode,
    string ConvergenceStatus)
{
    public bool ReconciliationRequired => Status == ServerEpochGuardService.ReconciliationRequiredStatus;
    public bool TrafficBlocked =>
        ReconciliationRequired ||
        ConvergenceStatus == "POST_APPROVAL_RESTART_REQUIRED";
}

public sealed record LocalReconciliationItem(
    string ItemId,
    string RunId,
    string EntityType,
    string LocalId,
    int LocalVersionNo,
    string Verdict,
    string ProposedAction,
    string? ServerDocumentId,
    string? ServerVersionId,
    int? ServerRevision,
    string? LocalHashSha256,
    string? ServerHashSha256,
    string? Details,
    string? ResolutionAction,
    string? ResolutionStatus);
