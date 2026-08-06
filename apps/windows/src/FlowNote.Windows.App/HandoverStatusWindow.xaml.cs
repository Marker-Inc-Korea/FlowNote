using System.Net.Http;
using System.Windows;
using System.Windows.Controls;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.App;

public partial class HandoverStatusWindow : Window
{
    private readonly FlowNoteServerChannelClient? channelClient;
    private readonly string currentUserId;
    private readonly string? initialHandoverId;

    public HandoverStatusWindow(
        FlowNoteServerChannelClient? channelClient,
        string currentUserId,
        string? initialHandoverId = null)
    {
        InitializeComponent();
        this.channelClient = channelClient;
        this.currentUserId = currentUserId;
        this.initialHandoverId = initialHandoverId;
        Loaded += HandoverStatusWindow_Loaded;
    }

    private async void HandoverStatusWindow_Loaded(object sender, RoutedEventArgs e)
    {
        await RefreshHandoversAsync();
    }

    private async void RefreshButton_Click(object sender, RoutedEventArgs e)
    {
        await RefreshHandoversAsync();
    }

    private async Task RefreshHandoversAsync()
    {
        if (!EnsureServerConnected())
        {
            return;
        }

        try
        {
            var handoversTask = channelClient!.ListHandoversAsync(200);
            var channelsTask = channelClient.ListChannelsAsync(status: "ACTIVE");
            await Task.WhenAll(handoversTask, channelsTask);
            var channels = channelsTask.Result.ToDictionary(item => item.ChannelId);
            var rows = handoversTask.Result
                .Select(handover => HandoverSupervisionRow.From(
                    handover,
                    channels.GetValueOrDefault(handover.ChannelId)))
                .ToList();
            HandoverGrid.ItemsSource = rows;
            ReceiptGrid.ItemsSource = Array.Empty<ServerHandoverReceiptResponse>();
            if (!string.IsNullOrWhiteSpace(initialHandoverId))
            {
                var selected = rows.FirstOrDefault(item =>
                    item.Handover.HandoverId == initialHandoverId);
                if (selected is not null)
                {
                    HandoverGrid.SelectedItem = selected;
                    HandoverGrid.ScrollIntoView(selected);
                }
            }
            var unconfirmed = rows.Sum(item => item.UnconfirmedRecipientCount);
            var followUp = rows.Sum(item => item.FollowUpRequiredCount);
            StatusTextBlock.Text =
                $"인수인계 {rows.Count}건 · 미확인 {unconfirmed}명 · 후속 조치 {followUp}명을 조회했습니다.";
        }
        catch (Exception exception)
        {
            StatusTextBlock.Text = BuildServerFailureMessage(exception);
        }
    }

    private void HandoverGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (HandoverGrid.SelectedItem is not HandoverSupervisionRow row)
        {
            ReceiptGrid.ItemsSource = Array.Empty<ServerHandoverReceiptResponse>();
            return;
        }

