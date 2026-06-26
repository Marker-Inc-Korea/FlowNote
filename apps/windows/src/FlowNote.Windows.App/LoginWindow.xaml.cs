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
            var client = new FlowNoteServerAuthClient(httpClient);
            var response = await client.TryLoginAsync(loginId, password);
            return response?.ToLoginResult();
        }
        catch
        {
            return null;
        }
    }
}
