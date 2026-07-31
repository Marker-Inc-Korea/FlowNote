using System.Text.Json.Serialization;

namespace FlowNote.Windows.Core.ServerApi;

public sealed class ServerAIApprovalResponse
{
    [JsonPropertyName("approvalId")] public string ApprovalId { get; set; } = string.Empty;
    [JsonPropertyName("customerScope")] public string CustomerScope { get; set; } = string.Empty;
    [JsonPropertyName("siteScope")] public string SiteScope { get; set; } = string.Empty;
    [JsonPropertyName("provider")] public string Provider { get; set; } = string.Empty;
    [JsonPropertyName("modelScope")] public string ModelScope { get; set; } = string.Empty;
    [JsonPropertyName("purposes")] public List<string> Purposes { get; set; } = [];
    [JsonPropertyName("sourceTypes")] public List<string> SourceTypes { get; set; } = [];
    [JsonPropertyName("status")] public string Status { get; set; } = string.Empty;
    [JsonPropertyName("expiresAt")] public DateTimeOffset ExpiresAt { get; set; }
    [JsonPropertyName("reason")] public string Reason { get; set; } = string.Empty;
}

public sealed class ServerAIApprovalCreateRequest
{
    [JsonPropertyName("customerScope")] public string CustomerScope { get; set; } = string.Empty;
    [JsonPropertyName("siteScope")] public string SiteScope { get; set; } = string.Empty;
    [JsonPropertyName("provider")] public string Provider { get; set; } = string.Empty;
    [JsonPropertyName("modelScope")] public string ModelScope { get; set; } = string.Empty;
    [JsonPropertyName("purposes")] public List<string> Purposes { get; set; } = [];
    [JsonPropertyName("sourceTypes")] public List<string> SourceTypes { get; set; } = [];
    [JsonPropertyName("dataHandlingPolicyVersion")] public string DataHandlingPolicyVersion { get; set; } = string.Empty;
    [JsonPropertyName("expiresAt")] public DateTimeOffset ExpiresAt { get; set; }
    [JsonPropertyName("reason")] public string Reason { get; set; } = string.Empty;
}

public sealed class ServerAIPromptResponse
{
    [JsonPropertyName("promptVersionId")] public string PromptVersionId { get; set; } = string.Empty;
    [JsonPropertyName("name")] public string Name { get; set; } = string.Empty;
    [JsonPropertyName("version")] public string Version { get; set; } = string.Empty;
    [JsonPropertyName("templateHash")] public string TemplateHash { get; set; } = string.Empty;
    [JsonPropertyName("templateText")] public string TemplateText { get; set; } = string.Empty;
    [JsonPropertyName("allowedPurpose")] public string AllowedPurpose { get; set; } = string.Empty;
    [JsonPropertyName("status")] public string Status { get; set; } = string.Empty;
}

public sealed class ServerAIPromptCreateRequest
{
    [JsonPropertyName("name")] public string Name { get; set; } = string.Empty;
    [JsonPropertyName("version")] public string Version { get; set; } = string.Empty;
    [JsonPropertyName("templateText")] public string TemplateText { get; set; } = string.Empty;
    [JsonPropertyName("allowedPurpose")] public string AllowedPurpose { get; set; } = string.Empty;
}

public sealed class ServerAIPolicyResponse
{
    [JsonPropertyName("policyId")] public string PolicyId { get; set; } = string.Empty;
    [JsonPropertyName("scopeType")] public string ScopeType { get; set; } = string.Empty;
    [JsonPropertyName("customerScope")] public string CustomerScope { get; set; } = string.Empty;
    [JsonPropertyName("siteScope")] public string SiteScope { get; set; } = string.Empty;
    [JsonPropertyName("killSwitchEnabled")] public bool KillSwitchEnabled { get; set; }
    [JsonPropertyName("maxRequestsPerDay")] public int MaxRequestsPerDay { get; set; }
    [JsonPropertyName("maxConcurrency")] public int MaxConcurrency { get; set; }
    [JsonPropertyName("timeoutSeconds")] public int TimeoutSeconds { get; set; }
    [JsonPropertyName("dailyCostBudgetMicros")] public long DailyCostBudgetMicros { get; set; }
    [JsonPropertyName("queryPayloadRetentionDays")] public int QueryPayloadRetentionDays { get; set; }
    [JsonPropertyName("responseRetentionDays")] public int ResponseRetentionDays { get; set; }
    [JsonPropertyName("auditRetentionDays")] public int AuditRetentionDays { get; set; }
    [JsonPropertyName("allowAuditExport")] public bool AllowAuditExport { get; set; }
    [JsonPropertyName("providerCredentialConfigured")] public bool ProviderCredentialConfigured { get; set; }
    [JsonPropertyName("reason")] public string Reason { get; set; } = string.Empty;
}

