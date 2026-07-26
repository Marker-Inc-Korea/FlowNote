using System.Net;
using System.Net.Http.Json;

namespace FlowNote.Windows.Core.ServerApi;

public sealed class FlowNoteServerAccountClient(HttpClient httpClient)
{
    public async Task<IReadOnlyList<ServerAccountRecord>> ListAsync(CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync("api/v1/server-accounts", cancellationToken);
        await EnsureSuccessAsync(response, cancellationToken);
        return await response.Content.ReadFromJsonAsync<List<ServerAccountRecord>>(cancellationToken) ?? [];
    }

    public async Task<ServerAccountMutationResponse> CreateAsync(
        ServerAccountCreateRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync("api/v1/server-accounts", request, cancellationToken);
        await EnsureSuccessAsync(response, cancellationToken);
        return (await response.Content.ReadFromJsonAsync<ServerAccountMutationResponse>(cancellationToken))!;
    }

    public async Task<ServerAccountMutationResponse> UpdateAsync(
        string userId,
        ServerAccountUpdateRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PatchAsJsonAsync(
            $"api/v1/server-accounts/{Uri.EscapeDataString(userId)}",
            request,
            cancellationToken);
        await EnsureSuccessAsync(response, cancellationToken);
        return (await response.Content.ReadFromJsonAsync<ServerAccountMutationResponse>(cancellationToken))!;
    }

    public async Task<ServerAccountMutationResponse> ResetPasswordAsync(
        string userId,
        ServerPasswordResetRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            $"api/v1/server-accounts/{Uri.EscapeDataString(userId)}/password-reset",
            request,
            cancellationToken);
        await EnsureSuccessAsync(response, cancellationToken);
        return (await response.Content.ReadFromJsonAsync<ServerAccountMutationResponse>(cancellationToken))!;
    }

    public async Task<IReadOnlyList<ServerAccountSessionRecord>> ListSessionsAsync(
        string userId,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync(
            $"api/v1/server-accounts/{Uri.EscapeDataString(userId)}/sessions",
            cancellationToken);
        await EnsureSuccessAsync(response, cancellationToken);
        return await response.Content.ReadFromJsonAsync<List<ServerAccountSessionRecord>>(cancellationToken) ?? [];
    }

    public async Task<int> RevokeSessionsAsync(
        string userId,
        string reason,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            $"api/v1/server-accounts/{Uri.EscapeDataString(userId)}/sessions/revoke",
            new ServerSessionRevokeRequest(reason),
            cancellationToken);
        await EnsureSuccessAsync(response, cancellationToken);
        var payload = await response.Content.ReadFromJsonAsync<ServerSessionsRevokedResponse>(cancellationToken);
        return payload?.SessionsRevoked ?? 0;
    }

    private static async Task EnsureSuccessAsync(HttpResponseMessage response, CancellationToken cancellationToken)
    {
        if (response.IsSuccessStatusCode)
        {
            return;
        }

        var responseBody = await response.Content.ReadAsStringAsync(cancellationToken);
        throw new ServerAccountApiException(response.StatusCode, responseBody);
    }
}

public sealed class ServerAccountApiException(HttpStatusCode statusCode, string responseBody)
    : InvalidOperationException(ServerAccessDenialPolicy.Message(statusCode, responseBody))
{
    public HttpStatusCode StatusCode { get; } = statusCode;

    public string ErrorCode { get; } = ServerAccessDenialPolicy.ErrorCode(responseBody);
}
