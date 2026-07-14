using System.Net;
using System.Text;
using FlowNote.Windows.Core.Notifications;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Storage;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class ServerNotificationCursorServiceTests
{
    private static readonly string DatabasePath = Path.Combine(
        FlowNoteLocalDatabase.DefaultDataDirectory,
        "flownote.core-tests.sqlite");

    [Fact]
    public void CursorIsPersistentAndIsolatedByUserAndServerScope()
    {
        var service = CreateService();
        var suffix = Guid.NewGuid().ToString("N");
        var serverA = "HTTPS://Factory.Example:443/api";
        var serverB = "https://factory-b.example/api/";
        var userA = $"user-a-{suffix}";
        var userB = $"user-b-{suffix}";

        service.ProcessBatch(serverA, userA, Page(10, Message("message-a", 10)), true);
        service.ProcessBatch(serverA, userB, Page(20, Message("message-b", 20)), true);
        service.ProcessBatch(serverB, userA, Page(30, Message("message-c", 30)), true);

        var restarted = CreateService();
        Assert.Equal(10, restarted.Get("https://factory.example/api/", userA).LastSuccessCursor);
        Assert.Equal(20, restarted.Get(serverA, userB).LastSuccessCursor);
        Assert.Equal(30, restarted.Get(serverB, userA).LastSuccessCursor);
        Assert.False(restarted.Get(serverB, userB).Exists);
    }

    [Fact]
    public void ProcessingFailureRollsBackCursorAndSuccessfulReplayIsIdempotent()
    {
        var service = CreateService();
        var suffix = Guid.NewGuid().ToString("N");
        var scope = $"https://failure-{suffix}.example/";
        var user = $"user-{suffix}";
        var page = Page(2, Message("message-1", 1), Message("message-2", 2));
        var attempts = 0;

        Assert.Throws<InvalidOperationException>(() => service.ProcessBatch(
            scope,
            user,
            page,
            true,
            notification =>
            {
                attempts++;
                if (notification.Cursor == 2)
                {
                    throw new InvalidOperationException("강제 처리 실패");
                }
            }));

        Assert.False(service.Get(scope, user).Exists);
        var replay = service.ProcessBatch(scope, user, page, true, _ => attempts++);
        Assert.Equal(2, replay.ProcessedCount);
        Assert.Equal(2, replay.State.LastSuccessCursor);

        var duplicateReplay = service.ProcessBatch(scope, user, page, true, _ => attempts++);
        Assert.Equal(0, duplicateReplay.ProcessedCount);
        Assert.Equal(2, duplicateReplay.DuplicateCount);
        Assert.Equal(4, attempts);
    }

    [Fact]
    public void LogoutAndReloginKeepCursorButServerRewindRequiresAdministratorReset()
    {
        var service = CreateService();
        var suffix = Guid.NewGuid().ToString("N");
        var scope = $"https://restore-{suffix}.example/";
        var user = $"user-{suffix}";
        service.ProcessBatch(scope, user, Page(50, Message("message-50", 50)), true);

        var afterLogoutAndRelogin = CreateService();
        Assert.Equal(50, afterLogoutAndRelogin.Get(scope, user).LastSuccessCursor);
        var rewind = afterLogoutAndRelogin.ProcessBatch(scope, user, Page(3), true);
        Assert.True(rewind.ResetRequired);
        Assert.Equal(50, rewind.State.LastSuccessCursor);
        Assert.Equal(3, rewind.State.ObservedServerCursor);

        Assert.Throws<UnauthorizedAccessException>(() =>
            afterLogoutAndRelogin.ResetAfterAdministratorConfirmation(scope, user, "team-member", "team-member"));
        var reset = afterLogoutAndRelogin.ResetAfterAdministratorConfirmation(
            scope,
            user,
            "system-admin",
            "system-admin");
        Assert.Equal(0, reset.LastSuccessCursor);
        Assert.False(reset.InitialSyncCompleted);
        Assert.Equal("system-admin", reset.ResetConfirmedBy);

        var caughtUp = afterLogoutAndRelogin.ProcessBatch(
            scope,
            user,
            Page(3, Message("restored-message", 3)),
            true);
        Assert.Equal(3, caughtUp.State.LastSuccessCursor);
        var preservedMessageId = afterLogoutAndRelogin.ProcessBatch(
            scope,
            user,
            Page(50, Message("message-50", 50)),
            true);
        Assert.Equal(0, preservedMessageId.ProcessedCount);
        Assert.Equal(1, preservedMessageId.DuplicateCount);
    }

    [Fact]
    public async Task UnauthorizedPollingDoesNotAdvanceCursor()
    {
        var service = CreateService();
        var suffix = Guid.NewGuid().ToString("N");
        var scope = $"https://unauthorized-{suffix}.example/";
        var user = $"user-{suffix}";
        service.ProcessBatch(scope, user, Page(8, Message("message-8", 8)), true);

        using var httpClient = new HttpClient(new UnauthorizedHandler())
        {
            BaseAddress = new Uri(scope)
        };
        var client = new FlowNoteServerChannelClient(httpClient);
        await Assert.ThrowsAsync<FlowNoteServerAuthenticationException>(() =>
            client.PollMyNotificationsAsync(afterId: 8));

        Assert.Equal(8, service.Get(scope, user).LastSuccessCursor);
    }

    [Fact]
    public void MissingCursorAfterLocalDatabaseRecoveryStartsAtZeroWithInitialSyncPending()
    {
        var service = CreateService();
        var state = service.Get(
            $"https://recovered-{Guid.NewGuid():N}.example/",
            $"user-{Guid.NewGuid():N}");

        Assert.False(state.Exists);
        Assert.Equal(0, state.LastSuccessCursor);
        Assert.False(state.InitialSyncCompleted);
    }

    private static ServerNotificationCursorService CreateService()
    {
        var database = new FlowNoteLocalDatabase(DatabasePath);
        database.Initialize();
        return new ServerNotificationCursorService(database);
    }

    private static ServerNotificationPage Page(long serverCursor, params ServerUserNotificationResponse[] items) =>
        new(items, serverCursor);

    private static ServerUserNotificationResponse Message(string messageId, long cursor) => new()
    {
        MessageId = messageId,
        ChannelId = "channel-test",
        MessageType = "NOTICE",
        SourceType = "SYSTEM",
        SourceId = messageId,
        Title = messageId,
        ChannelName = "테스트 채널",
        Cursor = cursor,
        CreatedAt = DateTime.UtcNow
    };

    private sealed class UnauthorizedHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.Unauthorized)
            {
                Content = new StringContent("{\"detail\":\"expired\"}", Encoding.UTF8, "application/json")
            });
    }
}
