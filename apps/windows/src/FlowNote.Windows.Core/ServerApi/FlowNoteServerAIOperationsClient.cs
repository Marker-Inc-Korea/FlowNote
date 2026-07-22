using System.Net;
using System.Net.Http.Json;

namespace FlowNote.Windows.Core.ServerApi;

public sealed class FlowNoteServerAIOperationsClient(HttpClient httpClient)
{
    public Task<List<ServerAIApprovalResponse>> ListApprovalsAsync(CancellationToken ct = default) =>
        GetAsync<List<ServerAIApprovalResponse>>("api/v1/ai-operations/approvals", ct);

    public Task<ServerAIApprovalResponse> CreateApprovalAsync(ServerAIApprovalCreateRequest value, CancellationToken ct = default) =>
        SendAsync<ServerAIApprovalResponse>(HttpMethod.Post, "api/v1/ai-operations/approvals", value, ct);

    public Task<ServerAIApprovalResponse> RevokeApprovalAsync(string id, string reason, CancellationToken ct = default) =>
        SendAsync<ServerAIApprovalResponse>(HttpMethod.Post, $"api/v1/ai-operations/approvals/{Uri.EscapeDataString(id)}/revoke", new { reason }, ct);

    public Task<List<ServerAIPromptResponse>> ListPromptsAsync(CancellationToken ct = default) =>
        GetAsync<List<ServerAIPromptResponse>>("api/v1/ai-operations/prompts", ct);

    public Task<ServerAIPromptResponse> CreatePromptAsync(ServerAIPromptCreateRequest value, CancellationToken ct = default) =>
        SendAsync<ServerAIPromptResponse>(HttpMethod.Post, "api/v1/ai-operations/prompts", value, ct);

    public Task<ServerAIPromptResponse> ChangePromptAsync(string id, string action, string reason, CancellationToken ct = default) =>
        SendAsync<ServerAIPromptResponse>(HttpMethod.Post, $"api/v1/ai-operations/prompts/{Uri.EscapeDataString(id)}/{action}", new { reason }, ct);

    public Task<List<ServerAIPolicyResponse>> ListPoliciesAsync(CancellationToken ct = default) =>
        GetAsync<List<ServerAIPolicyResponse>>("api/v1/ai-operations/policies", ct);

    public Task<ServerAIPolicyResponse> SavePolicyAsync(ServerAIPolicyUpdateRequest value, CancellationToken ct = default) =>
        SendAsync<ServerAIPolicyResponse>(HttpMethod.Put, "api/v1/ai-operations/policies", value, ct);

    public Task<List<ServerAIQueryAuditResponse>> ListQueryAuditAsync(CancellationToken ct = default) =>
        GetAsync<List<ServerAIQueryAuditResponse>>("api/v1/ai-operations/audit/queries?limit=500", ct);

    public Task<ServerAIRetentionResult> RunRetentionAsync(CancellationToken ct = default) =>
        SendAsync<ServerAIRetentionResult>(HttpMethod.Post, "api/v1/ai-operations/retention/run", new { }, ct);

    public Task<ServerAIQueryDetailResponse> GetQueryDetailAsync(string queryId, CancellationToken ct = default) =>
        GetAsync<ServerAIQueryDetailResponse>($"api/v1/ai-operations/queries/{Uri.EscapeDataString(queryId)}", ct);

    public Task<ServerAIQueryDetailResponse> ExpireQueryAndReadBackAsync(
        string queryId, ServerAIQueryMutationRequest value, CancellationToken ct = default) =>
        MutateAndReadBackAsync(
            $"api/v1/ai-operations/queries/{Uri.EscapeDataString(queryId)}/expire", queryId, value, ct);

    public Task<ServerAIQueryDetailResponse> PlaceLegalHoldAndReadBackAsync(
        string queryId, ServerAILegalHoldCreateRequest value, CancellationToken ct = default) =>
        MutateAndReadBackAsync(
            $"api/v1/ai-operations/queries/{Uri.EscapeDataString(queryId)}/legal-holds", queryId, value, ct);

    public Task<ServerAIQueryDetailResponse> ReleaseLegalHoldAndReadBackAsync(
        string queryId, string holdId, ServerAIQueryMutationRequest value, CancellationToken ct = default) =>
        MutateAndReadBackAsync(
            $"api/v1/ai-operations/legal-holds/{Uri.EscapeDataString(holdId)}/release", queryId, value, ct);

    private async Task<ServerAIQueryDetailResponse> MutateAndReadBackAsync(
        string path, string queryId, object value, CancellationToken ct)
    {
        await AIOperationMutationPolicy.RunWithResponseLossRetryAsync(async () =>
        {
            using var request = new HttpRequestMessage(HttpMethod.Post, path) { Content = JsonContent.Create(value) };
            using var response = await httpClient.SendAsync(request, ct);
            await EnsureSuccess(response, ct);
            return true;
        }, ct);
        return await GetQueryDetailAsync(queryId, ct);
    }

    public async Task<byte[]> ExportAuditAsync(CancellationToken ct = default)
    {
        using var response = await httpClient.GetAsync("api/v1/ai-operations/audit/export", ct);
        await EnsureSuccess(response, ct);
        return await response.Content.ReadAsByteArrayAsync(ct);
    }

    private async Task<T> GetAsync<T>(string path, CancellationToken ct)
    {
        using var response = await httpClient.GetAsync(path, ct);
        return await Read<T>(response, ct);
    }

    private async Task<T> SendAsync<T>(HttpMethod method, string path, object value, CancellationToken ct)
    {
        using var request = new HttpRequestMessage(method, path) { Content = JsonContent.Create(value) };
        using var response = await httpClient.SendAsync(request, ct);
        return await Read<T>(response, ct);
    }

    private static async Task<T> Read<T>(HttpResponseMessage response, CancellationToken ct)
    {
        await EnsureSuccess(response, ct);
        return await response.Content.ReadFromJsonAsync<T>(cancellationToken: ct)
            ?? throw new InvalidOperationException("외부 AI 운영 API가 빈 응답을 반환했습니다.");
    }

    private static async Task EnsureSuccess(HttpResponseMessage response, CancellationToken ct)
    {
        if (response.IsSuccessStatusCode) return;
        var body = await response.Content.ReadAsStringAsync(ct);
        if (response.StatusCode == HttpStatusCode.Unauthorized)
            throw new FlowNoteServerAuthenticationException("서버 로그인이 만료되었습니다. 다시 로그인하세요.");
        if (response.StatusCode == HttpStatusCode.Forbidden)
            throw new InvalidOperationException($"외부 AI 운영은 시스템 관리자만 사용할 수 있습니다. {body}");
        if (response.StatusCode == HttpStatusCode.Conflict)
            throw new InvalidOperationException($"다른 관리자 작업 또는 현재 상태와 충돌했습니다. 상세를 새로고침하세요. {body}");
        throw new InvalidOperationException($"외부 AI 운영 API 요청 실패: {(int)response.StatusCode}. {body}");
    }
}

public static class AIOperationMutationPolicy
{
    public static async Task<T> RunWithResponseLossRetryAsync<T>(
        Func<Task<T>> operation, CancellationToken cancellationToken = default)
    {
        try
        {
            return await operation();
        }
        catch (HttpRequestException)
        {
            return await operation();
        }
        catch (TaskCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            return await operation();
        }
    }

    public static string NewOperationKey(string action, string queryId) =>
        $"wpf:ai:{action}:{queryId}:{Guid.NewGuid():N}";
}
