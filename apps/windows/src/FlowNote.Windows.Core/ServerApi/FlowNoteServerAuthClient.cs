using System.Net.Http.Json;

namespace FlowNote.Windows.Core.ServerApi;

public sealed class FlowNoteServerAuthClient
{
    private readonly HttpClient httpClient;

    public FlowNoteServerAuthClient(HttpClient httpClient)
    {
        this.httpClient = httpClient;
    }

    public async Task<ServerLoginResponse?> TryLoginAsync(
        string username,
        string password,
        CancellationToken cancellationToken = default)
    {
        var request = new ServerLoginRequest(username, password);
        using var response = await httpClient.PostAsJsonAsync("api/v1/auth/login", request, cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            return null;
        }

        return await response.Content.ReadFromJsonAsync<ServerLoginResponse>(cancellationToken);
    }
}
