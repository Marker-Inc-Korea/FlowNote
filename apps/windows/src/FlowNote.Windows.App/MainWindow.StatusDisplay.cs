using System.Windows;
using System.Windows.Controls;
using FlowNote.Windows.Core.Auth;
using FlowNote.Windows.Core.Explorer;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.App;

public partial class MainWindow
{
    private async void MainWindow_Loaded(object sender, RoutedEventArgs e)
    {
        if (serverDocumentClient is null)
        {
            RefreshSyncState();
            return;
        }

        notificationPollingTimer.Start();
        await PollServerNotificationsAsync();

        var result = await services.ServerSync.RetryPendingAsync(
            serverDocumentClient,
            currentUser.UserId);
        if (result.Attempted > 0 || result.Skipped > 0)
        {
            workspace.StatusText = $"{workspace.StatusText}  {result.Message}";
        }

        RefreshSyncState();
    }

    private async void NotificationPollingTimer_Tick(object? sender, EventArgs e)
    {
        await PollServerNotificationsAsync();
    }

    private async Task PollServerNotificationsAsync()
    {
        if (serverChannelClient is null ||
            notificationServerScope is null ||
            notificationUserId is null ||
            notificationPolling)
        {
            return;
        }

        notificationPolling = true;
        try
        {
            var savedState = services.ServerNotificationCursors.Get(
                notificationServerScope,
                notificationUserId);
            if (serverDocumentClient is null)
            {
                return;
            }

            var manifest = await serverDocumentClient.GetSyncManifestAsync();
            var binding = services.ServerEpochGuard.Observe(
                notificationServerScope,
                manifest,
                savedState.LastSuccessCursor);
            if (binding.ReconciliationRequired)
            {
                notificationPollingTimer.Stop();
                workspace.StatusText =
                    $"서버 복구 경계가 감지되어 알림 확인과 자동 전송을 중지했습니다. {binding.BlockReason} " +
                    "로컬 기록과 동기화 큐는 보존됩니다. 이력 > 서버 재결합에서 관리자가 판정을 검토하고 승인하세요.";
                return;
            }

            var page = await serverChannelClient.PollMyNotificationsAsync(
                unreadOnly: false,
                limit: 100,
                afterId: savedState.LastSuccessCursor);
            var pageLastCursor = page.Items.Count == 0
                ? savedState.LastSuccessCursor
                : page.Items.Max(notification => notification.Cursor);
            var reachedServerCursor = page.Items.Count < 100 ||
                pageLastCursor >= page.ServerCursor;
            var result = services.ServerNotificationCursors.ProcessBatch(
                notificationServerScope,
                notificationUserId,
                page,
                reachedServerCursor);

            notificationPollFailures = 0;
            if (result.ResetRequired)
            {
                notificationPollingTimer.Stop();
                workspace.StatusText =
                    "서버 알림 위치가 이전 저장값보다 낮아 알림 확인을 중지했습니다. " +
                    "마지막 정상 위치는 보존됩니다. 서버 DB 복구 여부를 확인한 뒤 관리자가 '알림 위치 초기화'를 실행하세요.";
            }
            else if (!reachedServerCursor)
            {
                notificationPollingTimer.Interval = TimeSpan.FromMilliseconds(100);
                workspace.StatusText = savedState.InitialSyncCompleted
                    ? $"새 알림을 이어서 처리 중입니다. 진행 위치: {result.State.LastSuccessCursor}/{result.State.ObservedServerCursor}"
                    : $"이전 알림을 재확인 중입니다. 중복 알림을 새로 만들지 않습니다. " +
                      $"진행 위치: {result.State.LastSuccessCursor}/{result.State.ObservedServerCursor}";
            }
            else
            {
                notificationPollingTimer.Interval = TimeSpan.FromSeconds(15);
                if (!savedState.InitialSyncCompleted)
                {
                    workspace.StatusText =
                        $"이전 알림 재확인을 완료했습니다. 중복 없이 {result.State.LastSuccessCursor}번 다음부터 확인합니다.";
                }
                else if (result.ProcessedCount > 0)
                {
                    workspace.StatusText =
                        $"새 채널·인수인계 알림 {result.ProcessedCount}건이 도착했습니다.";
                }
            }
        }
        catch (FlowNoteServerAuthenticationException)
        {
            notificationPollingTimer.Stop();
            workspace.StatusText =
                "로그인이 만료되어 알림 확인을 멈췄습니다. 마지막 알림 위치와 로컬 기록은 보존됩니다. 다시 로그인하면 이어서 확인합니다.";
        }
        catch (Exception)
        {
            notificationPollFailures++;
            var seconds = Math.Min(
                120,
                15 * (1 << Math.Min(notificationPollFailures, 3)));
            notificationPollingTimer.Interval = TimeSpan.FromSeconds(seconds);
            workspace.StatusText =
                "서버 연결이 끊겨 알림 확인을 재시도합니다. 마지막 알림 위치와 로컬 기록은 보존되며 연결 복구 후 이어집니다.";
        }
        finally
        {
            notificationPolling = false;
            RefreshSyncState();
        }
    }

