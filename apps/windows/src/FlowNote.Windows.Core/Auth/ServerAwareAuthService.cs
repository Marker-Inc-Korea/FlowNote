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
                return LoginResult.Failed("서버 로그인 ID 또는 비밀번호가 올바르지 않습니다.");
            }

            if (response.StatusCode == HttpStatusCode.Forbidden)
            {
                return LoginResult.Failed("서버 계정이 비활성 상태입니다. 관리자에게 문의하세요.");
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
