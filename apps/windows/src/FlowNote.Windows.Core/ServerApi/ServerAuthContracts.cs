using System.Text.Json.Serialization;
using FlowNote.Windows.Core.Auth;

namespace FlowNote.Windows.Core.ServerApi;

public sealed record ServerLoginRequest(
    [property: JsonPropertyName("username")] string Username,
    [property: JsonPropertyName("password")] string Password);

public sealed record ServerRefreshRequest(
    [property: JsonPropertyName("refresh_token")] string RefreshToken);

public sealed record ServerLoginResponse
{
    [JsonPropertyName("user_id")]
    public string UserId { get; init; } = string.Empty;

    [JsonPropertyName("username")]
    public string Username { get; init; } = string.Empty;

    [JsonPropertyName("role")]
    public string Role { get; init; } = string.Empty;

    [JsonPropertyName("display_name")]
    public string DisplayName { get; init; } = string.Empty;

    [JsonPropertyName("access_token")]
    public string AccessToken { get; init; } = string.Empty;

    [JsonPropertyName("token_type")]
    public string TokenType { get; init; } = string.Empty;

    [JsonPropertyName("expires_at")]
    public DateTimeOffset ExpiresAt { get; init; }

    [JsonPropertyName("refresh_token")]
    public string RefreshToken { get; init; } = string.Empty;

    [JsonPropertyName("refresh_expires_at")]
    public DateTimeOffset RefreshExpiresAt { get; init; }

    public LoginResult ToLoginResult()
    {
        return new LoginResult(
            true,
            UserId,
            Username,
            DisplayName,
            Role,
            null,
            AccessToken,
            ExpiresAt,
            RefreshToken,
            RefreshExpiresAt);
    }
}

public sealed record ServerCurrentUserResponse
{
    [JsonPropertyName("user_id")]
    public string UserId { get; init; } = string.Empty;

    [JsonPropertyName("username")]
    public string Username { get; init; } = string.Empty;

    [JsonPropertyName("role")]
    public string Role { get; init; } = string.Empty;

    [JsonPropertyName("display_name")]
    public string DisplayName { get; init; } = string.Empty;
}