    private void NotificationCursorResetButton_Click(object sender, RoutedEventArgs e)
    {
        if (!IsNotificationCursorAdministrator(currentUser.Role) ||
            notificationServerScope is null ||
            notificationUserId is null)
        {
            workspace.StatusText =
                "알림 위치 초기화는 관리자/시스템 관리자 권한과 서버 연결이 필요합니다. 현장 관리자에게 로그인 ID와 업무명을 전달하세요.";
            return;
        }

        if (services.ServerEpochGuard.Get(notificationServerScope)
                ?.ReconciliationRequired == true)
        {
            workspace.StatusText =
                "서버 복구 경계 검토가 끝나지 않아 알림 위치만 따로 초기화할 수 없습니다. 기존 위치와 큐는 보존됩니다. 서버 재결합을 먼저 승인하세요.";
            return;
        }

        var confirmed = MessageBox.Show(
            "이 서버와 현재 사용자의 저장된 알림 위치를 0으로 초기화합니다.\n" +
            "다음 알림 확인에서 과거 알림을 재확인하지만 message_id 기준으로 중복 처리하지 않습니다. 계속하시겠습니까?",
            "알림 위치 초기화 관리자 확인",
            MessageBoxButton.YesNo,
            MessageBoxImage.Warning) == MessageBoxResult.Yes;
        if (!confirmed)
        {
            workspace.StatusText = "알림 위치 초기화를 취소했습니다. 기존 위치는 보존됩니다.";
            return;
        }

        services.ServerNotificationCursors.ResetAfterAdministratorConfirmation(
            notificationServerScope,
            notificationUserId,
            GetCurrentUserId(),
            currentUser.Role);
        notificationPollFailures = 0;
        notificationPollingTimer.Interval = TimeSpan.FromMilliseconds(100);
        notificationPollingTimer.Start();
        workspace.StatusText =
            "관리자 확인으로 알림 위치를 초기화했습니다. 과거 알림을 중복 없이 재확인합니다.";
    }

    private static bool IsNotificationCursorAdministrator(string? role) =>
        role is "admin" or "system-admin";