public sealed class ServerAIPolicyUpdateRequest
{
    [JsonPropertyName("scopeType")] public string ScopeType { get; set; } = "SITE";
    [JsonPropertyName("killSwitchEnabled")] public bool KillSwitchEnabled { get; set; } = true;
    [JsonPropertyName("maxRequestsPerDay")] public int MaxRequestsPerDay { get; set; }
    [JsonPropertyName("maxConcurrency")] public int MaxConcurrency { get; set; }
    [JsonPropertyName("timeoutSeconds")] public int TimeoutSeconds { get; set; } = 30;
    [JsonPropertyName("dailyCostBudgetMicros")] public long DailyCostBudgetMicros { get; set; }
    [JsonPropertyName("queryPayloadRetentionDays")] public int QueryPayloadRetentionDays { get; set; } = 90;
    [JsonPropertyName("responseRetentionDays")] public int ResponseRetentionDays { get; set; } = 90;
    [JsonPropertyName("auditRetentionDays")] public int AuditRetentionDays { get; set; } = 365;
    [JsonPropertyName("allowAuditExport")] public bool AllowAuditExport { get; set; }
    [JsonPropertyName("reason")] public string Reason { get; set; } = string.Empty;
}

public sealed class ServerAISensitivePolicyResponse
{
    [JsonPropertyName("policyId")] public string PolicyId { get; set; } = string.Empty;
    [JsonPropertyName("scopeType")] public string ScopeType { get; set; } = string.Empty;
    [JsonPropertyName("scopeDisplay")] public string ScopeDisplay { get; set; } = string.Empty;
    [JsonPropertyName("version")] public string Version { get; set; } = string.Empty;
    [JsonPropertyName("status")] public string Status { get; set; } = string.Empty;
    [JsonPropertyName("isActive")] public bool IsActive { get; set; }
    [JsonPropertyName("contentHash")] public string ContentHash { get; set; } = string.Empty;
    [JsonPropertyName("forbiddenTermCount")] public int ForbiddenTermCount { get; set; }
    [JsonPropertyName("customerIdentifierCount")] public int CustomerIdentifierCount { get; set; }
    [JsonPropertyName("createdBy")] public string CreatedBy { get; set; } = string.Empty;
    [JsonPropertyName("reviewedBy")] public string? ReviewedBy { get; set; }
    [JsonPropertyName("approvedBy")] public string? ApprovedBy { get; set; }
    [JsonPropertyName("activatedBy")] public string? ActivatedBy { get; set; }
    [JsonPropertyName("stateTag")] public string StateTag { get; set; } = string.Empty;
    [JsonPropertyName("responsibleOwner")] public string ResponsibleOwner { get; set; } = string.Empty;
    [JsonPropertyName("nextAction")] public string NextAction { get; set; } = string.Empty;
    [JsonPropertyName("rawPolicyExposed")] public bool RawPolicyExposed { get; set; }
}

public sealed class ServerAISensitivePolicyCreateRequest
{
    [JsonPropertyName("version")] public string Version { get; set; } = string.Empty;
    [JsonPropertyName("forbiddenTerms")] public List<string> ForbiddenTerms { get; set; } = [];
    [JsonPropertyName("customerIdentifiers")] public List<string> CustomerIdentifiers { get; set; } = [];
    [JsonPropertyName("reason")] public string Reason { get; set; } = string.Empty;
    [JsonPropertyName("operationKey")] public string OperationKey { get; set; } = string.Empty;
}

