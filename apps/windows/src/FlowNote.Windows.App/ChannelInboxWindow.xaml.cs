using System.Net.Http;
using System.Windows;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.App;

public partial class ChannelInboxWindow : Window
{
    private readonly FlowNoteServerChannelClient? channelClient;
    private readonly string currentUserId;
    private readonly string? initialChannelId;

    public ChannelInboxWindow(
        FlowNoteServerChannelClient? channelClient,
        string currentUserId,
        string? initialChannelId = null)
    {
        InitializeComponent();
        this.channelClient = channelClient;
        this.currentUserId = currentUserId;
        this.initialChannelId = initialChannelId;
        Loaded += ChannelInboxWindow_Loaded;
    }

    private async void ChannelInboxWindow_Loaded(object sender, RoutedEventArgs e)
    {
        await RefreshAsync();
    }

    private async void RefreshButton_Click(object sender, RoutedEventArgs e)
    {
        await RefreshAsync();
    }

    private async Task RefreshAsync()
    {
        if (!EnsureServerConnected())
        {
            return;
        }

        try
        {
            var channels = await channelClient!.ListChannelsAsync(status: "ACTIVE");
            var notifications = await channelClient.ListMyNotificationsAsync(UnreadOnlyCheckBox.IsChecked == true);
            var handovers = await channelClient.ListHandoversAsync();
            ChannelGrid.ItemsSource = channels;
            NotificationGrid.ItemsSource = notifications;
            HandoverGrid.ItemsSource = handovers;
            if (!string.IsNullOrWhiteSpace(initialChannelId))
            {
                var selected = channels.FirstOrDefault(item => item.ChannelId == initialChannelId);
                if (selected is not null)
                {
                    ChannelGrid.SelectedItem = selected;
                    ChannelGrid.ScrollIntoView(selected);
                }
            }
            StatusTextBlock.Text = $"내 채널 {channels.Count}개, 메시지 {notifications.Count}건, 인수인계 {handovers.Count}건을 조회했습니다.";
        }
        catch (Exception exception)
        {
            StatusTextBlock.Text = BuildServerFailureMessage(exception);
        }
    }

    private async void ChannelGrid_SelectionChanged(object sender, System.Windows.Controls.SelectionChangedEventArgs e)
    {
        if (channelClient is null || ChannelGrid.SelectedItem is not ServerNotificationChannelResponse channel)
        {
            return;
        }

        try
        {
            var messages = await channelClient.ListChannelMessagesAsync(channel.ChannelId);
            NotificationGrid.ItemsSource = messages;
            StatusTextBlock.Text = $"{channel.Name} 채널 메시지 {messages.Count}건을 조회했습니다.";
        }
        catch (Exception exception)
        {
            StatusTextBlock.Text = BuildServerFailureMessage(exception);
        }
    }

    private async void UnreadOnlyCheckBox_Changed(object sender, RoutedEventArgs e)
    {
        await RefreshAsync();
    }

