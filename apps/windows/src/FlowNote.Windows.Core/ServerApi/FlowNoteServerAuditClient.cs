using System.Net;
using System.Net.Http.Json;

namespace FlowNote.Windows.Core.ServerApi;

public sealed class FlowNoteServerAuditClient
{
    private readonly HttpClient httpClient;

    public FlowNoteServerAuditClient(HttpClient httpClient)
    {
        this.httpClient = httpClient;
    }

    public async Task<ServerChangeHistoryPage> ListChangeHistoryAsync(
        ServerChangeHistoryQuery query,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync(BuildListPath(query), cancellationToken);
        return await ReadAsync<ServerChangeHistoryPage>(response, cancellationToken);
    }

    public async Task<ServerChangeHistoryDetail> GetChangeHistoryDetailAsync(
        string eventId,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync(
            $"api/v1/change-history/{Uri.EscapeDataString(eventId)}",
            cancellationToken);
        return await ReadAsync<ServerChangeHistoryDetail>(response, cancellationToken);
    }

    public async Task<ServerOperationalReadinessPage> ListOperationalReadinessAsync(
        ServerOperationalReadinessQuery query,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync(
            BuildReadinessPath(query), cancellationToken);
        return await ReadAsync<ServerOperationalReadinessPage>(response, cancellationToken);
    }

    public async Task<ServerOperationalReadinessDetail> GetOperationalReadinessDetailAsync(
        string itemId,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync(
            $"api/v1/operational-readiness/{Uri.EscapeDataString(itemId)}",
            cancellationToken);
        return await ReadAsync<ServerOperationalReadinessDetail>(response, cancellationToken);
    }

    private static string BuildListPath(ServerChangeHistoryQuery query)
    {
        var values = new List<KeyValuePair<string, string>>();
        Add(values, "occurredFrom", query.OccurredFrom?.ToUniversalTime().ToString("O"));
        Add(values, "occurredTo", query.OccurredTo?.ToUniversalTime().ToString("O"));
        Add(values, "actorId", query.ActorId);
        Add(values, "actorRole", query.ActorRole);
        Add(values, "deviceId", query.DeviceId);
        Add(values, "targetType", query.TargetType);
        Add(values, "targetId", query.TargetId);
        Add(values, "targetQuery", query.TargetQuery);
        Add(values, "targetVersionId", query.TargetVersionId);
        Add(values, "targetRevision", query.TargetRevision?.ToString());
        Add(values, "result", query.Result);
        Add(values, "riskLevel", query.RiskLevel);
        Add(values, "runId", query.RunId);
        Add(values, "correlationId", query.CorrelationId);
        Add(values, "actionRequired", query.ActionRequired?.ToString().ToLowerInvariant());
        Add(values, "limit", Math.Clamp(query.Limit, 1, 200).ToString());
        Add(values, "cursor", query.Cursor);
        var encoded = string.Join("&", values.Select(pair =>
            $"{Uri.EscapeDataString(pair.Key)}={Uri.EscapeDataString(pair.Value)}"));
        return $"api/v1/change-history?{encoded}";
    }

    private static string BuildReadinessPath(ServerOperationalReadinessQuery query)
    {
        var values = new List<KeyValuePair<string, string>>();
        Add(values, "areaCode", query.AreaCode);
        Add(values, "severity", query.Severity);
        Add(values, "blockerCode", query.BlockerCode);
        Add(values, "targetQuery", query.TargetQuery);
        Add(values, "limit", Math.Clamp(query.Limit, 1, 200).ToString());
        Add(values, "cursor", query.Cursor);
        var encoded = string.Join("&", values.Select(pair =>
            $"{Uri.EscapeDataString(pair.Key)}={Uri.EscapeDataString(pair.Value)}"));
        return $"api/v1/operational-readiness?{encoded}";
    }

    private static void Add(
        ICollection<KeyValuePair<string, string>> values,
        string key,
        string? value)
    {
        if (!string.IsNullOrWhiteSpace(value))
        {
            values.Add(new KeyValuePair<string, string>(key, value.Trim()));
        }
    }

    private static async Task<T> ReadAsync<T>(
        HttpResponseMessage response,
        CancellationToken cancellationToken)
    {
        if (!response.IsSuccessStatusCode)
        {
            var body = await response.Content.ReadAsStringAsync(cancellationToken);
            if (response.StatusCode is HttpStatusCode.Unauthorized
                or HttpStatusCode.Forbidden
                or HttpStatusCode.NotFound)
            {
                throw ServerAccessDenialPolicy.CreateException(response.StatusCode, body);
            }
            throw new InvalidOperationException(
                "서버 읽기 화면을 조회하지 못했습니다. 서버 연결과 필터 값을 확인한 뒤 다시 시도하세요.");
        }
        return await response.Content.ReadFromJsonAsync<T>(cancellationToken)
            ?? throw new InvalidOperationException("변경 이력 서버 응답이 비어 있습니다.");
    }
}
