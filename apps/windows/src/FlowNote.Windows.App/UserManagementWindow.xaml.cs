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
    private bool isAddingUser;

    public UserManagementWindow(UserManagementService users, string actorName)
    {
        InitializeComponent();
        this.users = users;
        this.actorName = actorName;
        DataContext = workspace;
        RoleComboBox.ItemsSource = RolePermissionPolicy.UserRoleOptions;
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
        RefreshUsers(isAddingUser ? null : SelectedUser()?.UserId);
        StatusTextBlock.Text = "사용자 목록을 새로고침했습니다.";
    }

    private void UserGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (UserGrid.SelectedItem is not null)
        {
            isAddingUser = false;
        }

        LoadSelectedUser();
    }

    private void NewUserButton_Click(object sender, RoutedEventArgs e)
    {
        StartNewUser();
    }

    private void ClearPasswordButton_Click(object sender, RoutedEventArgs e)
    {
        if (isAddingUser)
        {
            StartNewUser();
            StatusTextBlock.Text = "새 사용자 입력을 초기화했습니다.";
            return;
        }

        LoadSelectedUser();
        StatusTextBlock.Text = "선택한 사용자 정보를 다시 불러왔습니다.";
    }

    private void SaveButton_Click(object sender, RoutedEventArgs e)
    {
        var selectedRole = RoleComboBox.SelectedValue?.ToString();
        if (string.IsNullOrWhiteSpace(selectedRole))
        {
            StatusTextBlock.Text = "권한을 선택하세요.";
            return;
        }

        var newPassword = NewPasswordBox.Password;
        var confirmPassword = ConfirmPasswordBox.Password;
        if (isAddingUser && string.IsNullOrWhiteSpace(newPassword))
        {
            StatusTextBlock.Text = "새 사용자의 비밀번호를 입력하세요.";
            return;
        }

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
            var updated = isAddingUser
                ? users.CreateUser(
                    LoginIdTextBox.Text,
                    DisplayNameTextBox.Text,
                    selectedRole,
                    newPassword,
                    actorName)
                : UpdateSelectedUser(selectedRole, newPassword);
            isAddingUser = false;
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
        else if (!isAddingUser && UserGrid.SelectedItem is null && workspace.Users.Count > 0)
        {
            UserGrid.SelectedIndex = 0;
        }

        LoadSelectedUser();
    }

    private void LoadSelectedUser()
    {
        var selected = SelectedUser();
        LoginIdTextBox.IsReadOnly = true;
        SaveButton.Content = "저장";
        UserIdTextBox.Text = selected?.UserId ?? string.Empty;
        LoginIdTextBox.Text = selected?.LoginId ?? string.Empty;
        DisplayNameTextBox.Text = selected?.DisplayName ?? string.Empty;
        RoleComboBox.SelectedValue = selected?.Role ?? "team-member";
        NewPasswordBox.Clear();
        ConfirmPasswordBox.Clear();
    }

    private void StartNewUser()
    {
        isAddingUser = true;
        UserGrid.SelectedItem = null;
        UserIdTextBox.Text = "자동 생성";
        LoginIdTextBox.IsReadOnly = false;
        LoginIdTextBox.Text = string.Empty;
        DisplayNameTextBox.Text = string.Empty;
        RoleComboBox.SelectedValue = "team-member";
        NewPasswordBox.Clear();
        ConfirmPasswordBox.Clear();
        SaveButton.Content = "추가";
        LoginIdTextBox.Focus();
        StatusTextBlock.Text = "새 사용자 정보를 입력하세요.";
    }

    private UserAccountRecord UpdateSelectedUser(string selectedRole, string newPassword)
    {
        var selected = SelectedUser();
        if (selected is null)
        {
            throw new InvalidOperationException("수정할 사용자를 선택하세요.");
        }

        return users.UpdateUserProfile(
            selected.UserId,
            DisplayNameTextBox.Text,
            selectedRole,
            string.IsNullOrWhiteSpace(newPassword) ? null : newPassword,
            actorName);
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
