using System.Net;
using System.Net.Http.Json;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.Core.Auth;

public sealed class ServerAwareAuthService(AuthService localAuth, HttpClient? serverHttpClient)
{
    public async Task<LoginResult> LoginAsync(
        string loginId,
        string password,
        CancellationToken cancellationToken = default)
    {
        var serverResult = await TryServerLoginAsync(
            serverHttpClient,
            loginId,
            password,
            cancellationToken);
        return serverResult ?? localAuth.Login(loginId, password);
    }

    public static async Task<LoginResult?> TryServerLoginAsync(
        HttpClient? httpClient,
        string loginId,
        string password,
        CancellationToken cancellationToken = default)
    {
        if (httpClient is null)
        {
            return null;
        }

        try
        {
            var response = await httpClient.PostAsJsonAsync(
                "api/v1/auth/login",
                new ServerLoginRequest(loginId, password),
                cancellationToken);
            if (response.IsSuccessStatusCode)
            {
                var payload = await response.Content.ReadFromJsonAsync<ServerLoginResponse>(
                    cancellationToken);
                return payload?.ToLoginResult();
            }

            if (response.StatusCode == HttpStatusCode.Unauthorized)
            {
                var body = await response.Content.ReadAsStringAsync(cancellationToken);
                return LoginResult.Failed(ServerAccessDenialPolicy.Message(response.StatusCode, body));
            }

            if (response.StatusCode == HttpStatusCode.Forbidden)
            {
                var body = await response.Content.ReadAsStringAsync(cancellationToken);
                return LoginResult.Failed(ServerAccessDenialPolicy.Message(response.StatusCode, body));
            }

            if (response.StatusCode == HttpStatusCode.NotFound)
            {
                var body = await response.Content.ReadAsStringAsync(cancellationToken);
                return LoginResult.Failed(ServerAccessDenialPolicy.Message(response.StatusCode, body));
            }

            return LoginResult.Failed("서버 로그인에 실패했습니다. 서버 상태를 확인한 뒤 다시 시도하세요.");
        }
        catch (HttpRequestException)
        {
            return null;
        }
        catch (TaskCanceledException)
        {
            return null;
        }
    }
}
