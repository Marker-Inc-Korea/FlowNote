using System.Windows;
using System.Windows.Controls;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.App;

public partial class HandoverStatusWindow : Window
{
    private readonly FlowNoteServerChannelClient? channelClient;
    private readonly string currentUserId;

    public HandoverStatusWindow(FlowNoteServerChannelClient? channelClient, string currentUserId)
    {
        InitializeComponent();
        this.channelClient = channelClient;
        this.currentUserId = currentUserId;
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
            var handovers = await channelClient!.ListHandoversAsync(200);
            HandoverGrid.ItemsSource = handovers;
            ReceiptGrid.ItemsSource = Array.Empty<ServerHandoverReceiptResponse>();
            StatusTextBlock.Text = $"인수인계 {handovers.Count}건을 조회했습니다.";
        }
        catch (Exception exception)
        {
            StatusTextBlock.Text = BuildServerFailureMessage(exception);
        }
    }

    private void HandoverGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (HandoverGrid.SelectedItem is not ServerHandoverResponse handover)
        {
            ReceiptGrid.ItemsSource = Array.Empty<ServerHandoverReceiptResponse>();
            return;
        }

        ReceiptGrid.ItemsSource = handover.Receipts;
        StatusTextBlock.Text = $"{handover.Title}: 수신자 {handover.Receipts.Count}명의 상태를 표시합니다.";
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

        if (HandoverGrid.SelectedItem is not ServerHandoverResponse handover ||
            ReceiptGrid.SelectedItem is not ServerHandoverReceiptResponse receipt)
        {
            StatusTextBlock.Text = "상태를 변경할 인수인계와 수신자를 선택하세요.";
            return;
        }

        try
        {
            var updated = await channelClient!.UpdateHandoverReceiptAsync(
                handover.HandoverId,
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

        if (HandoverGrid.SelectedItem is not ServerHandoverResponse handover)
        {
            StatusTextBlock.Text = "후속 FieldComment를 만들 인수인계를 선택하세요.";
            return;
        }

        var content = Clean(ReceiptNoteTextBox.Text)
            ?? $"Windows 확인 현황에서 후속 FieldComment를 작성했습니다. 제목: {handover.Title}";
        try
        {
            var fieldComment = await channelClient!.CreateHandoverFollowUpFieldCommentAsync(
                handover,
                content,
                currentUserId);
            StatusTextBlock.Text = $"후속 FieldComment를 만들었습니다. 원천 인수인계: {handover.HandoverId}, FieldComment: {fieldComment.CommentId}";
        }
        catch (Exception exception)
        {
            StatusTextBlock.Text = BuildServerFailureMessage(exception);
        }
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

        StatusTextBlock.Text = "서버에 연결되어 있지 않습니다. 로컬 데이터와 동기화 큐는 삭제되지 않습니다. 서버 주소와 로그인을 확인한 뒤 다시 시도하세요.";
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
        var prefix = exception is FlowNoteServerAuthenticationException
            ? "서버 인증이 만료되었습니다."
            : "서버 인수인계 확인 현황을 처리하지 못했습니다.";
        return $"{prefix} 로컬 데이터와 동기화 큐는 삭제되지 않습니다. {exception.Message}";
    }
}
