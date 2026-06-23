using System.Windows;
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

    private void SignInButton_Click(object sender, RoutedEventArgs e)
    {
        var result = services.Auth.Login(LoginIdTextBox.Text.Trim(), PasswordBox.Password);
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
