using System.Text.Json.Serialization;
using FlowNote.Windows.Core.Auth;

namespace FlowNote.Windows.Core.ServerApi;

public sealed record ServerLoginRequest(
    [property: JsonPropertyName("username")] string Username,
    [property: JsonPropertyName("password")] string Password);

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

    public LoginResult ToLoginResult()
    {
        return new LoginResult(
            true,
            UserId,
            Username,
            DisplayName,
            Role,
            null);
    }
}
