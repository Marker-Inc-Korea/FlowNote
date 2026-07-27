using System.Security.Authentication;
using FlowNote.Windows.Core.Auth;
using FlowNote.Windows.Core.ServerApi;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class ServerConnectionGuidanceTests
{
    [Fact]
    public async Task CertificateFailureDoesNotFallBackAndShowsRecoverySteps()
    {
        using var httpClient = CreateThrowingClient(
            new HttpRequestException(
                "TLS failed",
                new AuthenticationException("certificate rejected")));

        var result = await ServerAwareAuthService.TryServerLoginAsync(
            httpClient,
            "admin",
            "1234");

        Assert.NotNull(result);
        Assert.False(result.Success);
        Assert.Contains("인증서", result.FailureReason);
        Assert.Contains("날짜와 시간", result.FailureReason);
        Assert.Contains("자동 전환하지 않", result.FailureReason);
        Assert.DoesNotContain("TLS failed", result.FailureReason);
    }

    [Fact]
    public async Task TimeoutDoesNotFallBackAndShowsReconnectSteps()
    {
        using var httpClient = CreateThrowingClient(new TaskCanceledException());

        var result = await ServerAwareAuthService.TryServerLoginAsync(
            httpClient,
            "admin",
            "1234");

        Assert.NotNull(result);
        Assert.False(result.Success);
        Assert.Contains("시간이 초과", result.FailureReason);
        Assert.Contains("서버 주소", result.FailureReason);
    }

    [Fact]
    public async Task AddressFailureDoesNotExposeTransportDetails()
    {
        Assert.Null(FlowNoteServerApiEnvironment.CreateHttpClient(
            "ftp://flownote.invalid"));

        using var httpClient = CreateThrowingClient(
            new HttpRequestException("host=private-server token=secret"));

        var result = await ServerAwareAuthService.TryServerLoginAsync(
            httpClient,
            "admin",
            "1234");

        Assert.NotNull(result);
        Assert.False(result.Success);
        Assert.Contains("FLOWNOTE_API_BASE_URL", result.FailureReason);
        Assert.Contains("다시 실행", result.FailureReason);
        Assert.DoesNotContain("private-server", result.FailureReason);
        Assert.DoesNotContain("secret", result.FailureReason);
    }

    private static HttpClient CreateThrowingClient(Exception exception)
    {
        return new HttpClient(new ThrowingHandler(exception))
        {
            BaseAddress = new Uri("https://flownote.invalid/")
        };
    }

    private sealed class ThrowingHandler(Exception exception) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            return Task.FromException<HttpResponseMessage>(exception);
        }
    }
}
