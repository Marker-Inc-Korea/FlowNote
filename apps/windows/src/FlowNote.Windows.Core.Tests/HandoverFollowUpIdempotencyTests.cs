using System.Net;
using System.Text;
using FlowNote.Windows.Core.ServerApi;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class HandoverFollowUpIdempotencyTests
{
    [Fact]
    public async Task SameHandoverContentReusesCommentAndChannelMessage()
    {
        var handler = new FollowUpHandler();
        using var http = new HttpClient(handler)
        {
            BaseAddress = new Uri("https://server.example/")
        };
        var client = new FlowNoteServerChannelClient(http);
        var handover = new ServerHandoverResponse
        {
            HandoverId = "handover-1",
            ChannelId = "channel-1",
            Title = "교대 인수인계"
        };

        var first = await client.CreateHandoverFollowUpWithStatusAsync(
            handover,
            "베어링 온도를 다시 확인합니다.",
            "worker-1");
        var retry = await client.CreateHandoverFollowUpWithStatusAsync(
            handover,
            "베어링 온도를 다시 확인합니다.",
            "worker-1");

        Assert.True(first.ChannelMessagePublished);
        Assert.True(retry.ChannelMessagePublished);
        Assert.Equal(first.FieldComment.CommentId, retry.FieldComment.CommentId);
        Assert.Equal(first.OperationKey, retry.OperationKey);
        Assert.Equal(2, handler.FieldCommentBodies.Count);
        Assert.All(handler.FieldCommentBodies, body =>
            Assert.Contains(first.OperationKey, body, StringComparison.Ordinal));
        Assert.Equal(1, handler.ChannelMessagePostCount);
    }

    [Fact]
    public async Task ChannelFailureReportsPartialSuccessWithoutLosingComment()
    {
        var handler = new FollowUpHandler(failChannelMessage: true);
        using var http = new HttpClient(handler)
        {
            BaseAddress = new Uri("https://server.example/")
        };
        var client = new FlowNoteServerChannelClient(http);

        var result = await client.CreateHandoverFollowUpWithStatusAsync(
            new ServerHandoverResponse
            {
                HandoverId = "handover-2",
                ChannelId = "channel-2",
                Title = "야간조 인수인계"
            },
            "후속 점검이 필요합니다.",
            "worker-2");

        Assert.False(result.ChannelMessagePublished);
        Assert.Equal("comment-1", result.FieldComment.CommentId);
        Assert.StartsWith("handover-follow-up:", result.OperationKey);
    }

    private sealed class FollowUpHandler(bool failChannelMessage = false) : HttpMessageHandler
    {
        public List<string> FieldCommentBodies { get; } = [];

        public int ChannelMessagePostCount { get; private set; }

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            var path = request.RequestUri!.PathAndQuery;
            if (request.Method == HttpMethod.Post && path == "/api/v1/field-comments")
            {
                FieldCommentBodies.Add(
                    await request.Content!.ReadAsStringAsync(cancellationToken));
                return Json(HttpStatusCode.Created, """
                    {
                      "comment_id":"comment-1",
                      "work_record_id":"handover-1",
                      "entry_source":"handover_follow_up"
                    }
                    """);
            }

            if (request.Method == HttpMethod.Get &&
                path.StartsWith("/api/v1/notification-channels/channel-", StringComparison.Ordinal))
            {
                return ChannelMessagePostCount == 0
                    ? Json(HttpStatusCode.OK, "[]")
                    : Json(HttpStatusCode.OK, """
                        [{
                          "message_id":"message-1",
                          "channel_id":"channel-1",
                          "message_type":"FIELD_COMMENT_EVENT",
                          "source_type":"FIELD_COMMENT",
                          "source_id":"comment-1",
                          "title":"후속 현장 코멘트",
                          "created_at":"2026-07-28T00:00:00Z"
                        }]
                        """);
            }

            if (request.Method == HttpMethod.Post && path.EndsWith("/messages", StringComparison.Ordinal))
            {
                ChannelMessagePostCount++;
                if (failChannelMessage)
                {
                    throw new HttpRequestException("응답 유실");
                }
                return Json(HttpStatusCode.Created, """
                    {
                      "message_id":"message-1",
                      "channel_id":"channel-1",
                      "message_type":"FIELD_COMMENT_EVENT",
                      "source_type":"FIELD_COMMENT",
                      "source_id":"comment-1",
                      "title":"후속 현장 코멘트",
                      "created_at":"2026-07-28T00:00:00Z"
                    }
                    """);
            }

            throw new InvalidOperationException($"Unexpected request: {request.Method} {path}");
        }

        private static HttpResponseMessage Json(HttpStatusCode status, string body) => new(status)
        {
            Content = new StringContent(body, Encoding.UTF8, "application/json")
        };
    }
}