public sealed class ServerAISensitivePolicyActionRequest
{
    [JsonPropertyName("reason")] public string Reason { get; set; } = string.Empty;
    [JsonPropertyName("operationKey")] public string OperationKey { get; set; } = string.Empty;
    [JsonPropertyName("expectedStateTag")] public string ExpectedStateTag { get; set; } = string.Empty;
    [JsonPropertyName("confirmAction")] public string ConfirmAction { get; set; } = string.Empty;
    [JsonPropertyName("replacesPolicyId")] public string? ReplacesPolicyId { get; set; }
}

public sealed class ServerAISensitivePolicyRuntimeStatus
{
    [JsonPropertyName("scopeDisplay")] public string ScopeDisplay { get; set; } = string.Empty;
    [JsonPropertyName("activePolicy")] public ServerAISensitivePolicyResponse? ActivePolicy { get; set; }
    [JsonPropertyName("latestPolicy")] public ServerAISensitivePolicyResponse? LatestPolicy { get; set; }
    [JsonPropertyName("blockCategory")] public string BlockCategory { get; set; } = string.Empty;
    [JsonPropertyName("reasonCode")] public string? ReasonCode { get; set; }
    [JsonPropertyName("reason")] public string Reason { get; set; } = string.Empty;
    [JsonPropertyName("responsibleOwner")] public string ResponsibleOwner { get; set; } = string.Empty;
    [JsonPropertyName("nextAction")] public string NextAction { get; set; } = string.Empty;
    [JsonPropertyName("externalTransferOccurred")] public bool ExternalTransferOccurred { get; set; }
    [JsonPropertyName("providerStartReady")] public bool ProviderStartReady { get; set; }
}

public sealed class ServerAIQueryAuditResponse
{
    [JsonPropertyName("queryId")] public string QueryId { get; set; } = string.Empty;
    [JsonPropertyName("requestedBy")] public string RequestedBy { get; set; } = string.Empty;
    [JsonPropertyName("purpose")] public string Purpose { get; set; } = string.Empty;
    [JsonPropertyName("status")] public string Status { get; set; } = string.Empty;
    [JsonPropertyName("blockCode")] public string? BlockCode { get; set; }
    [JsonPropertyName("promptVersionId")] public string? PromptVersionId { get; set; }
    [JsonPropertyName("responseStored")] public bool ResponseStored { get; set; }
    [JsonPropertyName("queryPayloadExpired")] public bool QueryPayloadExpired { get; set; }
    [JsonPropertyName("evidenceCount")] public int EvidenceCount { get; set; }
    [JsonPropertyName("citationCount")] public int CitationCount { get; set; }
    [JsonPropertyName("createdAt")] public DateTimeOffset CreatedAt { get; set; }
    [JsonPropertyName("customerScope")] public string CustomerScope { get; set; } = string.Empty;
    [JsonPropertyName("siteScope")] public string SiteScope { get; set; } = string.Empty;
    [JsonPropertyName("blockCategory")] public string BlockCategory { get; set; } = string.Empty;
    [JsonPropertyName("externalTransferOccurred")] public bool ExternalTransferOccurred { get; set; }
    [JsonPropertyName("operatorReason")] public string OperatorReason { get; set; } = string.Empty;
    [JsonPropertyName("responsibleOwner")] public string ResponsibleOwner { get; set; } = string.Empty;
    [JsonPropertyName("nextAction")] public string NextAction { get; set; } = string.Empty;
}

public sealed class ServerAIRetentionResult
{
    [JsonPropertyName("processed")] public int Processed { get; set; }
    [JsonPropertyName("queryPayloadsDeidentified")] public int QueryPayloadsDeidentified { get; set; }
    [JsonPropertyName("responsesDeleted")] public int ResponsesDeleted { get; set; }
}

public class ServerAIQueryMutationRequest
{
    [JsonPropertyName("reason")] public string Reason { get; set; } = string.Empty;
    [JsonPropertyName("operationKey")] public string OperationKey { get; set; } = string.Empty;
    [JsonPropertyName("expectedStateTag")] public string ExpectedStateTag { get; set; } = string.Empty;
}

