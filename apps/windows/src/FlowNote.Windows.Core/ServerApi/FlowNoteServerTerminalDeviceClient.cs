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
            if (response.StatusCode is HttpStatusCode.Unauthorized
                or HttpStatusCode.Forbidden
                or HttpStatusCode.NotFound)
            {
                throw ServerAccessDenialPolicy.CreateException(response.StatusCode, errorBody);
            }

            throw new InvalidOperationException(
                "승인 단말 요청을 처리하지 못했습니다. 잠시 후 다시 시도하세요.");
        }

        var result = await response.Content.ReadFromJsonAsync<T>(cancellationToken);
        return result ?? throw new InvalidOperationException("승인 단말 API가 빈 응답을 반환했습니다.");
    }
}
