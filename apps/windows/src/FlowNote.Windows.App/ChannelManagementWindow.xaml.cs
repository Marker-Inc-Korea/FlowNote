using System.Windows;
using System.Windows.Controls;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.App;

public partial class ChannelManagementWindow : Window
{
    private readonly FlowNoteServerChannelClient? channelClient;

    public ChannelManagementWindow(FlowNoteServerChannelClient? channelClient)
    {
        InitializeComponent();
        this.channelClient = channelClient;
        Loaded += ChannelManagementWindow_Loaded;
    }

    private async void ChannelManagementWindow_Loaded(object sender, RoutedEventArgs e)
    {
        await RefreshChannelsAsync();
    }

    private async void RefreshButton_Click(object sender, RoutedEventArgs e)
    {
        await RefreshChannelsAsync();
    }

    private async Task RefreshChannelsAsync()
    {
        if (!EnsureServerConnected())
        {
            return;
        }

        try
        {
            var channels = await channelClient!.ListChannelsAsync(status: "ACTIVE");
            ChannelGrid.ItemsSource = channels;
            StatusTextBlock.Text = $"관리 가능한 채널 {channels.Count}개를 조회했습니다.";
        }
        catch (Exception exception)
        {
            StatusTextBlock.Text = BuildServerFailureMessage(exception);
        }
    }

    private async void ChannelGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        await RefreshMembersAsync();
    }

    private async Task RefreshMembersAsync()
    {
        if (channelClient is null || ChannelGrid.SelectedItem is not ServerNotificationChannelResponse channel)
        {
            MemberGrid.ItemsSource = Array.Empty<ServerChannelMemberResponse>();
            return;
        }

        try
        {
            var members = await channelClient.ListChannelMembersAsync(channel.ChannelId);
            MemberGrid.ItemsSource = members;
            StatusTextBlock.Text = $"{channel.Name} 채널 멤버 {members.Count}명을 조회했습니다.";
        }
        catch (Exception exception)
        {
            StatusTextBlock.Text = BuildServerFailureMessage(exception);
        }
    }

    private async void CreateChannelButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureServerConnected())
        {
            return;
        }

        var channelName = ChannelNameTextBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(channelName))
        {
            StatusTextBlock.Text = "채널 이름을 입력하세요.";
            return;
        }

        try
        {
            var channelType = (ChannelTypeComboBox.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "LINE";
            var sourceType = channelType == "HANDOVER" ? "HANDOVER" : "WORK_RECORD";
            var created = await channelClient!.CreateChannelAsync(
                new ServerNotificationChannelCreateRequest
                {
                    Name = channelName,
                    Description = Clean(ChannelDescriptionTextBox.Text),
                    ChannelType = channelType,
                    SourceType = sourceType,
                    SourceId = Clean(ChannelSourceIdTextBox.Text)
                });
            StatusTextBlock.Text = $"채널을 만들었습니다: {created.Name}";
            ChannelNameTextBox.Clear();
            ChannelDescriptionTextBox.Clear();
            ChannelSourceIdTextBox.Clear();
            await RefreshChannelsAsync();
        }
        catch (Exception exception)
        {
            StatusTextBlock.Text = BuildServerFailureMessage(exception);
        }
    }

    private async void AddMemberButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureServerConnected())
        {
            return;
        }

        if (ChannelGrid.SelectedItem is not ServerNotificationChannelResponse channel)
        {
            StatusTextBlock.Text = "멤버를 추가할 채널을 선택하세요.";
            return;
        }

        var userId = MemberUserIdTextBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(userId))
        {
            StatusTextBlock.Text = "추가할 사용자 ID를 입력하세요.";
            return;
        }

        try
        {
            var memberRole = (MemberRoleComboBox.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "MEMBER";
            await channelClient!.UpsertChannelMemberAsync(
                channel.ChannelId,
                new ServerChannelMemberUpsertRequest
                {
                    UserId = userId,
                    MemberRole = memberRole
                });
            StatusTextBlock.Text = $"{userId} 사용자를 채널 멤버로 반영했습니다.";
            MemberUserIdTextBox.Clear();
            await RefreshMembersAsync();
        }
        catch (Exception exception)
        {
            StatusTextBlock.Text = BuildServerFailureMessage(exception);
        }
    }

    private async void RemoveMemberButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureServerConnected())
        {
            return;
        }

        if (ChannelGrid.SelectedItem is not ServerNotificationChannelResponse channel ||
            MemberGrid.SelectedItem is not ServerChannelMemberResponse member)
        {
            StatusTextBlock.Text = "제외할 채널 멤버를 선택하세요.";
            return;
        }

        try
        {
            await channelClient!.UpdateChannelMemberAsync(
                channel.ChannelId,
                member.MemberId,
                new ServerChannelMemberUpdateRequest { Status = "REMOVED" });
            StatusTextBlock.Text = $"{member.UserId} 사용자를 채널에서 제외했습니다.";
            await RefreshMembersAsync();
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
        MemberGrid.ItemsSource = Array.Empty<ServerChannelMemberResponse>();
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
            : "서버 채널 관리 정보를 저장하지 못했습니다.";
        return $"{prefix} 로컬 데이터와 동기화 큐는 삭제되지 않습니다. {exception.Message}";
    }
}
