using System.Windows;
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
        ServerTargetTextBlock.Text = BuildServerTargetMessage();
    }

    private async void SignInButton_Click(object sender, RoutedEventArgs e)
    {
        ErrorTextBlock.Text = string.Empty;

        var loginId = LoginIdTextBox.Text.Trim();
        var password = PasswordBox.Password;
        var configuredServer = Environment.GetEnvironmentVariable(
            FlowNoteServerApiEnvironment.ApiBaseUrlEnvironmentVariable);
        using var httpClient = FlowNoteServerApiEnvironment.CreateHttpClientFromEnvironment(TimeSpan.FromSeconds(5));
        if (!string.IsNullOrWhiteSpace(configuredServer) && httpClient is null)
        {
            ErrorTextBlock.Text =
                ServerConnectionGuidance.InvalidServerAddressMessage;
            return;
        }

        var auth = new ServerAwareAuthService(services.Auth, httpClient);
        var result = await auth.LoginAsync(loginId, password);

        if (!result.Success)
        {
            ErrorTextBlock.Text = result.FailureReason;
            return;
        }

        if (result.MustChangePassword &&
            httpClient is not null &&
            !string.IsNullOrWhiteSpace(result.AccessToken))
        {
            var passwordChangeWindow = new PasswordChangeWindow(httpClient, result.AccessToken, password)
            {
                Owner = this
            };
            if (passwordChangeWindow.ShowDialog() == true)
            {
                PasswordBox.Clear();
                ErrorTextBlock.Text = "비밀번호를 변경했습니다. 새 비밀번호로 다시 로그인하세요.";
            }
            return;
        }

        var mainWindow = new MainWindow(services, result);
        mainWindow.Show();
        Close();
    }

    private static string BuildServerTargetMessage()
    {
        var configuredServer = Environment.GetEnvironmentVariable(
            FlowNoteServerApiEnvironment.ApiBaseUrlEnvironmentVariable);
        if (string.IsNullOrWhiteSpace(configuredServer))
        {
            return "서버 주소 미설정: 승인된 로컬 운영 계정으로만 로그인합니다.";
        }

        var normalized = configuredServer.EndsWith('/')
            ? configuredServer
            : $"{configuredServer}/";
        if (!Uri.TryCreate(normalized, UriKind.Absolute, out var uri))
        {
            return "서버 주소 설정 오류: 현장 관리자에게 FLOWNOTE_API_BASE_URL 확인을 요청하세요.";
        }

        var port = uri.IsDefaultPort ? string.Empty : $":{uri.Port}";
        return $"서버 로그인 대상: {uri.Scheme}://{uri.IdnHost}{port}";
    }
}