    private void ApplyRolePermissions()
    {
        const string contact =
            " 권한이 필요하면 현장 관리자에게 로그인 ID와 필요한 업무를 전달하세요.";
        const string noDocumentWritePermission =
            "문서 등록과 작업판 관리는 관리자/반장/조장 이상 권한에서 사용할 수 있습니다." +
            contact;
        const string noGovernancePermission =
            "문서 상태와 공개본 결정은 관리자/문서관리/부서관리 권한에서 사용할 수 있습니다." +
            contact;
        const string noReportWritePermission =
            "코멘트 검토와 보고서 작성은 관리자/문서관리/부서관리 권한에서 사용할 수 있습니다." +
            contact;

        NewFolderButton.IsEnabled = canRegisterDocuments;
        RegisterDocumentButton.IsEnabled = canRegisterDocuments;
        UploadFileButton.IsEnabled = canRegisterDocuments;
        WorkSequenceAdminButton.IsEnabled = canRegisterDocuments;
        ChannelManagementButton.IsEnabled = canRegisterDocuments;
        HandoverStatusButton.IsEnabled = canRegisterDocuments;
        FieldCommentReviewButton.IsEnabled = canWriteReports;
        ReportDraftButton.IsEnabled = canWriteReports;
        AISearchQualityButton.IsEnabled = canWriteReports;
        AIGroundTruthButton.IsEnabled = canWriteReports;
        AIOperationsButton.IsEnabled =
            RolePermissionPolicy.CanOperateAIOperations(currentUser.Role);
        ApplyDocumentStatusButton.IsEnabled = canGovernDocuments;
        PublishDocumentButton.IsEnabled = canGovernDocuments;
        DocumentStatusComboBox.IsEnabled = canGovernDocuments;
        FileListDropZone.AllowDrop = canRegisterDocuments;
        FileWatchButton.IsEnabled = canManageFileWatch;
        UserManagementButton.IsEnabled = canManageUsers;
        TerminalDeviceManagementButton.IsEnabled = canManageUsers;
        AdministrationActionsGroup.IsEnabled = canManageUsers;

        NewFolderButton.ToolTip = noDocumentWritePermission;
        RegisterDocumentButton.ToolTip = noDocumentWritePermission;
        UploadFileButton.ToolTip = noDocumentWritePermission;
        WorkSequenceAdminButton.ToolTip = noDocumentWritePermission;
        ChannelManagementButton.ToolTip =
            "채널 관리는 관리자/반장/조장 이상 권한에서 사용할 수 있습니다." +
            contact;
        HandoverStatusButton.ToolTip =
            "인수인계 확인 현황은 관리자/반장/조장 이상 권한에서 사용할 수 있습니다." +
            contact;
        ApplyDocumentStatusButton.ToolTip = noGovernancePermission;
        PublishDocumentButton.ToolTip = noGovernancePermission;
        DocumentStatusComboBox.ToolTip = noGovernancePermission;
        FieldCommentReviewButton.ToolTip = noReportWritePermission;
        ReportDraftButton.ToolTip = noReportWritePermission;
        AISearchQualityButton.ToolTip = noReportWritePermission;
        AIGroundTruthButton.ToolTip = noReportWritePermission;
        AIOperationsButton.ToolTip =
            "AI 운영은 시스템 관리자 권한에서만 사용할 수 있습니다." + contact;
        FileWatchButton.ToolTip =
            "파일 감시는 관리자/문서관리/부서관리 권한에서만 사용할 수 있습니다." +
            contact;
        UserManagementButton.ToolTip =
            "사용자 관리는 관리자/시스템 관리자 권한에서만 사용할 수 있습니다." +
            contact;
        TerminalDeviceManagementButton.ToolTip = UserManagementButton.ToolTip;
        AdministrationActionsGroup.ToolTip = UserManagementButton.ToolTip;
        NotificationCursorResetButton.ToolTip =
            "알림 위치 초기화는 관리자/시스템 관리자 권한과 서버 연결이 필요합니다." +
            contact;

        ConfigureRolePriorities();
    }

