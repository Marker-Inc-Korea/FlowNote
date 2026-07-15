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
}

public sealed class ServerAIRetentionResult
{
    [JsonPropertyName("processed")] public int Processed { get; set; }
    [JsonPropertyName("queryPayloadsDeidentified")] public int QueryPayloadsDeidentified { get; set; }
    [JsonPropertyName("responsesDeleted")] public int ResponsesDeleted { get; set; }
}
