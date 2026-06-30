namespace FlowNote.Windows.Core.Auth;

public sealed record LoginResult(
    bool Success,
    string? UserId,
    string? LoginId,
    string? DisplayName,
    string? Role,
    string? FailureReason,
    string? AccessToken = null,
    DateTimeOffset? AccessTokenExpiresAt = null,
    string? RefreshToken = null,
    DateTimeOffset? RefreshTokenExpiresAt = null)
{
    public static LoginResult Failed(string reason)
    {
        return new LoginResult(false, null, null, null, null, reason);
    }
}