    private void ConfigureRolePriorities()
    {
        var route = currentUser.Role switch
        {
            "line-foreman" => new RoleRoute(
                "반장",
                new("인수인계 확인", "HANDOVER"),
                new("문서 찾기·열람", "DOCUMENT"),
                new("작업판", "WORK_SEQUENCE")),
            "team-lead" => new RoleRoute(
                "조장",
                new("작업 전 문서 확인", "DOCUMENT"),
                new("인수인계 확인", "HANDOVER"),
                new("채널 알림", "CHANNEL")),
            "team-member" or "viewer" => new RoleRoute(
                "작업자",
                new("문서 찾기·열람", "DOCUMENT"),
                new("인수인계 확인", "HANDOVER"),
                new("알림 확인", "NOTIFICATION")),
            _ when canWriteReports => new RoleRoute(
                "관리자",
                new("코멘트 검토", "FIELD_COMMENT_REVIEW"),
                new("보고서 근거 선정", "REPORT"),
                new("동기화·충돌 확인", "HISTORY")),
            _ => new RoleRoute(
                FormatUserRole(currentUser.Role),
                new("문서 찾기·열람", "DOCUMENT"),
                new("인수인계 확인", "HANDOVER"),
                new("알림 확인", "NOTIFICATION"))
        };

        RolePriorityTextBlock.Text =
            $"{route.RoleLabel} 첫 업무: 1. {route.First.Label}  →  2. {route.Second.Label}  →  3. {route.Third.Label}";
        ConfigureQuickTaskButton(QuickTaskOneButton, 1, route.First);
        ConfigureQuickTaskButton(QuickTaskTwoButton, 2, route.Second);
        ConfigureQuickTaskButton(QuickTaskThreeButton, 3, route.Third);

        PermissionGuideTextBlock.Text = BuildPermissionGuide(route.RoleLabel);
    }

    private static void ConfigureQuickTaskButton(
        Button button,
        int order,
        QuickTask task)
    {
        button.Content = $"{order}. {task.Label}";
        button.Tag = task.Action;
    }

    private string BuildPermissionGuide(string roleLabel)
    {
        if (canManageUsers)
        {
            return $"{roleLabel} 권한으로 계정·단말, 문서 운영, 검토·보고서를 사용할 수 있습니다. 시스템 관리자 전용 AI 운영은 별도 표시됩니다.";
        }

        if (canWriteReports)
        {
            return $"{roleLabel} 권한으로 문서 운영과 검토·보고서를 사용할 수 있습니다. 계정·단말 권한이 필요하면 현장 관리자에게 로그인 ID와 업무명을 전달하세요.";
        }

        if (canRegisterDocuments)
        {
            return $"{roleLabel} 권한으로 문서 등록·작업판·채널 관리를 사용할 수 있습니다. 상태·공개·보고서는 관리자급 권한이 필요하며, 현장 관리자에게 로그인 ID와 업무명을 전달하세요.";
        }

        return $"{roleLabel}는 문서 열람·FieldComment·채널 수신 업무를 사용할 수 있습니다. 문서 등록이나 관리 업무가 필요하면 현장 관리자에게 로그인 ID와 업무명을 전달하세요.";
    }

    private void QuickTaskButton_Click(object sender, RoutedEventArgs e)
    {
        var action = (sender as FrameworkElement)?.Tag?.ToString();
        switch (action)
        {
            case "DOCUMENT":
                FocusDocumentSearch();
                break;
            case "HANDOVER":
            case "CHANNEL":
                ChannelInboxButton_Click(sender, e);
                break;
            case "NOTIFICATION":
                NotificationButton_Click(sender, e);
                break;
            case "WORK_SEQUENCE":
                WorkSequenceAdminButton_Click(sender, e);
                break;
            case "FIELD_COMMENT_REVIEW":
                FieldCommentReviewButton_Click(sender, e);
                break;
            case "REPORT":
                ReportDraftButton_Click(sender, e);
                break;
            case "HISTORY":
                HistoryButton_Click(sender, e);
                break;
        }
    }

    private void RefreshSyncState()
    {
        var summary = services.ServerSync.GetQueueSummary();
        var unresolved = summary.Pending + summary.Failed;
        if (unresolved > 0)
        {
            SyncStateTextBlock.Text =
                $"동기화 미완료: 대기 {summary.Pending}건 · 실패/충돌 {summary.Failed}건(보류 {summary.Held}건 포함). " +
                "로컬 데이터와 원본 파일은 보존됩니다. 이력 > 동기화 큐에서 사유와 다음 조치를 확인하세요.";
            return;
        }

        SyncStateTextBlock.Text = serverDocumentClient is null
            ? "서버 미연결: 로컬 기록은 보존됩니다. 서버 반영이 필요한 업무는 서버 주소를 확인하고 다시 로그인하세요."
            : "동기화 상태: 서버 확인 대기·실패·충돌 없음.";
    }

