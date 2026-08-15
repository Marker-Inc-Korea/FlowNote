using System.Collections.ObjectModel;
using System.Net.Http;
using System.Windows;
using System.Windows.Controls;
using FlowNote.Windows.Core.Auth;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.App;

public partial class ServerUserManagementWindow : Window
{
    private readonly FlowNoteServerAccountClient client;
    private readonly string currentUserId;
    private readonly string currentRole;
    private readonly Workspace workspace = new();
    private bool adding;

    public ServerUserManagementWindow(
        FlowNoteServerAccountClient client,
        string currentUserId,
        string currentRole)
    {
        InitializeComponent();
        this.client = client;
        this.currentUserId = currentUserId;
        this.currentRole = currentRole;
        DataContext = workspace;
        RoleComboBox.ItemsSource = RolePermissionPolicy.UserRoleOptions.Where(option =>
            ServerAccountUiPolicy.CanManageSystemAdmin(currentRole) || option.Role != "system-admin");
        ModeTextBlock.Text = ServerAccountUiPolicy.ConnectedMessage;
        Loaded += async (_, _) => await RefreshAsync();
    }

    private async void RefreshButton_Click(object sender, RoutedEventArgs e) => await RefreshAsync();

    private async void AccountGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (AccountGrid.SelectedItem is ServerAccountRecord account)
        {
            adding = false;
            LoadAccount(account);
            await LoadSessionsAsync(account.UserId);
        }
    }

    private void NewAccountButton_Click(object sender, RoutedEventArgs e)
    {
        adding = true;
        AccountGrid.SelectedItem = null;
        UserIdTextBox.Text = "자동 생성";
        UsernameTextBox.IsReadOnly = false;
        UsernameTextBox.Clear();
        DisplayNameTextBox.Clear();
        RoleComboBox.SelectedValue = "team-member";
        StatusComboBox.SelectedValue = "ACTIVE";
        StatusComboBox.IsEnabled = false;
        TemporaryPasswordBox.Clear();
        ReasonTextBox.Clear();
        SaveButton.Content = "계정 생성";
        ResetPasswordButton.IsEnabled = false;
        RevokeSessionsButton.IsEnabled = false;
        SessionList.ItemsSource = null;
        StatusTextBlock.Text = "새 서버 계정과 임시 비밀번호, 발급 사유를 입력하세요.";
    }

    private async void SaveButton_Click(object sender, RoutedEventArgs e)
    {
        if (!ValidateReason() || RoleComboBox.SelectedValue is not string role)
        {
            return;
        }

        try
        {
            ServerAccountMutationResponse result;
            if (adding)
            {
                if (TemporaryPasswordBox.Password.Length < 8)
                {
                    StatusTextBlock.Text = "임시 비밀번호는 8자 이상 200자 이하여야 합니다.";
                    return;
                }
                result = await client.CreateAsync(new ServerAccountCreateRequest(
                    UsernameTextBox.Text.Trim(),
                    DisplayNameTextBox.Text.Trim(),
                    role,
                    TemporaryPasswordBox.Password,
                    ReasonTextBox.Text.Trim()));
            }
            else
            {
                var selected = SelectedAccount();
                if (selected is null || StatusComboBox.SelectedValue is not string accountStatus)
                {
                    StatusTextBlock.Text = "변경할 서버 계정을 선택하세요.";
                    return;
                }
                result = await client.UpdateAsync(selected.UserId, new ServerAccountUpdateRequest(
                    DisplayNameTextBox.Text.Trim(), role, accountStatus, ReasonTextBox.Text.Trim()));
            }
            TemporaryPasswordBox.Clear();
            adding = false;
            await RefreshAsync(result.Account.UserId);
            StatusTextBlock.Text = $"{result.Account.DisplayName} 서버 계정을 저장했습니다. 폐기된 세션: {result.SessionsRevoked}개";
        }
        catch (ServerAccountApiException exception)
        {
            ApplyApiError(exception);
        }
        catch (HttpRequestException)
        {
            ApplyDisconnectedState();
        }
    }

    private async void ResetPasswordButton_Click(object sender, RoutedEventArgs e)
    {
        var selected = SelectedAccount();
        if (selected is null || !ValidateReason() || TemporaryPasswordBox.Password.Length < 8)
        {
            StatusTextBlock.Text = selected is null
                ? "비밀번호를 재설정할 서버 계정을 선택하세요."
                : "8자 이상 200자 이하의 임시 비밀번호와 변경 사유를 입력하세요.";
            return;
        }
        try
        {
            var result = await client.ResetPasswordAsync(
                selected.UserId,
                new ServerPasswordResetRequest(TemporaryPasswordBox.Password, ReasonTextBox.Text.Trim()));
            TemporaryPasswordBox.Clear();
            await RefreshAsync(result.Account.UserId);
            StatusTextBlock.Text = $"임시 비밀번호로 재설정했습니다. 다음 로그인에서 변경이 강제됩니다. 폐기된 세션: {result.SessionsRevoked}개";
        }
        catch (ServerAccountApiException exception)
        {
            ApplyApiError(exception);
        }
        catch (HttpRequestException)
        {
            ApplyDisconnectedState();
        }
    }

    private async void RevokeSessionsButton_Click(object sender, RoutedEventArgs e)
    {
        var selected = SelectedAccount();
        if (selected is null || !ValidateReason())
        {
            StatusTextBlock.Text = "세션을 폐기할 계정과 변경 사유를 입력하세요.";
            return;
        }
        try
        {
            var count = await client.RevokeSessionsAsync(selected.UserId, ReasonTextBox.Text.Trim());
            await LoadSessionsAsync(selected.UserId);
            StatusTextBlock.Text = $"활성 세션 {count}개를 강제 폐기했습니다.";
        }
        catch (ServerAccountApiException exception)
        {
            ApplyApiError(exception);
        }
        catch (HttpRequestException)
        {
            ApplyDisconnectedState();
        }
    }

    private async Task RefreshAsync(string? selectUserId = null)
    {
        try
        {
            var accounts = await client.ListAsync();
            workspace.Accounts.Clear();
            foreach (var account in accounts)
            {
                workspace.Accounts.Add(account);
            }
            AccountGrid.SelectedItem = workspace.Accounts.FirstOrDefault(account => account.UserId == selectUserId)
                ?? workspace.Accounts.FirstOrDefault();
            SetButtonsEnabled(true);
            StatusTextBlock.Text = "서버 계정 목록을 불러왔습니다.";
        }
        catch (ServerAccountApiException exception)
        {
            ApplyApiError(exception);
        }
        catch (HttpRequestException)
        {
            ApplyDisconnectedState();
        }
    }

    private async Task LoadSessionsAsync(string userId)
    {
        try
        {
            SessionList.ItemsSource = await client.ListSessionsAsync(userId);
        }
        catch (ServerAccountApiException exception)
        {
            ApplyApiError(exception);
        }
        catch (HttpRequestException)
        {
            ApplyDisconnectedState();
        }
    }

    private void LoadAccount(ServerAccountRecord account)
    {
        UserIdTextBox.Text = account.UserId;
        UsernameTextBox.Text = account.Username;
        UsernameTextBox.IsReadOnly = true;
        DisplayNameTextBox.Text = account.DisplayName;
        RoleComboBox.SelectedValue = account.Role;
        StatusComboBox.SelectedValue = account.Status;
        StatusComboBox.IsEnabled = !string.Equals(account.UserId, currentUserId, StringComparison.Ordinal);
        TemporaryPasswordBox.Clear();
        ReasonTextBox.Clear();
        SaveButton.Content = "저장";
        ResetPasswordButton.IsEnabled = true;
        RevokeSessionsButton.IsEnabled = true;
    }

    private bool ValidateReason()
    {
        if (!string.IsNullOrWhiteSpace(ReasonTextBox.Text))
        {
            return true;
        }
        StatusTextBlock.Text = "변경 사유를 입력하세요.";
        return false;
    }

    private void ApplyApiError(ServerAccountApiException exception)
    {
        StatusTextBlock.Text = exception.Message;
        if (exception.StatusCode is System.Net.HttpStatusCode.Unauthorized or System.Net.HttpStatusCode.Forbidden)
        {
            SetButtonsEnabled(false);
        }
    }

    private void ApplyDisconnectedState()
    {
        ModeTextBlock.Text = "서버 연결이 끊어졌습니다. 로컬 계정 화면으로 자동 전환하지 않습니다.";
        StatusTextBlock.Text = "서버에 연결할 수 없습니다. 연결 상태를 확인한 뒤 다시 로그인하세요.";
        SetButtonsEnabled(false);
    }

    private void SetButtonsEnabled(bool enabled)
    {
        SaveButton.IsEnabled = enabled;
        ResetPasswordButton.IsEnabled = enabled && !adding && SelectedAccount() is not null;
        RevokeSessionsButton.IsEnabled = enabled && !adding && SelectedAccount() is not null;
    }

    private ServerAccountRecord? SelectedAccount() => AccountGrid.SelectedItem as ServerAccountRecord;

    private sealed class Workspace
    {
        public ObservableCollection<ServerAccountRecord> Accounts { get; } = [];
    }
}