public sealed class ServerAILegalHoldCreateRequest : ServerAIQueryMutationRequest
{
    [JsonPropertyName("authorityReference")] public string AuthorityReference { get; set; } = string.Empty;
}

public sealed class ServerAILegalHoldResponse
{
    [JsonPropertyName("holdId")] public string HoldId { get; set; } = string.Empty;
    [JsonPropertyName("queryId")] public string QueryId { get; set; } = string.Empty;
    [JsonPropertyName("status")] public string Status { get; set; } = string.Empty;
    [JsonPropertyName("reason")] public string Reason { get; set; } = string.Empty;
    [JsonPropertyName("authorityReference")] public string AuthorityReference { get; set; } = string.Empty;
    [JsonPropertyName("placedBy")] public string PlacedBy { get; set; } = string.Empty;
    [JsonPropertyName("placedAt")] public DateTimeOffset PlacedAt { get; set; }
    [JsonPropertyName("releasedBy")] public string? ReleasedBy { get; set; }
    [JsonPropertyName("releasedAt")] public DateTimeOffset? ReleasedAt { get; set; }
    [JsonPropertyName("releaseReason")] public string? ReleaseReason { get; set; }
}

public sealed class ServerAIRetentionAuditResponse
{
    [JsonPropertyName("retentionAuditId")] public string RetentionAuditId { get; set; } = string.Empty;
    [JsonPropertyName("queryId")] public string QueryId { get; set; } = string.Empty;
    [JsonPropertyName("action")] public string Action { get; set; } = string.Empty;
    [JsonPropertyName("queryTextAction")] public string QueryTextAction { get; set; } = string.Empty;
    [JsonPropertyName("responseTextAction")] public string ResponseTextAction { get; set; } = string.Empty;
    [JsonPropertyName("processedAt")] public DateTimeOffset ProcessedAt { get; set; }
}

public sealed class ServerAIOperationAuditEventResponse
{
    [JsonPropertyName("eventId")] public string EventId { get; set; } = string.Empty;
    [JsonPropertyName("eventType")] public string EventType { get; set; } = string.Empty;
    [JsonPropertyName("actorId")] public string? ActorId { get; set; }
    [JsonPropertyName("targetType")] public string TargetType { get; set; } = string.Empty;
    [JsonPropertyName("targetId")] public string TargetId { get; set; } = string.Empty;
    [JsonPropertyName("reasonCode")] public string? ReasonCode { get; set; }
    [JsonPropertyName("occurredAt")] public DateTimeOffset OccurredAt { get; set; }
}

public sealed class ServerAIQueryDetailResponse
{
    [JsonPropertyName("queryId")] public string QueryId { get; set; } = string.Empty;
    [JsonPropertyName("requestedBy")] public string RequestedBy { get; set; } = string.Empty;
    [JsonPropertyName("customerScope")] public string CustomerScope { get; set; } = string.Empty;
    [JsonPropertyName("siteScope")] public string SiteScope { get; set; } = string.Empty;
    [JsonPropertyName("purpose")] public string Purpose { get; set; } = string.Empty;
    [JsonPropertyName("status")] public string Status { get; set; } = string.Empty;
    [JsonPropertyName("queryPayloadExpired")] public bool QueryPayloadExpired { get; set; }
    [JsonPropertyName("responseStored")] public bool ResponseStored { get; set; }
    [JsonPropertyName("retentionUntil")] public DateTimeOffset RetentionUntil { get; set; }
    [JsonPropertyName("responseRetentionUntil")] public DateTimeOffset? ResponseRetentionUntil { get; set; }
    [JsonPropertyName("activeHold")] public ServerAILegalHoldResponse? ActiveHold { get; set; }
    [JsonPropertyName("holds")] public List<ServerAILegalHoldResponse> Holds { get; set; } = [];
    [JsonPropertyName("retentionAudits")] public List<ServerAIRetentionAuditResponse> RetentionAudits { get; set; } = [];
    [JsonPropertyName("auditEvents")] public List<ServerAIOperationAuditEventResponse> AuditEvents { get; set; } = [];
    [JsonPropertyName("stateTag")] public string StateTag { get; set; } = string.Empty;
}
