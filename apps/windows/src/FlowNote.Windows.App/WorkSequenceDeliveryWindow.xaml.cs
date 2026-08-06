using System.Collections.ObjectModel;
using System.Net.Http;
using System.Windows;
using System.Windows.Controls;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.WorkSequences;

namespace FlowNote.Windows.App;

public partial class WorkSequenceDeliveryWindow : Window
{
    private readonly FlowNoteServerDocumentClient documentClient;
    private readonly FlowNoteServerChannelClient channelClient;
    private readonly WorkSequenceBoardRecord board;
    private readonly string currentUserId;
    private readonly DeliveryWorkspace workspace = new();
    private ServerWorkSequenceDeliveryPreviewResponse? preview;
    private ServerWorkSequenceDeliveryRequest? pendingDeliveryRequest;
    private string? pendingCandidateId;
    private bool refreshing;

    public WorkSequenceDeliveryWindow(
        FlowNoteServerDocumentClient documentClient,
        FlowNoteServerChannelClient channelClient,
        WorkSequenceBoardRecord board,
        string currentUserId)
    {
        InitializeComponent();
        this.documentClient = documentClient;
        this.channelClient = channelClient;
        this.board = board;
        this.currentUserId = currentUserId;
        DataContext = workspace;
        ApplyDeliveryState(false);
        Loaded += async (_, _) => await RefreshAsync();
    }

    private async void RefreshButton_Click(object sender, RoutedEventArgs e) => await RefreshAsync();

    private async Task RefreshAsync()
    {
        refreshing = true;
        try
        {
            var candidatesTask = documentClient.ListWorkSequenceNotificationCandidatesAsync(board.BoardId);
            var channelsTask = channelClient.ListChannelsAsync(status: "ACTIVE", manageableOnly: true);
            var templatesTask = channelClient.ListWorkSequenceDeliveryTemplatesAsync();
            await Task.WhenAll(candidatesTask, channelsTask, templatesTask);
            Replace(workspace.Candidates, candidatesTask.Result.Where(item => item.Status == "CANDIDATE"));
            Replace(workspace.Channels, channelsTask.Result);
            Replace(workspace.Templates, templatesTask.Result);
            CandidateListBox.SelectedItem = workspace.Candidates.FirstOrDefault();
            ChannelComboBox.SelectedItem = workspace.Channels.FirstOrDefault();
            ResultTextBox.Text = workspace.Channels.Count == 0
                ? "전달 가능한 채널이 없습니다. 채널 관리자에게 소유자 또는 관리자 역할과 등록 방법을 문의하세요."
                : $"후보 {workspace.Candidates.Count}건, 전달 가능 채널 {workspace.Channels.Count}개를 조회했습니다.";
        }
        catch (Exception exception)
        {
            ResultTextBox.Text = $"후보 전달 자료를 불러오지 못했습니다. 기존 후보와 채널 기록은 유지됩니다. 새로고침 후 다시 시도하세요. ({exception.Message})";
        }
        finally
        {
            refreshing = false;
        }
        await RefreshPreviewAsync();
    }

