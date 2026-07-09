using System.Windows;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.App;

public partial class ChannelInboxWindow : Window
{
    private readonly FlowNoteServerChannelClient? channelClient;
    private readonly string currentUserId;

    public ChannelInboxWindow(FlowNoteServerChannelClient? channelClient, string currentUserId)
    {
        InitializeComponent();
        this.channelClient = channelClient;
        this.currentUserId = currentUserId;
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
            await channelClient!.UpdateHandoverReceiptAsync(
                handover.HandoverId,
                receipt.ReceiptId,
                new ServerHandoverReceiptUpdateRequest
                {
                    ReceiptStatus = status,
                    Note = $"{label}: Windows 채널 수신함"
                });
            StatusTextBlock.Text = $"인수인계 수신 상태를 {label}(으)로 변경했습니다.";
            await RefreshAsync();
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
            var fieldComment = await channelClient!.CreateHandoverFollowUpFieldCommentAsync(
                handover,
                $"Windows 채널 수신함에서 후속 확인이 필요하다고 기록했습니다. 제목: {handover.Title}",
                currentUserId);
            StatusTextBlock.Text = $"후속 FieldComment를 만들었습니다. 원천 인수인계: {handover.HandoverId}, FieldComment: {fieldComment.CommentId}";
            await RefreshAsync();
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

    private bool EnsureServerConnected()
    {
        if (channelClient is not null)
        {
            return true;
        }

        StatusTextBlock.Text = "서버에 연결되어 있지 않습니다. 로컬 데이터와 동기화 큐는 삭제되지 않습니다. 서버 주소와 로그인을 확인한 뒤 다시 시도하세요.";
        ChannelGrid.ItemsSource = Array.Empty<ServerNotificationChannelResponse>();
        NotificationGrid.ItemsSource = Array.Empty<ServerUserNotificationResponse>();
        HandoverGrid.ItemsSource = Array.Empty<ServerHandoverResponse>();
        return false;
    }

    private static string BuildServerFailureMessage(Exception exception)
    {
        var prefix = exception is FlowNoteServerAuthenticationException
            ? "서버 인증이 만료되었습니다."
            : "서버 채널 정보를 불러오지 못했습니다.";
        return $"{prefix} 로컬 데이터와 동기화 큐는 삭제되지 않습니다. {exception.Message}";
    }
}
