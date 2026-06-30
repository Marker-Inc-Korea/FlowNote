using System.Collections.ObjectModel;
using System.Windows;
using System.Windows.Controls;
using FlowNote.Windows.Core.Auth;

namespace FlowNote.Windows.App;

public partial class UserManagementWindow : Window
{
    private readonly UserManagementService users;
    private readonly string actorName;
    private readonly UserManagementWorkspace workspace = new();

    public UserManagementWindow(UserManagementService users, string actorName)
    {
        InitializeComponent();
        this.users = users;
        this.actorName = actorName;
        DataContext = workspace;
        Loaded += UserManagementWindow_Loaded;
    }

    public string? UpdatedUserId { get; private set; }

    public string? UpdatedDisplayName { get; private set; }

    private void UserManagementWindow_Loaded(object sender, RoutedEventArgs e)
    {
        RefreshUsers();
    }

    private void RefreshButton_Click(object sender, RoutedEventArgs e)
    {
        RefreshUsers(SelectedUser()?.UserId);
        StatusTextBlock.Text = "사용자 목록을 새로고침했습니다.";
    }

    private void UserGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        LoadSelectedUser();
    }

    private void ClearPasswordButton_Click(object sender, RoutedEventArgs e)
    {
        NewPasswordBox.Clear();
        ConfirmPasswordBox.Clear();
        StatusTextBlock.Text = "비밀번호 입력을 비웠습니다.";
    }

    private void SaveButton_Click(object sender, RoutedEventArgs e)
    {
        var selected = SelectedUser();
        if (selected is null)
        {
            StatusTextBlock.Text = "수정할 사용자를 선택하세요.";
            return;
        }

        var newPassword = NewPasswordBox.Password;
        var confirmPassword = ConfirmPasswordBox.Password;
        if (!string.IsNullOrWhiteSpace(newPassword) || !string.IsNullOrWhiteSpace(confirmPassword))
        {
            if (!string.Equals(newPassword, confirmPassword, StringComparison.Ordinal))
            {
                StatusTextBlock.Text = "새 비밀번호와 확인 값이 일치하지 않습니다.";
                return;
            }
        }

        try
        {
            var updated = users.UpdateUserProfile(
                selected.UserId,
                DisplayNameTextBox.Text,
                string.IsNullOrWhiteSpace(newPassword) ? null : newPassword,
                actorName);
            NewPasswordBox.Clear();
            ConfirmPasswordBox.Clear();
            RefreshUsers(updated.UserId);
            UpdatedUserId = updated.UserId;
            UpdatedDisplayName = updated.DisplayName;
            StatusTextBlock.Text = $"{updated.DisplayName} 사용자 정보를 저장했습니다.";
        }
        catch (Exception exception) when (exception is ArgumentException or InvalidOperationException)
        {
            StatusTextBlock.Text = exception.Message;
        }
    }

    private void RefreshUsers(string? selectUserId = null)
    {
        workspace.Users.Clear();
        foreach (var user in users.ListUsers())
        {
            workspace.Users.Add(user);
        }

        if (!string.IsNullOrWhiteSpace(selectUserId))
        {
            UserGrid.SelectedItem = workspace.Users.FirstOrDefault(user => user.UserId == selectUserId);
        }
        else if (UserGrid.SelectedItem is null && workspace.Users.Count > 0)
        {
            UserGrid.SelectedIndex = 0;
        }

        LoadSelectedUser();
    }

    private void LoadSelectedUser()
    {
        var selected = SelectedUser();
        UserIdTextBox.Text = selected?.UserId ?? string.Empty;
        LoginIdTextBox.Text = selected?.LoginId ?? string.Empty;
        DisplayNameTextBox.Text = selected?.DisplayName ?? string.Empty;
        RoleTextBox.Text = selected?.RoleLabel ?? string.Empty;
        NewPasswordBox.Clear();
        ConfirmPasswordBox.Clear();
    }

    private UserAccountRecord? SelectedUser()
    {
        return UserGrid.SelectedItem as UserAccountRecord;
    }

    private sealed class UserManagementWorkspace
    {
        public ObservableCollection<UserAccountRecord> Users { get; } = [];
    }
}
