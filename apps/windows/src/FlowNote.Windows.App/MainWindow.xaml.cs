using System.Net.Http;
using System.Net.Http.Headers;
using System.Windows;
using System.Windows.Threading;
using FlowNote.Windows.Core.Auth;
using FlowNote.Windows.Core.Explorer;
using FlowNote.Windows.Core.Notifications;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Storage;

namespace FlowNote.Windows.App;

public partial class MainWindow : Window
{
    private readonly FlowNoteLocalServices services;
    private readonly LoginResult currentUser;
    private readonly HttpClient? serverHttpClient;
    private readonly FlowNoteServerDocumentClient? serverDocumentClient;
    private readonly FlowNoteServerChannelClient? serverChannelClient;
    private readonly FlowNoteServerTerminalDeviceClient? serverTerminalDeviceClient;
    private readonly FlowNoteServerAccountClient? serverAccountClient;
    private readonly FlowNoteServerAIOperationsClient? serverAIOperationsClient;
    private readonly FlowNoteServerAuditClient? serverAuditClient;
    private readonly bool canRegisterDocuments;
    private readonly bool canGovernDocuments;
    private readonly bool canManageFileWatch;
    private readonly bool canWriteReports;
    private readonly bool canManageUsers;
    private readonly ExplorerWorkspace workspace = new();
    private ExplorerFolder? selectedFolder;
    private string currentDisplayName;
    private readonly DispatcherTimer notificationPollingTimer = new()
    {
        Interval = TimeSpan.FromSeconds(15)
    };
    private bool notificationPolling;
    private readonly string? notificationServerScope;
    private readonly string? notificationUserId;
    private int notificationPollFailures;

    public MainWindow(FlowNoteLocalServices services, LoginResult currentUser)
    {
        InitializeComponent();
        this.services = services;
        this.currentUser = currentUser;
        canRegisterDocuments =
            RolePermissionPolicy.CanRegisterDocuments(currentUser.Role);
        canGovernDocuments =
            RolePermissionPolicy.CanGovernDocuments(currentUser.Role);
        canManageFileWatch =
            RolePermissionPolicy.CanManageFileWatch(currentUser.Role);
        canWriteReports =
            RolePermissionPolicy.CanWriteReports(currentUser.Role);
        canManageUsers =
            RolePermissionPolicy.CanManageUsers(currentUser.Role);
        currentDisplayName =
            currentUser.DisplayName ?? currentUser.LoginId ?? "admin";
        (
            serverDocumentClient,
            serverChannelClient,
            serverTerminalDeviceClient,
            serverAccountClient,
            serverAIOperationsClient,
            serverAuditClient,
            serverHttpClient) = CreateServerClients(currentUser);
        notificationServerScope = serverHttpClient?.BaseAddress is null
            ? null
            : ServerNotificationCursorService.NormalizeServerScope(
                serverHttpClient.BaseAddress);
        notificationUserId = string.IsNullOrWhiteSpace(currentUser.UserId)
            ? null
            : currentUser.UserId;
        SignedInUserTextBlock.Text =
            $"{currentDisplayName} ({FormatUserRole(currentUser.Role)})";
        DataContext = workspace;
        ApplyRolePermissions();
        NotificationCursorResetButton.IsEnabled =
            serverChannelClient is not null &&
            IsNotificationCursorAdministrator(currentUser.Role);
        Loaded += MainWindow_Loaded;
        notificationPollingTimer.Tick += NotificationPollingTimer_Tick;
        RefreshWorkspace(
            "로컬 작업 공간을 열었습니다.",
            services.Folders
                .GetDefaultSystemFolder(FlowNoteLocalDatabase.DocumentsFolderName)
                .Id);
        RefreshNotificationButton();
    }

    protected override void OnClosed(EventArgs e)
    {
        Loaded -= MainWindow_Loaded;
        notificationPollingTimer.Stop();
        notificationPollingTimer.Tick -= NotificationPollingTimer_Tick;
        services.FileWatch.Dispose();
        serverHttpClient?.Dispose();
        base.OnClosed(e);
    }

    private static (
        FlowNoteServerDocumentClient? DocumentClient,
        FlowNoteServerChannelClient? ChannelClient,
        FlowNoteServerTerminalDeviceClient? TerminalDeviceClient,
        FlowNoteServerAccountClient? AccountClient,
        FlowNoteServerAIOperationsClient? AIOperationsClient,
        FlowNoteServerAuditClient? AuditClient,
        HttpClient? HttpClient) CreateServerClients(LoginResult currentUser)
    {
        var httpClient =
            FlowNoteServerApiEnvironment.CreateHttpClientFromEnvironment();
        if (httpClient is null ||
            string.IsNullOrWhiteSpace(currentUser.AccessToken))
        {
            httpClient?.Dispose();
            return (null, null, null, null, null, null, null);
        }

        httpClient.DefaultRequestHeaders.Authorization =
            new AuthenticationHeaderValue(
                "Bearer",
                currentUser.AccessToken);
        return (
            new FlowNoteServerDocumentClient(httpClient),
            new FlowNoteServerChannelClient(httpClient),
            new FlowNoteServerTerminalDeviceClient(httpClient),
            new FlowNoteServerAccountClient(httpClient),
            new FlowNoteServerAIOperationsClient(httpClient),
            new FlowNoteServerAuditClient(httpClient),
            httpClient);
    }
}
