using System.Windows;
using System.Windows.Controls;
using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.App;

public partial class DocumentApprovalWindow : Window
{
    private readonly FlowNoteServerApprovalClient client;
    private readonly bool canRequest;
    private readonly bool canDecide;

    public DocumentApprovalWindow(
        FlowNoteServerApprovalClient client,
        bool canRequest,
        bool canDecide,
        string? initialDocumentId = null)
    {
        InitializeComponent();
        this.client = client;
        this.canRequest = canRequest;
        this.canDecide = canDecide;
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
            ApprovalGrid.ItemsSource = await client.ListAsync(AssignedToMeCheckBox.IsChecked == true);
            GuidanceTextBox.Text = "승인 작업함을 서버 권위 상태로 갱신했습니다.";
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
            await client.PublishAsync(approval, ReasonTextBox.Text.Trim(), NewMutationKey("publish"));
            await RefreshAsync();
        }
        catch (Exception exception) { ShowFailure(exception); }
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

    private void ShowFailure(Exception exception)
    {
        GuidanceTextBox.Text = $"작업을 완료하지 못했습니다. 원본 문서와 승인 이력은 보존됩니다.\n{exception.Message}\n담당 검토자 또는 문서 관리자에게 문의한 뒤 서버 상태를 새로고침하세요.";
    }
}
