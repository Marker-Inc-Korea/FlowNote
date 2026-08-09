using System.Security.Authentication;
using FlowNote.Windows.Core.Auth;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Storage;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class ServerConnectionGuidanceTests
{
    [Fact]
    public void MissingServerOverrideUsesPublicExampleServer()
    {
        Assert.Equal(
            "https://flownote.example",
            FlowNoteServerApiEnvironment.ResolveApiBaseUrl(null));
    }

    [Fact]
    public void ExplicitServerOverrideRemainsAvailableForApprovedTesting()
    {
        Assert.Equal(
            "https://test.flownote.example",
            FlowNoteServerApiEnvironment.ResolveApiBaseUrl(
                "  https://test.flownote.example  "));
    }

    [Fact]
    public void HttpServerOverrideIsRejected()
    {
        Assert.Null(FlowNoteServerApiEnvironment.CreateHttpClient(
            "http://127.0.0.1:5184"));
    }

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
        Assert.Contains("CRL/OCSP", result.FailureReason);
        Assert.Contains("폐기", result.FailureReason);
        Assert.Contains("날짜·시간", result.FailureReason);
        Assert.Contains("자동 전환하지 않", result.FailureReason);
        Assert.Contains("누락 항목:", result.FailureReason);
        Assert.Contains("보존된 로컬 상태:", result.FailureReason);
        Assert.Contains("동기화 큐", result.FailureReason);
        Assert.Contains("cursor", result.FailureReason);
        Assert.Contains("처리 담당자:", result.FailureReason);
        Assert.Contains("가능한 다음 행동:", result.FailureReason);
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
        Assert.Contains("HTTPS 주소", result.FailureReason);
        Assert.Contains("가능한 다음 행동:", result.FailureReason);
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
        Assert.Contains("보존된 로컬 상태:", result.FailureReason);
        Assert.Contains("처리 담당자:", result.FailureReason);
        Assert.DoesNotContain("private-server", result.FailureReason);
        Assert.DoesNotContain("secret", result.FailureReason);
    }

    [Fact]
    public async Task ConfiguredServerFailureNeverFallsBackToValidLocalAccount()
    {
        var artifactDirectory = Path.Combine(
            Path.GetTempPath(),
            "flownote-login-fail-closed-tests",
            Guid.NewGuid().ToString("N"));
        var database = new FlowNoteLocalDatabase(
            Path.Combine(artifactDirectory, "flownote.local.sqlite"));
        database.Initialize();
        using var httpClient = CreateThrowingClient(
            new HttpRequestException("server unavailable"));
        var auth = new ServerAwareAuthService(new AuthService(database), httpClient);

        var result = await auth.LoginAsync("admin", "1234");

        Assert.False(result.Success);
        Assert.Null(result.UserId);
        Assert.Contains("로컬 로그인으로 우회하지 마세요", result.FailureReason);
    }

    [Fact]
    public void StartupFailureGuidanceProtectsSourcesQueueAndCursor()
    {
        var guidance = ServerConnectionGuidance.LocalStartupFailureMessage;

        Assert.Contains("실패 내용:", guidance);
        Assert.Contains("로컬 원천", guidance);
        Assert.Contains("동기화 큐", guidance);
        Assert.Contains("cursor", guidance);
        Assert.Contains("자동 삭제·초기화·덮어쓰기하지 않습니다", guidance);
        Assert.Contains("처리 담당자:", guidance);
        Assert.Contains("가능한 다음 행동:", guidance);
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
