using System.Net.Http.Headers;
using System.Net.Http;
using System.Windows;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.App;

public partial class PasswordChangeWindow : Window
{
    private readonly HttpClient httpClient;
    private readonly string currentPassword;

    public PasswordChangeWindow(HttpClient httpClient, string accessToken, string currentPassword)
    {
        InitializeComponent();
        this.httpClient = httpClient;
        this.currentPassword = currentPassword;
        httpClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", accessToken);
    }

    private async void ChangeButton_Click(object sender, RoutedEventArgs e)
    {
        ErrorTextBlock.Text = string.Empty;
        if (NewPasswordBox.Password.Length < 8)
        {
            ErrorTextBlock.Text = "새 비밀번호는 8자 이상이어야 합니다.";
            return;
        }
        if (!string.Equals(NewPasswordBox.Password, ConfirmPasswordBox.Password, StringComparison.Ordinal))
        {
            ErrorTextBlock.Text = "새 비밀번호와 확인 값이 일치하지 않습니다.";
            return;
        }

        ChangeButton.IsEnabled = false;
        try
        {
            var changed = await new FlowNoteServerAuthClient(httpClient).TryChangePasswordAsync(
                currentPassword,
                NewPasswordBox.Password);
            if (!changed)
            {
                ErrorTextBlock.Text = "비밀번호를 변경하지 못했습니다. 현재 비밀번호와 정책을 확인하세요.";
                return;
            }
            DialogResult = true;
        }
        catch (HttpRequestException)
        {
            ErrorTextBlock.Text = "서버에 연결할 수 없습니다. 연결 상태를 확인하세요.";
        }
        finally
        {
            ChangeButton.IsEnabled = true;
        }
    }
}
