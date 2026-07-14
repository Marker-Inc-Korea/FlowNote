using System.Text.Json.Serialization;

namespace FlowNote.Windows.Core.ServerApi;

public sealed record ServerAccountCreateRequest(
    [property: JsonPropertyName("username")] string Username,
    [property: JsonPropertyName("display_name")] string DisplayName,
    [property: JsonPropertyName("role")] string Role,
    [property: JsonPropertyName("temporary_password")] string TemporaryPassword,
    [property: JsonPropertyName("reason")] string Reason);

public sealed record ServerAccountUpdateRequest(
    [property: JsonPropertyName("display_name")] string DisplayName,
    [property: JsonPropertyName("role")] string Role,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("reason")] string Reason);

public sealed record ServerPasswordResetRequest(
    [property: JsonPropertyName("temporary_password")] string TemporaryPassword,
    [property: JsonPropertyName("reason")] string Reason);

public sealed record ServerSessionRevokeRequest(
    [property: JsonPropertyName("reason")] string Reason);

public sealed record ServerAccountRecord
{
    [JsonPropertyName("user_id")]
    public string UserId { get; init; } = string.Empty;

    [JsonPropertyName("username")]
    public string Username { get; init; } = string.Empty;

    [JsonPropertyName("display_name")]
    public string DisplayName { get; init; } = string.Empty;

    [JsonPropertyName("role")]
    public string Role { get; init; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("is_active")]
    public bool IsActive { get; init; }

    [JsonPropertyName("must_change_password")]
    public bool MustChangePassword { get; init; }

    public string RoleLabel => Auth.RolePermissionPolicy.FormatUserRole(Role);

    public string StatusLabel => ServerAccountUiPolicy.FormatStatus(Status, MustChangePassword);
}

public sealed record ServerAccountMutationResponse(
    [property: JsonPropertyName("account")] ServerAccountRecord Account,
    [property: JsonPropertyName("sessions_revoked")] int SessionsRevoked);

public sealed record ServerAccountSessionRecord
{
    [JsonPropertyName("session_id")]
    public string SessionId { get; init; } = string.Empty;

    [JsonPropertyName("device_id")]
    public string? DeviceId { get; init; }

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("last_used_at")]
    public DateTimeOffset? LastUsedAt { get; init; }

    [JsonPropertyName("created_at")]
    public DateTimeOffset CreatedAt { get; init; }
}

public sealed record ServerSessionsRevokedResponse(
    [property: JsonPropertyName("sessions_revoked")] int SessionsRevoked);