        ReceiptGrid.ItemsSource = row.Handover.Receipts;
        StatusTextBlock.Text =
            $"{row.ChannelTypeLabel} · {row.ChannelName} · {row.Title}: " +
            $"{row.Handover.ReceiptSummary}. 수신자별 상태와 후속 메모를 확인하세요.";
    }

    private async void ReadButton_Click(object sender, RoutedEventArgs e)
    {
        await UpdateSelectedReceiptAsync("READ", "읽음");
    }

    private async void AckButton_Click(object sender, RoutedEventArgs e)
    {
        await UpdateSelectedReceiptAsync("ACKNOWLEDGED", "확인");
    }

    private async void HoldButton_Click(object sender, RoutedEventArgs e)
    {
        await UpdateSelectedReceiptAsync("UNREAD", "보류");
    }

    private async void FollowUpRequiredButton_Click(object sender, RoutedEventArgs e)
    {
        await UpdateSelectedReceiptAsync("FOLLOW_UP_REQUIRED", "후속 필요");
    }

    private async Task UpdateSelectedReceiptAsync(string receiptStatus, string label)
    {
        if (!EnsureServerConnected())
        {
            return;
        }

        if (HandoverGrid.SelectedItem is not HandoverSupervisionRow row ||
            ReceiptGrid.SelectedItem is not ServerHandoverReceiptResponse receipt)
        {
            StatusTextBlock.Text = "상태를 변경할 인수인계와 수신자를 선택하세요.";
            return;
        }

        try
        {
            var updated = await channelClient!.UpdateHandoverReceiptAsync(
                row.Handover.HandoverId,
                receipt.ReceiptId,
                new ServerHandoverReceiptUpdateRequest
                {
                    ReceiptStatus = receiptStatus,
                    Note = Clean(ReceiptNoteTextBox.Text) ?? $"{label}: Windows 확인 현황"
                });
            ReplaceSelectedHandover(updated);
            StatusTextBlock.Text = $"{receipt.RecipientId} 수신자 상태를 {label}(으)로 변경했습니다.";
        }
        catch (Exception exception)
        {
            StatusTextBlock.Text = BuildServerFailureMessage(exception);
        }
    }

    private async void FollowUpFieldCommentButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureServerConnected())
        {
            return;
        }

        if (HandoverGrid.SelectedItem is not HandoverSupervisionRow row)
        {
            StatusTextBlock.Text = "후속 FieldComment를 만들 인수인계를 선택하세요.";
            return;
        }

        var handover = row.Handover;
        var content = Clean(ReceiptNoteTextBox.Text)
            ?? $"Windows 확인 현황에서 후속 FieldComment를 작성했습니다. 제목: {handover.Title}";
        try
        {
            var result = await channelClient!.CreateHandoverFollowUpWithStatusAsync(
                handover,
                content,
                currentUserId);
            StatusTextBlock.Text = result.ChannelMessagePublished
                ? "후속 현장 코멘트와 채널 알림을 저장했습니다. 원천 인수인계와 처리 기록은 서버에 보존됩니다. 다음: 코멘트 검토에서 후속 조치를 확인하세요."
                : "후속 현장 코멘트는 저장했지만 채널 알림은 보내지 못했습니다. 원천 인수인계와 코멘트는 서버에 보존됩니다. 다음: 같은 내용으로 다시 저장해 알림만 복구하세요. 코멘트는 중복 생성되지 않습니다.";
        }
        catch (Exception exception)
        {
            StatusTextBlock.Text = BuildServerFailureMessage(exception);
        }
    }

    private void ReplaceSelectedHandover(ServerHandoverResponse updated)
    {
        if (HandoverGrid.ItemsSource is not IEnumerable<HandoverSupervisionRow> current)
        {
            return;
        }

        var handovers = current
            .Select(item => item.Handover.HandoverId == updated.HandoverId
                ? item with { Handover = updated }
                : item)
            .ToList();
        HandoverGrid.ItemsSource = handovers;
        HandoverGrid.SelectedItem = handovers.First(
            item => item.Handover.HandoverId == updated.HandoverId);
        ReceiptGrid.ItemsSource = updated.Receipts;
    }

    private void CloseButton_Click(object sender, RoutedEventArgs e)
    {
        Close();
    }

    private bool EnsureServerConnected()
    {
        if (channelClient is not null)
        {
            return true;
        }

        StatusTextBlock.Text = WorkflowFailureGuidance.Format(
            "서버 연결이 없어 인수인계 작업을 시작하지 못했습니다.",
            "로컬 데이터와 동기화 큐",
            "현재 사용자",
            "서버 주소와 로그인을 확인한 뒤 다시 시도하세요.");
        HandoverGrid.ItemsSource = Array.Empty<ServerHandoverResponse>();
        ReceiptGrid.ItemsSource = Array.Empty<ServerHandoverReceiptResponse>();
        return false;
    }

    private static string? Clean(string value)
    {
        var cleaned = value.Trim();
        return string.IsNullOrWhiteSpace(cleaned) ? null : cleaned;
    }

    private static string BuildServerFailureMessage(Exception exception)
    {
        return WorkflowFailureGuidance.FromServerException(
            exception,
            "인수인계 작업 결과를 확인하지 못했습니다.",
            "기존 인수인계, FieldComment와 수신 확인 기록",
            "네트워크를 확인하고 목록을 새로고침한 뒤 다시 시도하세요.");
    }
}

internal sealed record HandoverSupervisionRow(
    ServerHandoverResponse Handover,
    string ChannelName,
    string ChannelTypeLabel)
{
    public string Title => Handover.Title;

    public string StatusLabel => Handover.StatusLabel;

    public int UnconfirmedRecipientCount => Handover.UnconfirmedRecipientCount;

    public int FollowUpRequiredCount => Handover.FollowUpRequiredCount;

    public string SourceLinkText => Handover.SourceLinkText;

    public static HandoverSupervisionRow From(
        ServerHandoverResponse handover,
        ServerNotificationChannelResponse? channel) => new(
            handover,
            channel?.Name ?? handover.ChannelId,
            channel?.ChannelTypeLabel ?? "채널");
}
