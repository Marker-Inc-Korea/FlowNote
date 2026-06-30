using System.Windows;
using System.Net;
using System.Net.Http;
using System.Net.Http.Json;
using FlowNote.Windows.Core.Auth;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Storage;

namespace FlowNote.Windows.App;

public partial class LoginWindow : Window
{
    private readonly FlowNoteLocalServices services;

    public LoginWindow()
    {
        InitializeComponent();
        services = new FlowNoteLocalServices(FlowNoteLocalDatabase.DefaultDatabasePath);
    }

    private async void SignInButton_Click(object sender, RoutedEventArgs e)
    {
        ErrorTextBlock.Text = string.Empty;

        var loginId = LoginIdTextBox.Text.Trim();
        var password = PasswordBox.Password;
        var result = await TryServerLoginAsync(loginId, password)
            ?? services.Auth.Login(loginId, password);

        if (!result.Success)
        {
            ErrorTextBlock.Text = result.FailureReason;
            return;
        }

        var mainWindow = new MainWindow(services, result);
        mainWindow.Show();
        Close();
    }

    private static async Task<LoginResult?> TryServerLoginAsync(string loginId, string password)
    {
        using var httpClient = FlowNoteServerApiEnvironment.CreateHttpClientFromEnvironment(TimeSpan.FromSeconds(5));
        if (httpClient is null)
        {
            return null;
        }

        try
        {
            var response = await httpClient.PostAsJsonAsync(
                "api/v1/auth/login",
                new ServerLoginRequest(loginId, password));
            if (response.IsSuccessStatusCode)
            {
                var payload = await response.Content.ReadFromJsonAsync<ServerLoginResponse>();
                return payload?.ToLoginResult();
            }

            if (response.StatusCode == HttpStatusCode.Unauthorized)
            {
                return LoginResult.Failed("서버 로그인 ID 또는 비밀번호가 올바르지 않습니다.");
            }

            if (response.StatusCode == HttpStatusCode.Forbidden)
            {
                return LoginResult.Failed("서버 계정이 비활성 상태입니다. 관리자에게 문의하세요.");
            }

            return LoginResult.Failed("서버 로그인에 실패했습니다. 서버 상태를 확인한 뒤 다시 시도하세요.");
        }
        catch (HttpRequestException)
        {
            return null;
        }
        catch (TaskCanceledException)
        {
            return null;
        }
    }
}