    private async void PreviewSelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!refreshing) await RefreshPreviewAsync();
    }

    private async Task RefreshPreviewAsync()
    {
        if (CandidateListBox.SelectedItem is not ServerWorkSequenceNotificationCandidateResponse candidate ||
            ChannelComboBox.SelectedItem is not ServerNotificationChannelResponse channel)
        {
            preview = null;
            workspace.Recipients.Clear();
            ApplyDeliveryState();
            return;
        }

        try
        {
            preview = await channelClient.PreviewWorkSequenceDeliveryAsync(
                board.BoardId,
                candidate.CandidateId,
                channel.ChannelId);
            Replace(workspace.Recipients, preview.Recipients);
            ChannelSummaryTextBlock.Text = $"운영 단위: {preview.ChannelSummary}";
            SourceSummaryTextBlock.Text = $"업무 원천: {preview.SourceSummary}";
            DocumentSummaryTextBlock.Text = preview.DocumentSummary;
            DeliveryTitleTextBox.Text = preview.Title;
            DeliveryBodyTextBox.Text = preview.Body;
            ResultTextBox.Text = preview.CanDeliver
                ? "대상 채널·수신자·업무 원천·공개 문서를 확인한 뒤 전달 방식을 선택하세요."
                : "채널 소유자 또는 관리자 역할이 필요합니다. 채널 관리자에게 역할 변경을 요청하세요.";
        }
        catch (Exception exception)
        {
            preview = null;
            workspace.Recipients.Clear();
            ResultTextBox.Text = $"미리보기를 확정하지 못했습니다. 후보와 원천은 변경하지 않았습니다. 새로고침 후 다시 확인하세요. ({exception.Message})";
        }
        ApplyDeliveryState();
    }

    private void TemplateComboBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (TemplateComboBox.SelectedItem is not ServerWorkSequenceDeliveryTemplateResponse template) return;
        DeliveryTitleTextBox.Text = template.Title;
        DeliveryBodyTextBox.Text = template.Body;
    }

    private async void SaveTemplateButton_Click(object sender, RoutedEventArgs e)
    {
        if (string.IsNullOrWhiteSpace(TemplateNameTextBox.Text) ||
            string.IsNullOrWhiteSpace(DeliveryTitleTextBox.Text) ||
            string.IsNullOrWhiteSpace(DeliveryBodyTextBox.Text))
        {
            ResultTextBox.Text = "템플릿 이름, 제목과 안내 문구를 입력하세요.";
            return;
        }
        try
        {
            var saved = await channelClient.CreateWorkSequenceDeliveryTemplateAsync(
                new ServerWorkSequenceDeliveryTemplateCreateRequest
                {
                    Name = TemplateNameTextBox.Text.Trim(),
                    Title = DeliveryTitleTextBox.Text.Trim(),
                    Body = DeliveryBodyTextBox.Text.Trim()
                });
            workspace.Templates.Add(saved);
            TemplateComboBox.SelectedItem = saved;
            ResultTextBox.Text = $"현재 현장 범위에 문구 템플릿을 저장했습니다: {saved.Name}";
        }
        catch (Exception exception)
        {
            ResultTextBox.Text = $"문구 템플릿을 저장하지 못했습니다. 입력 문구는 유지됩니다. ({exception.Message})";
        }
    }

    private async void ChannelDeliveryButton_Click(object sender, RoutedEventArgs e) =>
        await DeliverAsync("CHANNEL");

    private async void HandoverDeliveryButton_Click(object sender, RoutedEventArgs e) =>
        await DeliverAsync("HANDOVER");

    private async Task DeliverAsync(string deliveryMode)
    {
        if (preview is null || CandidateListBox.SelectedItem is not ServerWorkSequenceNotificationCandidateResponse candidate)
        {
            ResultTextBox.Text = "먼저 후보와 채널의 미리보기를 확인하세요.";
            return;
        }
        if (string.IsNullOrWhiteSpace(DeliveryReasonTextBox.Text))
        {
            ResultTextBox.Text = "감사 이력에 남길 전달 사유를 입력하세요.";
            DeliveryReasonTextBox.Focus();
            return;
        }
        var recipientIds = preview.Recipients.Select(item => item.UserId).ToArray();
        var draftWithoutKey = new ServerWorkSequenceDeliveryRequest
        {
            ChannelId = preview.ChannelId,
            DeliveryMode = deliveryMode,
            RecipientIds = recipientIds,
            Title = DeliveryTitleTextBox.Text.Trim(),
            Body = DeliveryBodyTextBox.Text.Trim(),
            Reason = DeliveryReasonTextBox.Text.Trim(),
            BaseBoardRevision = preview.CurrentBoardRevision,
        };
        var draft = draftWithoutKey with
        {
            IdempotencyKey = draftWithoutKey.BuildStableIdempotencyKey(board.BoardId, candidate.CandidateId)
        };
        var request = pendingCandidateId == candidate.CandidateId &&
                      pendingDeliveryRequest is not null &&
                      SameIntent(pendingDeliveryRequest, draft)
            ? pendingDeliveryRequest
            : draft;
        pendingCandidateId = candidate.CandidateId;
        pendingDeliveryRequest = request;
        ApplyDeliveryState(false);
        try
        {
            var result = await WorkSequenceServerPolicy.RunWithResponseLossRetryAsync(() =>
                channelClient.DeliverWorkSequenceCandidateAsync(
                    board.BoardId,
                    candidate.CandidateId,
                    request));
            var resultText = BuildResult(result);
            if (result.Status == "COMPLETED")
            {
                pendingCandidateId = null;
                pendingDeliveryRequest = null;
            }
            await RefreshAsync();
            ResultTextBox.Text = resultText;
        }
        catch (FlowNoteServerConflictException exception)
        {
            ResultTextBox.Text = $"전달을 중단했습니다. 기존 메시지·인수인계·수신 확인과 원천은 유지됩니다. {exception.Message} 후보와 채널을 새로고침하세요.";
        }
        catch (Exception exception) when (exception is HttpRequestException or TaskCanceledException or InvalidOperationException)
        {
            ResultTextBox.Text = $"서버 응답을 확인하지 못했습니다. 같은 전달 의도는 서버 멱등 receipt로 보호됩니다. 새로고침해 결과를 확인한 뒤 실패 수신자만 다시 시도하세요. ({exception.Message})";
        }
        finally
        {
            ApplyDeliveryState();
        }
    }

    private string BuildResult(ServerWorkSequenceDeliveryResponse result)
    {
        var failed = result.Recipients.Where(item => item.DeliveryStatus == "FAILED").ToList();
        var lines = new List<string>
        {
            $"전달 결과: 성공 {result.SuccessCount}명 / 실패 {result.FailureCount}명",
            $"메시지: {result.MessageId ?? "없음"}",
            $"인수인계: {result.HandoverId ?? "생성하지 않음"}",
            $"업무 원천 변경 이력: {result.ChangeId}",
        };
        if (failed.Count == 0)
        {
            lines.Add("모든 수신자 전달이 완료됐습니다. 채널함 또는 인수인계 현황에서 후속 상태를 확인하세요.");
        }
        else
        {
            lines.Add("실패 수신자: " + string.Join(", ", failed.Select(item => item.RecipientId)));
            lines.Add("기존 성공 receipt와 원천은 유지됩니다. 채널 관리자에게 멤버십을 확인한 뒤 같은 의도로 실패 수신자만 재전송하세요.");
        }
        return string.Join(Environment.NewLine, lines);
    }

    private static bool SameIntent(
        ServerWorkSequenceDeliveryRequest left,
        ServerWorkSequenceDeliveryRequest right) =>
        left.ChannelId == right.ChannelId &&
        left.DeliveryMode == right.DeliveryMode &&
        left.RecipientIds.SequenceEqual(right.RecipientIds, StringComparer.Ordinal) &&
        left.Title == right.Title &&
        left.Body == right.Body &&
        left.Reason == right.Reason &&
        left.BaseBoardRevision == right.BaseBoardRevision;

    private void OpenChannelInboxButton_Click(object sender, RoutedEventArgs e) =>
        new ChannelInboxWindow(channelClient, currentUserId) { Owner = this }.ShowDialog();

    private void OpenHandoverStatusButton_Click(object sender, RoutedEventArgs e) =>
        new HandoverStatusWindow(channelClient, currentUserId) { Owner = this }.ShowDialog();

    private void ApplyDeliveryState(bool enabled = true)
    {
        var canDeliver = enabled && preview?.CanDeliver == true && preview.Recipients.Count > 0;
        ChannelDeliveryButton.IsEnabled = canDeliver;
        HandoverDeliveryButton.IsEnabled = canDeliver;
    }

    private static void Replace<T>(ObservableCollection<T> target, IEnumerable<T> values)
    {
        target.Clear();
        foreach (var value in values) target.Add(value);
    }

    private sealed class DeliveryWorkspace
    {
        public ObservableCollection<ServerWorkSequenceNotificationCandidateResponse> Candidates { get; } = [];
        public ObservableCollection<ServerNotificationChannelResponse> Channels { get; } = [];
        public ObservableCollection<ServerWorkSequenceDeliveryRecipientPreview> Recipients { get; } = [];
        public ObservableCollection<ServerWorkSequenceDeliveryTemplateResponse> Templates { get; } = [];
    }
}