    private bool EnsureDocumentRegistrationAllowed()
    {
        if (canRegisterDocuments)
        {
            return true;
        }

        workspace.StatusText =
            "문서 등록은 관리자/반장/조장 이상 권한이 필요합니다. 현장 관리자의 문의 채널로 로그인 ID와 필요한 업무를 전달하세요.";
        return false;
    }

    private bool EnsureDocumentGovernanceAllowed()
    {
        if (canGovernDocuments)
        {
            return true;
        }

        workspace.StatusText =
            "문서 상태와 공개본 결정은 관리자/문서관리/부서관리 권한이 필요합니다. 현장 관리자에게 로그인 ID와 필요한 업무를 전달하세요.";
        return false;
    }

    private bool EnsureFileWatchAllowed()
    {
        if (canManageFileWatch)
        {
            return true;
        }

        workspace.StatusText =
            "파일 감시는 관리자/문서관리/부서관리 권한이 필요합니다. 현장 관리자에게 로그인 ID와 필요한 업무를 전달하세요.";
        return false;
    }

    private bool EnsureReportWriteAllowed()
    {
        if (canWriteReports)
        {
            return true;
        }

        workspace.StatusText =
            "코멘트 검토와 보고서 작성은 관리자/문서관리/부서관리 권한이 필요합니다. 현장 관리자에게 로그인 ID와 필요한 업무를 전달하세요.";
        return false;
    }

    private bool EnsureChannelManagementAllowed()
    {
        if (canRegisterDocuments)
        {
            return true;
        }

        workspace.StatusText =
            "채널 관리와 인수인계 확인 현황은 관리자/반장/조장 이상 권한이 필요합니다. 현장 관리자에게 로그인 ID와 필요한 업무를 전달하세요.";
        return false;
    }

    private bool EnsureUserManagementAllowed()
    {
        if (canManageUsers)
        {
            return true;
        }

        workspace.StatusText =
            "사용자·단말 관리는 관리자/시스템 관리자 권한이 필요합니다. 현장 관리자에게 로그인 ID와 필요한 업무를 전달하세요.";
        return false;
    }

    private string GetCurrentActorName()
    {
        return currentDisplayName;
    }

    private string GetCurrentUserId()
    {
        return currentUser.UserId ?? currentUser.LoginId ?? GetCurrentActorName();
    }

    private void RefreshNotificationButton()
    {
        var unreadCount = services.Notifications.CountUnread(GetCurrentActorName());
        NotificationButton.Header =
            unreadCount == 0 ? "알림함" : $"알림함 ({unreadCount})";
    }

    private static string FormatDocumentStatus(string status)
    {
        return status switch
        {
            "WORKING" => "작업중",
            "IN_REVIEW" => "검토중",
            "PUBLISHED" => "공개",
            "ARCHIVED" => "보관",
            _ => status
        };
    }

    private static string FormatUserRole(string? role)
    {
        return role switch
        {
            "admin" => "관리자",
            "manager" => "관리자",
            "system-admin" => "시스템 관리자",
            "document-admin" => "문서 관리자",
            "assistant-manager" => "차장",
            "department-manager" => "부서장",
            "line-foreman" => "반장",
            "team-lead" => "조장",
            "team-member" => "조원",
            "viewer" => "열람자",
            _ => role ?? string.Empty
        };
    }

    private sealed record QuickTask(string Label, string Action);

    private sealed record RoleRoute(
        string RoleLabel,
        QuickTask First,
        QuickTask Second,
        QuickTask Third);
}
