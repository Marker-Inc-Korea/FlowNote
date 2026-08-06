using System.Net;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace FlowNote.Windows.Core.ServerApi;

public sealed class FlowNoteServerChannelClient
{
    public const string NotificationCursorHeaderName = "X-FlowNote-Notification-Cursor";
    private readonly HttpClient httpClient;

    public FlowNoteServerChannelClient(HttpClient httpClient)
    {
        this.httpClient = httpClient;
    }

    public async Task<IReadOnlyList<ServerNotificationChannelResponse>> ListChannelsAsync(
        string? channelType = null,
        string? status = null,
        CancellationToken cancellationToken = default,
        bool manageableOnly = false)
    {
        var query = new List<string>();
        if (!string.IsNullOrWhiteSpace(channelType))
        {
            query.Add($"channelType={Uri.EscapeDataString(channelType.Trim())}");
        }

        if (!string.IsNullOrWhiteSpace(status))
        {
            query.Add($"status={Uri.EscapeDataString(status.Trim())}");
        }
        if (manageableOnly)
        {
            query.Add("manageableOnly=true");
        }

        using var response = await httpClient.GetAsync(
            query.Count == 0 ? "api/v1/notification-channels" : $"api/v1/notification-channels?{string.Join("&", query)}",
            cancellationToken);
        var channels = await ReadJsonResponse<List<ServerNotificationChannelResponse>>(response, cancellationToken);
        return channels;
    }

    public async Task<ServerWorkSequenceDeliveryPreviewResponse> PreviewWorkSequenceDeliveryAsync(
        string boardId,
        string candidateId,
        string channelId,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync(
            $"api/v1/work-sequence-boards/{Uri.EscapeDataString(boardId)}/notification-candidates/" +
            $"{Uri.EscapeDataString(candidateId)}/delivery-preview?channelId={Uri.EscapeDataString(channelId)}",
            cancellationToken);
        return await ReadJsonResponse<ServerWorkSequenceDeliveryPreviewResponse>(response, cancellationToken);
    }

