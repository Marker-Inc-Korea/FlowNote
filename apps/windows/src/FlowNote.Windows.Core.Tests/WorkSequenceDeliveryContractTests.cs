using System.Net;
using System.Text;
using FlowNote.Windows.Core.ServerApi;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class WorkSequenceDeliveryContractTests
{
    [Fact]
    public async Task PreviewKeepsChannelRecipientsSourceHistoryAndPublishedDocument()
    {
        var handler = new RecordingHandler(HttpStatusCode.OK, PreviewJson());
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://server.example/") };
        var client = new FlowNoteServerChannelClient(http);

        var preview = await client.PreviewWorkSequenceDeliveryAsync("board-a", "candidate-a", "channel-a");

        Assert.Contains("channelId=channel-a", handler.RequestUri);
        Assert.Equal(12, preview.CurrentBoardRevision);
        Assert.True(preview.CanDeliver);
        Assert.Equal("history-a", preview.Source.ChangeId);
        Assert.Equal("document-a", preview.Source.PublishedDocumentId);
        Assert.Single(preview.Recipients);
    }

    [Fact]
    public async Task DeliverySendsStableKeyRevisionIntentAndRecipientSet()
    {
        var handler = new RecordingHandler(HttpStatusCode.Created, DeliveryJson());
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://server.example/") };
        var client = new FlowNoteServerChannelClient(http);
        var request = new ServerWorkSequenceDeliveryRequest
        {
            ChannelId = "channel-a",
            DeliveryMode = "HANDOVER",
            RecipientIds = ["user-a"],
            Title = "작업순서 변경",
            Body = "포장 작업을 먼저 진행합니다.",
            Reason = "현장 우선순위 공유",
            BaseBoardRevision = 12,
            IdempotencyKey = "wpf:wseq-delivery:stable"
        };

        var response = await client.DeliverWorkSequenceCandidateAsync(
            "board-a",
            "candidate-a",
            request);

        Assert.Equal("COMPLETED", response.Status);
        Assert.Equal(1, response.SuccessCount);
        Assert.Contains("\"baseBoardRevision\":12", handler.RequestBody);
        Assert.Contains("\"idempotencyKey\":\"wpf:wseq-delivery:stable\"", handler.RequestBody);
        Assert.Contains("\"recipientIds\":[\"user-a\"]", handler.RequestBody);
    }

    [Fact]
    public void StableDeliveryKeySurvivesRestartAndTracksTheCanonicalIntent()
    {
        var request = new ServerWorkSequenceDeliveryRequest
        {
            ChannelId = "channel-a",
            DeliveryMode = "handover",
            RecipientIds = ["user-b", "user-a"],
            Title = " 작업순서 변경 ",
            Body = "안내",
            Reason = "공유",
            BaseBoardRevision = 12,
        };
        var reorderedAfterRestart = request with { RecipientIds = ["user-a", "user-b"] };

        var key = request.BuildStableIdempotencyKey("board-a", "candidate-a");

        Assert.Equal(key, reorderedAfterRestart.BuildStableIdempotencyKey("board-a", "candidate-a"));
        Assert.NotEqual(
            key,
            (request with { Body = "다른 안내" }).BuildStableIdempotencyKey("board-a", "candidate-a"));
        Assert.StartsWith("wpf:wseq-delivery:", key);
    }

    [Fact]
    public async Task ManageableChannelQueryDoesNotExposeUnmanageableChannelNames()
    {
        var handler = new RecordingHandler(HttpStatusCode.OK, "[]");
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://server.example/") };
        var client = new FlowNoteServerChannelClient(http);

        await client.ListChannelsAsync(status: "ACTIVE", manageableOnly: true);

        Assert.Contains("manageableOnly=true", handler.RequestUri);
    }

    private static string PreviewJson() => """
        {
          "candidate_id":"candidate-a","candidate_status":"CANDIDATE",
          "candidate_board_revision":12,"current_board_revision":12,"expires_at":"2026-08-07T00:00:00Z",
          "channel_id":"channel-a","channel_name":"포장 라인","channel_type":"LINE",
          "channel_source_type":"WORK_RECORD","channel_source_id":"record-a",
          "required_member_role":"OWNER_OR_MANAGER","can_deliver":true,
          "recipients":[{"user_id":"user-a","display_name":"작업자","member_role":"MEMBER"}],
          "recipient_count":1,"title":"작업순서 변경","body":"안내",
          "source":{"source_type":"WORK_SEQUENCE_ITEM","source_id":"item-a","change_id":"history-a",
          "item_title":"포장","published_document_id":"document-a","published_document_version_id":"version-a",
          "published_document_title":"포장 작업표준"}
        }
        """;

    private static string DeliveryJson() => """
        {
          "delivery_id":"delivery-a","candidate_id":"candidate-a","candidate_status":"SENT",
          "board_id":"board-a","board_revision":12,"change_id":"history-a","channel_id":"channel-a",
          "delivery_mode":"HANDOVER","intent_hash_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          "message_id":"message-a","handover_id":"handover-a","source_type":"WORK_SEQUENCE_ITEM",
          "source_id":"item-a","source_version_id":null,"related_document_id":"document-a",
          "related_document_version_id":"version-a","status":"COMPLETED","success_count":1,"failure_count":0,
          "recipients":[{"recipient_id":"user-a","delivery_status":"DELIVERED","handover_receipt_id":"receipt-a",
          "error_code":null,"error_message":null,"attempt_count":1}],
          "created_at":"2026-08-06T00:00:00Z","updated_at":"2026-08-06T00:00:00Z"
        }
        """;

    private sealed class RecordingHandler(HttpStatusCode statusCode, string responseBody) : HttpMessageHandler
    {
        public string RequestBody { get; private set; } = string.Empty;
        public string RequestUri { get; private set; } = string.Empty;

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            RequestUri = request.RequestUri?.ToString() ?? string.Empty;
            RequestBody = request.Content is null
                ? string.Empty
                : await request.Content.ReadAsStringAsync(cancellationToken);
            return new HttpResponseMessage(statusCode)
            {
                Content = new StringContent(responseBody, Encoding.UTF8, "application/json")
            };
        }
    }
}
