using System.Windows;
using System.Windows.Controls;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Sync;

namespace FlowNote.Windows.App;

public partial class DocumentApprovalWindow : Window
{
    private readonly FlowNoteServerApprovalClient client;
    private readonly bool canRequest;
    private readonly bool canDecide;
    private readonly ServerSyncService? serverSyncService;

    public DocumentApprovalWindow(
        FlowNoteServerApprovalClient client,
        bool canRequest,
        bool canDecide,
        string? initialDocumentId = null,
        ServerSyncService? serverSyncService = null)
    {
        InitializeComponent();
        this.client = client;
        this.canRequest = canRequest;
        this.canDecide = canDecide;
        this.serverSyncService = serverSyncService;
        DocumentIdTextBox.Text = initialDocumentId ?? string.Empty;
        RequestButton.IsEnabled = canRequest;
        ApproveButton.IsEnabled = RejectButton.IsEnabled = PublishButton.IsEnabled = CancelButton.IsEnabled = canDecide;
        RequestButton.ToolTip = canRequest
            ? "현재 서버 최신 버전과 hash를 고정해 검토를 요청합니다."
            : "문서 작성 권한이 필요합니다. 시스템 관리자에게 문의하세요.";
        var governanceGuide = canDecide
            ? "선택한 승인 작업을 처리합니다."
            : "문서 검토·공개 권한이 필요합니다. 시스템 관리자에게 문의하세요.";
        ApproveButton.ToolTip = RejectButton.ToolTip = PublishButton.ToolTip = CancelButton.ToolTip = governanceGuide;
        Loaded += async (_, _) => await RefreshAsync();
    }

    private async void RefreshButton_Click(object sender, RoutedEventArgs e) => await RefreshAsync();

    private async Task RefreshAsync()
    {
        try
        {
            var approvals = await client.ListAsync(AssignedToMeCheckBox.IsChecked == true);
            ApprovalGrid.ItemsSource = approvals;
            var recovered = await RecoverPublishedApprovalsAsync(approvals);
            GuidanceTextBox.Text = recovered > 0
                ? $"승인 작업함을 갱신하고 서버 공개본 {recovered}건을 로컬 SQLite에 복구 반영했습니다."
                : "승인 작업함을 서버 권위 상태로 갱신했습니다.";
        }
        catch (Exception exception)
        {
            ShowFailure(exception);
        }
    }

