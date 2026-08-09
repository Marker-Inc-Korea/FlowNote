namespace FlowNote.Windows.Core.ServerApi;

public static class FlowNoteServerApiEnvironment
{
    public const string ApiBaseUrlEnvironmentVariable = "FLOWNOTE_API_BASE_URL";
    public const string DefaultServerExampleUrl = "https://flownote.example";

    public static HttpClient? CreateHttpClientFromEnvironment(TimeSpan? timeout = null)
    {
        var apiBaseUrl = ResolveApiBaseUrlFromEnvironment();
        return CreateHttpClient(apiBaseUrl, timeout);
    }

    public static string ResolveApiBaseUrlFromEnvironment()
    {
        return ResolveApiBaseUrl(
            Environment.GetEnvironmentVariable(ApiBaseUrlEnvironmentVariable));
    }

    public static string ResolveApiBaseUrl(string? configuredApiBaseUrl)
    {
        return string.IsNullOrWhiteSpace(configuredApiBaseUrl)
            ? DefaultServerExampleUrl
            : configuredApiBaseUrl.Trim();
    }

    public static HttpClient? CreateHttpClient(string? apiBaseUrl, TimeSpan? timeout = null)
    {
        if (string.IsNullOrWhiteSpace(apiBaseUrl))
        {
            return null;
        }

        var normalizedBaseUrl = apiBaseUrl.EndsWith('/') ? apiBaseUrl : $"{apiBaseUrl}/";
        if (!Uri.TryCreate(normalizedBaseUrl, UriKind.Absolute, out var baseAddress) ||
            baseAddress.Scheme != Uri.UriSchemeHttps)
        {
            return null;
        }

        var handler = new HttpClientHandler
        {
            CheckCertificateRevocationList = true
        };
        return new HttpClient(handler)
        {
            BaseAddress = baseAddress,
            Timeout = timeout ?? TimeSpan.FromSeconds(10)
        };
    }
}
