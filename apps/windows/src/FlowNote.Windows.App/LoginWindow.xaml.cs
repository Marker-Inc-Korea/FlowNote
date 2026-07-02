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
        using var httpClient = FlowNoteServerApiEnvironment.CreateHttpClientFromEnvironment(TimeSpan.FromSeconds(5));
        var auth = new ServerAwareAuthService(services.Auth, httpClient);
        var result = await auth.LoginAsync(loginId, password);

        if (!result.Success)
        {
            ErrorTextBlock.Text = result.FailureReason;
            return;
        }

        var mainWindow = new MainWindow(services, result);
        mainWindow.Show();
        Close();
    }
}
