using System.Net.Http;
using System.Windows;
using FlowNote.Windows.Core.Auth;

namespace FlowNote.Windows.App;

public partial class MainWindow
{
    private void NotificationButton_Click(object sender, RoutedEventArgs e)
    {
        var window = new NotificationWindow(services.Notifications, GetCurrentActorName())
        {
            Owner = this
        };
        window.ShowDialog();
        RefreshNotificationButton();
    }

    private void ChannelInboxButton_Click(object sender, RoutedEventArgs e)
    {
        var window = new ChannelInboxWindow(serverChannelClient, GetCurrentUserId())
        {
            Owner = this
        };
        window.ShowDialog();
        RefreshSyncState();
    }

    private void ChannelManagementButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureChannelManagementAllowed())
        {
            return;
        }

        var window = new ChannelManagementWindow(serverChannelClient)
        {
            Owner = this
        };
        window.ShowDialog();
    }

    private void HandoverStatusButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureChannelManagementAllowed())
        {
            return;
        }

        var window = new HandoverStatusWindow(serverChannelClient, GetCurrentUserId())
        {
            Owner = this
        };
        window.ShowDialog();
    }

    private void HistoryButton_Click(object sender, RoutedEventArgs e)
    {
        var window = new HistoryWindow(
            services.History,
            services.ServerSync,
            services.ServerReconciliation,
            serverDocumentClient,
            currentUser.UserId,
            ResumeServerTrafficAfterReconciliationAsync)
        {
            Owner = this
        };
        window.ShowDialog();
        RefreshSyncState();
    }

    private void UserManagementButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureUserManagementAllowed())
        {
            return;
        }

        if (serverAccountClient is not null)
        {
            new ServerUserManagementWindow(
                serverAccountClient,
                GetCurrentUserId(),
                currentUser.Role ?? string.Empty)
            {
                Owner = this
            }.ShowDialog();
            return;
        }

        var localWindow = new UserManagementWindow(services.Users, GetCurrentActorName())
        {
            Owner = this
        };
        localWindow.ShowDialog();
        if (string.Equals(
                localWindow.UpdatedUserId,
                currentUser.UserId,
                StringComparison.Ordinal) &&
            !string.IsNullOrWhiteSpace(localWindow.UpdatedDisplayName))
        {
            currentDisplayName = localWindow.UpdatedDisplayName;
            SignedInUserTextBlock.Text =
                $"{localWindow.UpdatedDisplayName} ({FormatUserRole(currentUser.Role)})";
        }
    }

    private void TerminalDeviceManagementButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureUserManagementAllowed())
        {
            return;
        }

        var window = new TerminalDeviceManagementWindow(serverTerminalDeviceClient)
        {
            Owner = this
        };
        window.ShowDialog();
    }

    private void WorkSequenceAdminButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureDocumentRegistrationAllowed())
        {
            return;
        }

        var window = new WorkSequenceAdminWindow(
            services.WorkSequences,
            serverDocumentClient,
            GetCurrentUserId())
        {
            Owner = this
        };
        window.ShowDialog();
    }

    private async void WorkSequenceTvButton_Click(object sender, RoutedEventArgs e)
    {
        string? boardId = null;
        if (serverDocumentClient is not null)
        {
            try
            {
                boardId = (await serverDocumentClient.ListWorkSequenceBoardsAsync())
                    .FirstOrDefault()
                    ?.BoardId;
            }
            catch (Exception exception) when (
                exception is HttpRequestException or TaskCanceledException or InvalidOperationException)
            {
                workspace.StatusText =
                    $"서버 작업순서 조회 실패: 로컬 읽기 캐시를 확인합니다. ({exception.Message})";
            }
        }

        var localBoard = services.WorkSequences.ListBoards().FirstOrDefault();
        boardId ??= localBoard?.BoardId;
        if (boardId is null)
        {
            workspace.StatusText = "현황판을 열기 전에 작업판을 먼저 생성하세요.";
            return;
        }

        var window = new WorkSequenceTvWindow(
            services.WorkSequences,
            serverDocumentClient,
            boardId)
        {
            Owner = this
        };
        window.Show();
    }

    private void ReportDraftButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureReportWriteAllowed())
        {
            return;
        }

        var folder = GetSelectedFolderOrDefault();
        var window = new ReportDraftWindow(
            services.Reports,
            folder.Id,
            GetCurrentActorName(),
            serverDocumentClient)
        {
            Owner = this
        };
        window.ShowDialog();
        if (window.DocumentSaved)
        {
            RefreshDocuments(folder.Id, "보고서 문서를 저장했습니다.");
        }
    }

    private void AISearchQualityButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureReportWriteAllowed())
        {
            return;
        }

        var window = new AISearchQualityWindow(serverDocumentClient)
        {
            Owner = this
        };
        window.ShowDialog();
    }

    private void AIOperationsButton_Click(object sender, RoutedEventArgs e)
    {
        if (!RolePermissionPolicy.CanOperateAIOperations(currentUser.Role))
        {
            workspace.StatusText =
                "AI 운영은 시스템 관리자 권한이 필요합니다. 현장 관리자에게 로그인 ID와 필요한 업무를 전달하세요.";
            return;
        }

        new AIOperationsWindow(serverAIOperationsClient) { Owner = this }.ShowDialog();
    }

    private void AIGroundTruthButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureReportWriteAllowed())
        {
            return;
        }

        new AIGroundTruthOperationsWindow(
            serverDocumentClient,
            GetCurrentUserId(),
            currentUser.Role ?? string.Empty)
        {
            Owner = this
        }.ShowDialog();
    }

    private void FieldCommentReviewButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureReportWriteAllowed())
        {
            return;
        }

        var window = new FieldCommentReviewWindow(
            services.FieldComments,
            services.ServerSync,
            GetCurrentActorName(),
            currentUser.UserId,
            serverDocumentClient)
        {
            Owner = this
        };
        window.ShowDialog();
        if (window.ReviewChanged)
        {
            workspace.StatusText =
                "FieldComment 검토 변경을 반영했습니다. 보고서 근거 선정은 빠른 업무 2번에서 이어갈 수 있습니다.";
        }

        RefreshSyncState();
    }

    private void FileWatchButton_Click(object sender, RoutedEventArgs e)
    {
        if (!EnsureFileWatchAllowed())
        {
            return;
        }

        var window = new FileWatchWindow(
            services.FileWatch,
            services.Documents,
            GetCurrentActorName())
        {
            Owner = this
        };
        window.ShowDialog();
        RefreshDocuments(selectedFolder?.Id, "파일 감시 후보를 갱신했습니다.");
    }
}
