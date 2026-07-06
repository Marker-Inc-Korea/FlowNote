namespace FlowNote.Windows.Core.ServerApi;

public static class FlowNoteServerApiEnvironment
{
    public const string ApiBaseUrlEnvironmentVariable = "FLOWNOTE_API_BASE_URL";
    public const string LocalLoopbackApiBaseUrl = "http://127.0.0.1:5184";

    public static HttpClient? CreateHttpClientFromEnvironment(TimeSpan? timeout = null)
    {
        var apiBaseUrl = Environment.GetEnvironmentVariable(ApiBaseUrlEnvironmentVariable);
        return CreateHttpClient(apiBaseUrl, timeout);
    }

    public static HttpClient? CreateHttpClient(string? apiBaseUrl, TimeSpan? timeout = null)
    {
        if (string.IsNullOrWhiteSpace(apiBaseUrl))
        {
            return null;
        }

        var normalizedBaseUrl = apiBaseUrl.EndsWith('/') ? apiBaseUrl : $"{apiBaseUrl}/";
        if (!Uri.TryCreate(normalizedBaseUrl, UriKind.Absolute, out var baseAddress))
        {
            return null;
        }

        return new HttpClient
        {
            BaseAddress = baseAddress,
            Timeout = timeout ?? TimeSpan.FromSeconds(10)
        };
    }
}