    private void ApprovalGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (ApprovalGrid.SelectedItem is not ServerDocumentApprovalResponse approval)
        {
            EventGrid.ItemsSource = null;
            return;
        }
        DocumentIdTextBox.Text = approval.DocumentId;
        EventGrid.ItemsSource = approval.Events;
        GuidanceTextBox.Text = $"{approval.StatusDisplay}\n{approval.NextAction}\n\n승인 ID: {approval.ApprovalId}\nversion: {approval.VersionId}\nrevision: {approval.BaseDocumentRevision}\nhash: {approval.SourceFileHashSha256}";
    }

    private async void RequestButton_Click(object sender, RoutedEventArgs e)
    {
        if (!canRequest || !RequireReason() || string.IsNullOrWhiteSpace(DocumentIdTextBox.Text))
        {
            GuidanceTextBox.Text = "문서 ID와 세 글자 이상의 요청 사유를 입력하세요.";
            return;
        }
        if (string.IsNullOrWhiteSpace(ReviewerUserIdTextBox.Text) == string.IsNullOrWhiteSpace(ReviewerRoleTextBox.Text))
        {
            GuidanceTextBox.Text = "검토자 사용자 ID 또는 검토 역할 중 하나만 입력하세요.";
            return;
        }
        try
        {
            var document = await client.GetDocumentAsync(DocumentIdTextBox.Text.Trim());
            var version = document.LatestVersion;
            if (version?.File.HashSha256 is not { Length: 64 } hash)
                throw new InvalidOperationException("서버 최신 버전의 file hash를 확인할 수 없습니다.");
            await client.RequestAsync(new ServerDocumentApprovalCreateRequest(
                document.DocumentId,
                version.VersionId,
                document.Revision,
                hash,
                Clean(ReviewerUserIdTextBox.Text),
                Clean(ReviewerRoleTextBox.Text),
                ReasonTextBox.Text.Trim(),
                DueDatePicker.SelectedDate is { } due ? new DateTimeOffset(due) : null,
                NewMutationKey("request")));
            await RefreshAsync();
        }
        catch (Exception exception) { ShowFailure(exception); }
    }

    private async void ApproveButton_Click(object sender, RoutedEventArgs e) => await DecideAsync("APPROVE");
    private async void RejectButton_Click(object sender, RoutedEventArgs e) => await DecideAsync("REJECT");

    private async Task DecideAsync(string decision)
    {
        if (!canDecide || ApprovalGrid.SelectedItem is not ServerDocumentApprovalResponse approval || !RequireReason())
        {
            GuidanceTextBox.Text = "승인 작업을 선택하고 세 글자 이상의 사유를 입력하세요.";
            return;
        }
        try
        {
            await client.DecideAsync(approval.ApprovalId, decision, ReasonTextBox.Text.Trim(), NewMutationKey(decision));
            await RefreshAsync();
        }
        catch (Exception exception) { ShowFailure(exception); }
    }

    private async void PublishButton_Click(object sender, RoutedEventArgs e)
    {
        if (!canDecide || ApprovalGrid.SelectedItem is not ServerDocumentApprovalResponse approval || !RequireReason())
        {
            GuidanceTextBox.Text = "승인 완료 작업을 선택하고 공개 사유를 입력하세요.";
            return;
        }
        try
        {
            var mutationKey = NewMutationKey("publish");
            var publishResponse = await client.PublishAsync(
                approval, ReasonTextBox.Text.Trim(), mutationKey);
            var readBack = await client.GetDocumentAsync(approval.DocumentId);
            EnsurePublicationReadBack(approval, publishResponse, readBack);
            var localResult = serverSyncService?.ApplyApprovalPublicationReadBack(
                readBack, approval.ApprovalId, mutationKey);
            await RefreshAsync();
            GuidanceTextBox.Text = localResult is null
                ? $"서버 공개를 확인했습니다. 공개 version {readBack.PublishedVersionId}, revision {readBack.Revision}. 로컬 동기화 서비스가 없어 로컬 원천과 큐는 변경하지 않았습니다."
                : $"서버 공개와 로컬 반영을 확인했습니다.\n{localResult.Message}";
        }
        catch (Exception exception)
        {
            if (await TryRecoverPublishedApprovalAsync(approval))
            {
                GuidanceTextBox.Text = "공개 응답 또는 로컬 반영 중 오류가 있었지만 서버 상세를 다시 읽어 공개 성공 사실과 로컬 상태를 복구했습니다.";
                return;
            }
            ShowFailure(exception, publicationAttempted: true);
        }
    }

    private async void CancelButton_Click(object sender, RoutedEventArgs e)
    {
        if (!canDecide || ApprovalGrid.SelectedItem is not ServerDocumentApprovalResponse approval || !RequireReason())
        {
            GuidanceTextBox.Text = "취소할 승인 작업을 선택하고 사유를 입력하세요.";
            return;
        }
        try
        {
            await client.CancelAsync(approval.ApprovalId, ReasonTextBox.Text.Trim(), NewMutationKey("cancel"));
            await RefreshAsync();
        }
        catch (Exception exception) { ShowFailure(exception); }
    }

    private bool RequireReason() => ReasonTextBox.Text.Trim().Length >= 3;
    private static string? Clean(string value) => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
    private static string NewMutationKey(string action) => $"wpf-approval:{action}:{Guid.NewGuid():N}";

    private async Task<int> RecoverPublishedApprovalsAsync(
        IReadOnlyList<ServerDocumentApprovalResponse> approvals)
    {
        if (serverSyncService is null)
        {
            return 0;
        }
        var recovered = 0;
        foreach (var approval in approvals.Where(item => item.Status == "PUBLISHED"))
        {
            var readBack = await client.GetDocumentAsync(approval.DocumentId);
            if (!PublicationMatches(approval, readBack))
            {
                continue;
            }
            var result = serverSyncService.ApplyApprovalPublicationReadBack(
                readBack,
                approval.ApprovalId,
                $"server-read-back:{approval.ApprovalId}");
            recovered += result.Applied ? 1 : 0;
        }
        return recovered;
    }

    private async Task<bool> TryRecoverPublishedApprovalAsync(
        ServerDocumentApprovalResponse approval)
    {
        if (serverSyncService is null)
        {
            return false;
        }
        try
        {
            var currentApproval = (await client.ListAsync())
                .FirstOrDefault(item => item.ApprovalId == approval.ApprovalId);
            if (currentApproval?.Status != "PUBLISHED")
            {
                return false;
            }
            var readBack = await client.GetDocumentAsync(approval.DocumentId);
            if (!PublicationMatches(approval, readBack))
            {
                return false;
            }
            var result = serverSyncService.ApplyApprovalPublicationReadBack(
                readBack,
                approval.ApprovalId,
                $"server-recovery:{approval.ApprovalId}");
            return result.LocalMappingFound;
        }
        catch
        {
            return false;
        }
    }

    private static void EnsurePublicationReadBack(
        ServerDocumentApprovalResponse approval,
        ServerApprovalDocumentResponse response,
        ServerApprovalDocumentResponse readBack)
    {
        if (response.Revision > readBack.Revision || !PublicationMatches(approval, readBack))
        {
            throw new InvalidOperationException(
                "공개 응답과 서버 상세 read-back의 공개 version, revision 또는 승인 ID가 일치하지 않습니다.");
        }
    }

    private static bool PublicationMatches(
        ServerDocumentApprovalResponse approval,
        ServerApprovalDocumentResponse readBack) =>
        readBack.Status == "PUBLISHED" &&
        readBack.PublishedVersion?.IsPublished == true &&
        readBack.PublishedVersion.VersionStatus == "PUBLISHED" &&
        readBack.PublishedVersionId == approval.VersionId &&
        readBack.PublicationApprovalId == approval.ApprovalId;

    private void ShowFailure(Exception exception, bool publicationAttempted = false)
    {
        if (exception is FlowNoteServerApprovalException { StatusCode: 403 })
        {
            GuidanceTextBox.Text = $"문서 검토·공개 역할이 필요합니다. 시스템 관리자에게 역할을 요청하세요.\n{exception.Message}\n원본 문서, 로컬 큐와 승인 이력은 보존됩니다.";
            return;
        }
        GuidanceTextBox.Text = publicationAttempted
            ? $"공개 작업을 완료하지 못했습니다. 서버 공개 여부는 확인되지 않았고 로컬 원천과 큐는 보존됩니다.\n{exception.Message}\n서버 연결을 확인한 뒤 새로고침하면 공개 성공 사실을 상세 read-back으로 복구합니다."
            : $"작업을 완료하지 못했습니다. 원본 문서와 승인 이력은 보존됩니다.\n{exception.Message}\n담당 검토자 또는 문서 관리자에게 문의한 뒤 서버 상태를 새로고침하세요.";
    }
}