    private async void MarkSelectedReadButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureServerConnected())
        {
            return;
        }

        var messageId = NotificationGrid.SelectedItem switch
        {
            ServerUserNotificationResponse notification => notification.MessageId,
            ServerChannelMessageResponse message => message.MessageId,
            _ => null
        };
        if (string.IsNullOrWhiteSpace(messageId))
        {
            StatusTextBlock.Text = "읽음 처리할 메시지를 선택하세요.";
            return;
        }

        try
        {
            await channelClient!.MarkNotificationReadAsync(messageId);
            StatusTextBlock.Text = "선택한 채널 메시지를 읽음 처리했습니다.";
            await RefreshAsync();
        }
        catch (Exception exception)
        {
            StatusTextBlock.Text = BuildServerFailureMessage(exception);
        }
    }

    private async void ReadReceiptButton_Click(object sender, RoutedEventArgs e)
    {
        await UpdateMyReceiptAsync("READ", "읽음 처리");
    }

    private async void AckReceiptButton_Click(object sender, RoutedEventArgs e)
    {
        await UpdateMyReceiptAsync("ACKNOWLEDGED", "확인");
    }

    private async void HoldReceiptButton_Click(object sender, RoutedEventArgs e)
    {
        await UpdateMyReceiptAsync("UNREAD", "보류");
    }

    private async void FollowUpReceiptButton_Click(object sender, RoutedEventArgs e)
    {
        await UpdateMyReceiptAsync("FOLLOW_UP_REQUIRED", "후속 필요");
    }

    private async Task UpdateMyReceiptAsync(string status, string label)
    {
        if (!EnsureServerConnected())
        {
            return;
        }

        if (HandoverGrid.SelectedItem is not ServerHandoverResponse handover)
        {
            StatusTextBlock.Text = "상태를 바꿀 인수인계를 선택하세요.";
            return;
        }

        var receipt = handover.Receipts.FirstOrDefault(item =>
            string.Equals(item.RecipientId, currentUserId, StringComparison.OrdinalIgnoreCase));
        if (receipt is null)
        {
            StatusTextBlock.Text = "현재 사용자의 인수인계 수신자 항목이 없습니다.";
            return;
        }

        try
        {
            var updated = await channelClient!.UpdateHandoverReceiptAsync(
                handover.HandoverId,
                receipt.ReceiptId,
                new ServerHandoverReceiptUpdateRequest
                {
                    ReceiptStatus = status,
                    Note = $"{label}: Windows 채널 수신함"
                });
            ReplaceSelectedHandover(updated);
            StatusTextBlock.Text =
                $"인수인계를 {label}(으)로 저장했습니다. 수신 확인 기록은 서버에 보존됩니다. " +
                "다음: 후속 조치가 필요하면 아래의 '후속 코멘트 저장'을 선택하세요.";
        }
        catch (Exception exception)
        {
            StatusTextBlock.Text = BuildServerFailureMessage(exception);
        }
    }

    private void CopySourceButton_Click(object sender, RoutedEventArgs e)
    {
        var text = NotificationGrid.SelectedItem switch
        {
            ServerUserNotificationResponse notification => notification.SourceLinkText,
            ServerChannelMessageResponse message => message.SourceLinkText,
            _ => HandoverGrid.SelectedItem is ServerHandoverResponse handover ? handover.SourceLinkText : null
        };
        if (string.IsNullOrWhiteSpace(text))
        {
            StatusTextBlock.Text = "복사할 원천 링크를 선택하세요.";
            return;
        }

        Clipboard.SetText(text);
        StatusTextBlock.Text = "원천 정보를 클립보드에 복사했습니다.";
    }

    private async void FollowUpFieldCommentButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureServerConnected())
        {
            return;
        }

        if (HandoverGrid.SelectedItem is not ServerHandoverResponse handover)
        {
            StatusTextBlock.Text = "후속 FieldComment를 만들 인수인계를 선택하세요.";
            return;
        }

        try
        {
            var result = await channelClient!.CreateHandoverFollowUpWithStatusAsync(
                handover,
                $"Windows 채널 수신함에서 후속 확인이 필요하다고 기록했습니다. 제목: {handover.Title}",
                currentUserId);
            StatusTextBlock.Text = result.ChannelMessagePublished
                ? "후속 현장 코멘트와 채널 알림을 저장했습니다. 원천 인수인계와 처리 기록은 서버에 보존됩니다. 다음: 코멘트 검토에서 후속 조치를 확인하세요."
                : "후속 현장 코멘트는 저장했지만 채널 알림은 보내지 못했습니다. 원천 인수인계와 코멘트는 서버에 보존됩니다. 다음: 같은 버튼을 다시 눌러 알림만 복구하세요. 코멘트는 중복 생성되지 않습니다.";
        }
        catch (Exception exception)
        {
            StatusTextBlock.Text = BuildServerFailureMessage(exception);
        }
    }

    private void CloseButton_Click(object sender, RoutedEventArgs e)
    {
        Close();
    }

    private void ReplaceSelectedHandover(ServerHandoverResponse updated)
    {
        if (HandoverGrid.ItemsSource is not IEnumerable<ServerHandoverResponse> current)
        {
            return;
        }

        var handovers = current
            .Select(item => item.HandoverId == updated.HandoverId ? updated : item)
            .ToList();
        HandoverGrid.ItemsSource = handovers;
        HandoverGrid.SelectedItem = handovers.First(item => item.HandoverId == updated.HandoverId);
    }

    private bool EnsureServerConnected()
    {
        if (channelClient is not null)
        {
            return true;
        }

        StatusTextBlock.Text = WorkflowFailureGuidance.Format(
            "서버 연결이 없어 채널 작업을 시작하지 못했습니다.",
            "로컬 데이터와 동기화 큐",
            "현재 사용자",
            "서버 주소와 로그인을 확인한 뒤 다시 시도하세요.");
        ChannelGrid.ItemsSource = Array.Empty<ServerNotificationChannelResponse>();
        NotificationGrid.ItemsSource = Array.Empty<ServerUserNotificationResponse>();
        HandoverGrid.ItemsSource = Array.Empty<ServerHandoverResponse>();
        return false;
    }

    private static string BuildServerFailureMessage(Exception exception)
    {
        return WorkflowFailureGuidance.FromServerException(
            exception,
            "채널 작업 결과를 확인하지 못했습니다.",
            "기존 원천, FieldComment와 수신 확인 기록",
            "네트워크를 확인하고 목록을 새로고침한 뒤 다시 시도하세요.");
    }
}
