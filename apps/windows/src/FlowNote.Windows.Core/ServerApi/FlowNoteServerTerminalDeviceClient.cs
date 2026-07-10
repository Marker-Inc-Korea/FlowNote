using System.Net;
using System.Net.Http.Json;

namespace FlowNote.Windows.Core.ServerApi;

public sealed class FlowNoteServerTerminalDeviceClient(HttpClient httpClient)
{
    public async Task<IReadOnlyList<ServerTerminalDeviceResponse>> ListAsync(
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync("api/v1/terminal-devices", cancellationToken);
        return await ReadJsonResponse<List<ServerTerminalDeviceResponse>>(response, cancellationToken);
    }

    public async Task<ServerTerminalDeviceResponse> CreateAsync(
        ServerTerminalDeviceCreateRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            "api/v1/terminal-devices",
            request,
            cancellationToken);
        return await ReadJsonResponse<ServerTerminalDeviceResponse>(response, cancellationToken);
    }

    public async Task<ServerTerminalDeviceResponse> UpdateAsync(
        string deviceId,
        ServerTerminalDeviceUpdateRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PatchAsJsonAsync(
            $"api/v1/terminal-devices/{Uri.EscapeDataString(deviceId)}",
            request,
            cancellationToken);
        return await ReadJsonResponse<ServerTerminalDeviceResponse>(response, cancellationToken);
    }

    public async Task<ServerTerminalDeviceResponse> ChangeStatusAsync(
        string deviceId,
        ServerTerminalDeviceStatusRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PatchAsJsonAsync(
            $"api/v1/terminal-devices/{Uri.EscapeDataString(deviceId)}/status",
            request,
            cancellationToken);
        return await ReadJsonResponse<ServerTerminalDeviceResponse>(response, cancellationToken);
    }

    public async Task<ServerTerminalDeviceResponse> ReplaceAsync(
        string previousDeviceId,
        ServerTerminalDeviceReplaceRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            $"api/v1/terminal-devices/{Uri.EscapeDataString(previousDeviceId)}/replace",
            request,
            cancellationToken);
        return await ReadJsonResponse<ServerTerminalDeviceResponse>(response, cancellationToken);
    }

    private static async Task<T> ReadJsonResponse<T>(
        HttpResponseMessage response,
        CancellationToken cancellationToken)
    {
        if (!response.IsSuccessStatusCode)
        {
            var errorBody = await response.Content.ReadAsStringAsync(cancellationToken);
            if (response.StatusCode == HttpStatusCode.Unauthorized)
            {
                throw new FlowNoteServerAuthenticationException(
                    $"서버 로그인이 만료되었습니다. 다시 로그인하세요. {errorBody}");
            }

            if (response.StatusCode == HttpStatusCode.Forbidden)
            {
                throw new InvalidOperationException(
                    $"승인 단말 관리는 관리자 또는 시스템 관리자만 사용할 수 있습니다. {errorBody}");
            }

            throw new InvalidOperationException(
                $"승인 단말 API 요청 실패: {(int)response.StatusCode} {response.ReasonPhrase}. {errorBody}");
        }

        var result = await response.Content.ReadFromJsonAsync<T>(cancellationToken);
        return result ?? throw new InvalidOperationException("승인 단말 API가 빈 응답을 반환했습니다.");
    }
}