    public async Task<ServerWorkSequenceDeliveryResponse> DeliverWorkSequenceCandidateAsync(
        string boardId,
        string candidateId,
        ServerWorkSequenceDeliveryRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            $"api/v1/work-sequence-boards/{Uri.EscapeDataString(boardId)}/notification-candidates/" +
            $"{Uri.EscapeDataString(candidateId)}/deliveries",
            request,
            cancellationToken);
        return await ReadJsonResponse<ServerWorkSequenceDeliveryResponse>(response, cancellationToken);
    }

    public async Task<IReadOnlyList<ServerWorkSequenceDeliveryTemplateResponse>> ListWorkSequenceDeliveryTemplatesAsync(
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync(
            "api/v1/work-sequence-delivery-templates",
            cancellationToken);
        return await ReadJsonResponse<List<ServerWorkSequenceDeliveryTemplateResponse>>(response, cancellationToken);
    }

    public async Task<ServerWorkSequenceDeliveryTemplateResponse> CreateWorkSequenceDeliveryTemplateAsync(
        ServerWorkSequenceDeliveryTemplateCreateRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            "api/v1/work-sequence-delivery-templates",
            request,
            cancellationToken);
        return await ReadJsonResponse<ServerWorkSequenceDeliveryTemplateResponse>(response, cancellationToken);
    }

    public async Task<ServerNotificationChannelResponse> CreateChannelAsync(
        ServerNotificationChannelCreateRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            "api/v1/notification-channels",
            request,
            cancellationToken);
        return await ReadJsonResponse<ServerNotificationChannelResponse>(response, cancellationToken);
    }

    public async Task<IReadOnlyList<ServerChannelMemberResponse>> ListChannelMembersAsync(
        string channelId,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync(
            $"api/v1/notification-channels/{Uri.EscapeDataString(channelId)}/members",
            cancellationToken);
        var members = await ReadJsonResponse<List<ServerChannelMemberResponse>>(response, cancellationToken);
        return members;
    }

    public async Task<ServerChannelMemberResponse> UpsertChannelMemberAsync(
        string channelId,
        ServerChannelMemberUpsertRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            $"api/v1/notification-channels/{Uri.EscapeDataString(channelId)}/members",
            request,
            cancellationToken);
        return await ReadJsonResponse<ServerChannelMemberResponse>(response, cancellationToken);
    }

    public async Task<ServerChannelMemberResponse> UpdateChannelMemberAsync(
        string channelId,
        string memberId,
        ServerChannelMemberUpdateRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PatchAsJsonAsync(
            $"api/v1/notification-channels/{Uri.EscapeDataString(channelId)}/members/{Uri.EscapeDataString(memberId)}",
            request,
            cancellationToken);
        return await ReadJsonResponse<ServerChannelMemberResponse>(response, cancellationToken);
    }

    public async Task<ServerChannelMessageResponse> CreateChannelMessageAsync(
        string channelId,
        ServerChannelMessageCreateRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            $"api/v1/notification-channels/{Uri.EscapeDataString(channelId)}/messages",
            request,
            cancellationToken);
        return await ReadJsonResponse<ServerChannelMessageResponse>(response, cancellationToken);
    }

    public async Task<IReadOnlyList<ServerChannelMessageResponse>> ListChannelMessagesAsync(
        string channelId,
        int limit = 100,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync(
            $"api/v1/notification-channels/{Uri.EscapeDataString(channelId)}/messages?limit={Math.Clamp(limit, 1, 500)}",
            cancellationToken);
        var messages = await ReadJsonResponse<List<ServerChannelMessageResponse>>(response, cancellationToken);
        return messages;
    }

    public async Task<IReadOnlyList<ServerUserNotificationResponse>> ListMyNotificationsAsync(
        bool unreadOnly = false,
        int limit = 100,
        long? afterId = null,
        CancellationToken cancellationToken = default)
    {
        var page = await PollMyNotificationsAsync(unreadOnly, limit, afterId, cancellationToken);
        return page.Items;
    }

    public async Task<ServerNotificationPage> PollMyNotificationsAsync(
        bool unreadOnly = false,
        int limit = 100,
        long? afterId = null,
        CancellationToken cancellationToken = default)
    {
        var afterQuery = afterId.HasValue ? $"&afterId={Math.Max(0, afterId.Value)}" : string.Empty;
        using var response = await httpClient.GetAsync(
            $"api/v1/notifications?unreadOnly={unreadOnly.ToString().ToLowerInvariant()}&limit={Math.Clamp(limit, 1, 500)}{afterQuery}",
            cancellationToken);
        var notifications = await ReadJsonResponse<List<ServerUserNotificationResponse>>(response, cancellationToken);
        var serverCursor = notifications.Count == 0 ? 0 : notifications.Max(item => item.Cursor);
        if (response.Headers.TryGetValues(NotificationCursorHeaderName, out var values) &&
            long.TryParse(values.FirstOrDefault(), out var headerCursor) &&
            headerCursor >= 0)
        {
            serverCursor = headerCursor;
        }
        else if (afterId.HasValue)
        {
            serverCursor = Math.Max(serverCursor, afterId.Value);
        }

        return new ServerNotificationPage(notifications, serverCursor);
    }

    public async Task<ServerUserNotificationResponse> MarkNotificationReadAsync(
        string messageId,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PatchAsync(
            $"api/v1/notifications/{Uri.EscapeDataString(messageId)}/read",
            null,
            cancellationToken);
        return await ReadJsonResponse<ServerUserNotificationResponse>(response, cancellationToken);
    }

    public async Task<ServerHandoverResponse> CreateHandoverAsync(
        ServerHandoverCreateRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync("api/v1/handovers", request, cancellationToken);
        return await ReadJsonResponse<ServerHandoverResponse>(response, cancellationToken);
    }

    public async Task<IReadOnlyList<ServerHandoverResponse>> ListHandoversAsync(
        int limit = 100,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync(
            $"api/v1/handovers?limit={Math.Clamp(limit, 1, 200)}",
            cancellationToken);
        var handovers = await ReadJsonResponse<List<ServerHandoverResponse>>(response, cancellationToken);
        return handovers;
    }

    public async Task<ServerHandoverResponse> GetHandoverAsync(
        string handoverId,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync(
            $"api/v1/handovers/{Uri.EscapeDataString(handoverId)}",
            cancellationToken);
        return await ReadJsonResponse<ServerHandoverResponse>(response, cancellationToken);
    }

    public async Task<ServerHandoverResponse> UpdateHandoverReceiptAsync(
        string handoverId,
        string receiptId,
        ServerHandoverReceiptUpdateRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PatchAsJsonAsync(
            $"api/v1/handovers/{Uri.EscapeDataString(handoverId)}/receipts/{Uri.EscapeDataString(receiptId)}",
            request,
            cancellationToken);
        return await ReadJsonResponse<ServerHandoverResponse>(response, cancellationToken);
    }

    public async Task<ServerFieldCommentResponse> CreateHandoverFollowUpFieldCommentAsync(
        ServerHandoverResponse handover,
        string rawContent,
        string actorId,
        CancellationToken cancellationToken = default)
    {
        var result = await CreateHandoverFollowUpWithStatusAsync(
            handover,
            rawContent,
            actorId,
            cancellationToken);
        return result.FieldComment;
    }

    public async Task<ServerHandoverFollowUpResult> CreateHandoverFollowUpWithStatusAsync(
        ServerHandoverResponse handover,
        string rawContent,
        string actorId,
        CancellationToken cancellationToken = default)
    {
        var cleanedContent = rawContent.Trim();
        var operationKey = BuildHandoverFollowUpOperationKey(
            handover.HandoverId,
            actorId,
            cleanedContent);
        var request = new ServerFieldCommentCreateRequest
        {
            WorkRecordId = handover.HandoverId,
            CommentType = "issue",
            InputMode = "free_text",
            RawContent = $"원천 인수인계: {handover.HandoverId}{Environment.NewLine}{cleanedContent}",
            AuthorId = actorId,
            ReportedBy = actorId,
            EntrySource = "handover_follow_up",
            Category = "handover-follow-up",
            Priority = 2,
            IdempotencyKey = operationKey
        };
        using var response = await httpClient.PostAsJsonAsync("api/v1/field-comments", request, cancellationToken);
        var fieldComment = await ReadJsonResponse<ServerFieldCommentResponse>(response, cancellationToken);
        try
        {
            var existingMessage = (await ListChannelMessagesAsync(
                    handover.ChannelId,
                    500,
                    cancellationToken))
                .FirstOrDefault(item =>
                    item.SourceType == "FIELD_COMMENT" &&
                    item.SourceId == fieldComment.CommentId);
            if (existingMessage is not null)
            {
                return new ServerHandoverFollowUpResult(
                    fieldComment,
                    true,
                    operationKey,
                    existingMessage.MessageId);
            }

            var message = await CreateChannelMessageAsync(
                handover.ChannelId,
                new ServerChannelMessageCreateRequest
                {
                    MessageType = "FIELD_COMMENT_EVENT",
                    SourceType = "FIELD_COMMENT",
                    SourceId = fieldComment.CommentId,
                    Title = $"인수인계 후속 FieldComment: {handover.Title}",
                    Body = $"원천 인수인계 {handover.HandoverId}에서 후속 FieldComment를 작성했습니다."
                },
                cancellationToken);
            return new ServerHandoverFollowUpResult(
                fieldComment,
                true,
                operationKey,
                message.MessageId);
        }
        catch (Exception exception) when (
            exception is InvalidOperationException
                or HttpRequestException
                or TaskCanceledException)
        {
            return new ServerHandoverFollowUpResult(
                fieldComment,
                false,
                operationKey,
                null);
        }
    }

    internal static string BuildHandoverFollowUpOperationKey(
        string handoverId,
        string actorId,
        string rawContent)
    {
        var source = $"{handoverId.Trim()}\n{actorId.Trim()}\n{rawContent.Trim()}";
        var digest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(source)))
            .ToLowerInvariant();
        return $"handover-follow-up:{digest}";
    }

    private static async Task<T> ReadJsonResponse<T>(
        HttpResponseMessage response,
        CancellationToken cancellationToken)
    {
        if (!response.IsSuccessStatusCode)
        {
            var errorBody = await response.Content.ReadAsStringAsync(cancellationToken);
            if (response.StatusCode == HttpStatusCode.Conflict)
            {
                try
                {
                    using var document = JsonDocument.Parse(errorBody);
                    if (!document.RootElement.TryGetProperty("detail", out var detail) ||
                        detail.ValueKind != JsonValueKind.Object)
                    {
                        throw new JsonException("Conflict detail is not an object.");
                    }
                    string? ReadString(string name) =>
                        detail.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
                            ? value.GetString()
                            : null;
                    int? ReadInt(string name) =>
                        detail.TryGetProperty(name, out var value) && value.TryGetInt32(out var number)
                            ? number
                            : null;
                    throw new FlowNoteServerConflictException(
                        ReadString("code") ?? "SERVER_CONFLICT",
                        ReadString("message") ?? "서버 전달 요청이 충돌했습니다.",
                        ReadInt("expectedRevision"),
                        ReadInt("currentRevision"),
                        null,
                        null,
                        null,
                        errorBody);
                }
                catch (JsonException)
                {
                    throw new FlowNoteServerConflictException(
                        "SERVER_CONFLICT",
                        "서버 전달 요청이 충돌했습니다. 후보와 채널을 새로고침하세요.",
                        null, null, null, null, null, errorBody);
                }
            }
            if (response.StatusCode is HttpStatusCode.Unauthorized
                or HttpStatusCode.Forbidden
                or HttpStatusCode.NotFound)
            {
                throw ServerAccessDenialPolicy.CreateException(response.StatusCode, errorBody);
            }

            throw new InvalidOperationException(
                "채널 요청을 처리하지 못했습니다. 잠시 후 다시 시도하세요.");
        }

        var result = await response.Content.ReadFromJsonAsync<T>(cancellationToken);
        return result ?? throw new InvalidOperationException("FlowNote API returned an empty response body.");
    }
}
