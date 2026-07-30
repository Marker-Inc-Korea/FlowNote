using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Windows;
using System.Windows.Controls;
using FlowNote.Windows.Core.FieldComments;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Storage;
using FlowNote.Windows.Core.Sync;

namespace FlowNote.Windows.App;

public partial class FieldCommentReviewWindow : Window
{
    private readonly FieldCommentService fieldComments;
    private readonly ServerSyncService serverSync;
    private readonly FlowNoteServerDocumentClient? serverClient;
    private readonly string actorName;
    private readonly string? serverUserId;
    private readonly ReviewWorkspace workspace = new();
    private IReadOnlyList<ServerFieldCommentQualityItemResponse> qualityIssues = [];
    private ServerFieldCommentBulkReviewRequest? lastBulkRequest;
    private IReadOnlyDictionary<string, FieldCommentReviewRecord>? lastBulkLocalByServerId;
    private bool loadingSavedViews;

    public FieldCommentReviewWindow(
        FieldCommentService fieldComments,
        ServerSyncService serverSync,
        string actorName,
        string? serverUserId,
        FlowNoteServerDocumentClient? serverClient)
    {
        InitializeComponent();
        this.fieldComments = fieldComments;
        this.serverSync = serverSync;
        this.actorName = actorName;
        this.serverUserId = serverUserId;
        this.serverClient = serverClient;
        DataContext = workspace;
        Loaded += FieldCommentReviewWindow_Loaded;
    }

    public bool ReviewChanged { get; private set; }

    private async void FieldCommentReviewWindow_Loaded(object sender, RoutedEventArgs e)
    {
        StatusFilterComboBox.ItemsSource = new[]
        {
            new StatusOption("ALL", "전체")
        }.Concat(FieldCommentService.ReviewStatuses.Select(status => new StatusOption(status, FormatStatus(status))));
        StatusFilterComboBox.SelectedValue = "ALL";
        ReviewStatusComboBox.ItemsSource = FieldCommentService.ReviewStatuses.Select(status => new StatusOption(status, FormatStatus(status))).ToList();
        AgingFilterComboBox.ItemsSource = new[]
        {
            new StatusOption("ALL", "전체"), new StatusOption("7", "7일 이상"), new StatusOption("30", "30일 이상")
        };
        AttachmentFilterComboBox.ItemsSource = new[]
        {
            new StatusOption("ALL", "전체"), new StatusOption("YES", "첨부 있음"), new StatusOption("NO", "첨부 없음")
        };
        ReportLinkFilterComboBox.ItemsSource = new[]
        {
            new StatusOption("ALL", "전체"), new StatusOption("YES", "연결됨"), new StatusOption("NO", "미연결")
        };
        WorkbenchFilterComboBox.ItemsSource = new[]
        {
            new StatusOption("ALL", "전체"),
            new StatusOption("CONFLICT", "상충/검토 필요"),
            new StatusOption("UNREVIEWED", "미검토"),
            new StatusOption("OVERDUE", "기한 초과"),
            new StatusOption("UNASSIGNED", "담당자 없음"),
            new StatusOption("MISSING_EVIDENCE", "근거 누락"),
            new StatusOption("DUPLICATE_SUSPECTED", "중복 의심"),
            new StatusOption("REPORT_UNLINKED", "보고서 미연결"),
            new StatusOption("OLD_NEW", "품질: 오래된 NEW"),
            new StatusOption("WEAK_SELECTED", "품질: 근거 부족 SELECTED"),
            new StatusOption("MISSING_REPORT_SOURCE", "품질: 보고서 원천 누락"),
            new StatusOption("INCOMPLETE_REPORT_TRACE", "품질: trace/version 누락"),
            new StatusOption("SOURCE_HASH_MISMATCH", "품질: hash 불일치"),
            new StatusOption("SOURCE_REVISION_MISMATCH", "품질: revision 불일치")
        };
        foreach (var combo in new[] { AgingFilterComboBox, AttachmentFilterComboBox, ReportLinkFilterComboBox, WorkbenchFilterComboBox })
        {
            combo.DisplayMemberPath = nameof(StatusOption.Label);
            combo.SelectedValuePath = nameof(StatusOption.Value);
            combo.SelectedValue = "ALL";
        }
        ReloadSavedViews();
        await RefreshQualityIssuesAsync();
        RefreshComments("FieldComment 검토 목록을 조회했습니다.");
    }

    private void SaveViewButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            fieldComments.SaveView(SavedViewNameTextBox.Text, BuildFilter());
            ReloadSavedViews(SavedViewNameTextBox.Text.Trim());
            StatusTextBlock.Text = "현재 필터를 저장된 보기로 보존했습니다.";
        }
        catch (ArgumentException exception)
        {
            StatusTextBlock.Text = exception.Message;
        }
    }

    private void SavedViewComboBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (loadingSavedViews || SavedViewComboBox.SelectedItem is not FieldCommentSavedView view)
        {
            return;
        }
        ApplyFilter(view.Filter);
        RefreshComments($"저장된 보기 '{view.Name}'를 적용했습니다.");
    }

    private void ReloadSavedViews(string? selectedName = null)
    {
        loadingSavedViews = true;
        var views = fieldComments.ListSavedViews();
        SavedViewComboBox.ItemsSource = views;
        SavedViewComboBox.SelectedItem = views.FirstOrDefault(item => item.Name == selectedName);
        loadingSavedViews = false;
    }

    private async void RefreshButton_Click(object sender, RoutedEventArgs e)
    {
        await RefreshQualityIssuesAsync();
        RefreshComments("필터를 적용했습니다.");
    }

    private void FieldCommentGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        LoadSelectedComment();
    }

    private async void SaveReviewButton_Click(object sender, RoutedEventArgs e)
    {
        if (FieldCommentGrid.SelectedItem is not FieldCommentReviewRecord selected)
        {
            StatusTextBlock.Text = "검토할 FieldComment를 선택하세요.";
            return;
        }

        var status = ReviewStatusComboBox.SelectedValue?.ToString();
        if (string.IsNullOrWhiteSpace(status))
        {
            StatusTextBlock.Text = "변경할 상태를 선택하세요.";
            return;
        }

        var changedAt = DateTime.UtcNow;
        try
        {
            var updated = fieldComments.UpdateReview(
                selected.CommentId,
                NormalizedContentTextBox.Text,
                AnalysisContentTextBox.Text,
                status,
                actorName,
                TransitionReasonTextBox.Text,
                AssignedToTextBox.Text,
                ReviewDueDatePicker.SelectedDate,
                ConflictCheckBox.IsChecked == true,
                ConflictBasisTextBox.Text);
            var syncResult = await serverSync.QueueAndTrySyncFieldCommentReviewAsync(
                updated,
                serverClient,
                serverUserId,
                changedAt);
            ReviewChanged = true;
            RefreshComments(syncResult.Success
                ? $"검토 내용을 서버에 저장했습니다: {FormatStatus(status)}. 원천 코멘트와 검토 이력은 함께 보존됩니다. 다음: 보고서에 쓸 항목은 '보고서선정' 상태인지 확인하세요."
                : $"검토 내용은 이 PC에 저장했고 서버 반영은 대기 중입니다: {FormatStatus(status)}. 원천 코멘트와 동기화 기록은 보존됩니다. 다음: 이력의 동기화 큐에서 실패·충돌 사유를 확인한 뒤 다시 시도하세요.",
                selected.CommentId);
        }
        catch (Exception exception) when (exception is InvalidOperationException or ArgumentOutOfRangeException or HttpRequestException or TaskCanceledException)
        {
            StatusTextBlock.Text = BuildPreservedSourceFailureMessage(
                exception,
                "검토 내용을 저장하지 못했습니다.",
                "목록을 새로고침한 뒤 최신 상태에서 다시 저장하세요.");
        }
    }

    private async void BulkSaveReviewButton_Click(object sender, RoutedEventArgs e)
    {
        var selected = FieldCommentGrid.SelectedItems.Cast<FieldCommentReviewRecord>().ToList();
        if (selected.Count == 0)
        {
            StatusTextBlock.Text = "일괄 검토할 FieldComment를 하나 이상 선택하세요.";
            return;
        }
        if (selected.Count > 200)
        {
            StatusTextBlock.Text = "일괄 검토는 한 번에 최대 200건입니다. 선택을 나눠 실행하세요.";
            return;
        }

        var status = ReviewStatusComboBox.SelectedValue?.ToString();
        if (string.IsNullOrWhiteSpace(status))
        {
            StatusTextBlock.Text = "일괄 변경할 상태를 선택하세요.";
            return;
        }

        if (serverClient is null)
        {
            StatusTextBlock.Text = WorkflowFailureGuidance.Format(
                "서버 연결이 없어 일괄 처리를 시작하지 못했습니다.",
                "선택 항목과 원천 코멘트",
                "현재 사용자",
                "서버 주소와 로그인을 확인한 뒤 다시 실행하세요.");
            return;
        }

        try
        {
            var localByServerId = new Dictionary<string, FieldCommentReviewRecord>(StringComparer.Ordinal);
            var requestItems = new List<ServerFieldCommentBulkReviewItemRequest>();
            foreach (var item in selected)
            {
                var serverCommentId = fieldComments.GetServerCommentId(item.CommentId);
                if (string.IsNullOrWhiteSpace(serverCommentId))
                {
                    continue;
                }
                var serverState = await serverClient.GetFieldCommentAsync(serverCommentId);
                localByServerId[serverCommentId] = item;
                requestItems.Add(new ServerFieldCommentBulkReviewItemRequest
                {
                    CommentId = serverCommentId,
                    BaseReviewRevision = serverState.ReviewRevision,
                    MutationKey = $"wpf-bulk-review-{Guid.NewGuid():N}"
                });
            }
            if (requestItems.Count != selected.Count)
            {
                StatusTextBlock.Text = $"선택 {selected.Count}건 중 서버 ID가 없는 {selected.Count - requestItems.Count}건은 일괄 처리할 수 없습니다.";
                return;
            }

            var request = new ServerFieldCommentBulkReviewRequest
            {
                Items = requestItems,
                Status = status,
                NormalizedContent = NormalizedContentTextBox.Text,
                AnalysisContent = AnalysisContentTextBox.Text,
                AssignedTo = AssignedToTextBox.Text,
                ReviewDueAt = ReviewDueDatePicker.SelectedDate,
                TransitionReason = TransitionReasonTextBox.Text,
                ConflictFlag = ConflictCheckBox.IsChecked == true,
                ConflictBasis = ConflictBasisTextBox.Text
            };
            var preview = await serverClient.PreviewFieldCommentBulkReviewAsync(request);
            FieldCommentBulkReviewResultValidator.ValidatePreview(preview, request.Items);
            var previewWindow = new FieldCommentBulkPreviewWindow(preview) { Owner = this };
            if (previewWindow.ShowDialog() != true)
            {
                StatusTextBlock.Text = "일괄 처리를 취소했습니다. 사전검증 결과는 화면에서 확인했습니다.";
                return;
            }

            lastBulkRequest = request;
            lastBulkLocalByServerId = localByServerId;
            RetryBulkResultButton.IsEnabled = true;
            await ExecuteAndApplyBulkAsync(request, localByServerId, "일괄 처리");
        }
        catch (Exception exception) when (exception is InvalidOperationException or ArgumentOutOfRangeException or HttpRequestException or TaskCanceledException)
        {
            StatusTextBlock.Text = WorkflowFailureGuidance.FromServerException(
                exception,
                "일괄 처리 결과를 모두 확인하지 못했습니다.",
                "이미 성공한 항목, 모든 원천 코멘트와 원래 요청 식별값",
                "'일괄 결과 다시 확인'을 눌러 같은 요청 식별값의 결과만 확인하세요.");
        }
    }

    private async void RetryBulkResultButton_Click(object sender, RoutedEventArgs e)
    {
        if (serverClient is null || lastBulkRequest is null || lastBulkLocalByServerId is null)
        {
            StatusTextBlock.Text = "복구할 일괄 요청이 없습니다.";
            return;
        }
        try
        {
            await ExecuteAndApplyBulkAsync(lastBulkRequest, lastBulkLocalByServerId, "일괄 결과 복구");
        }
        catch (Exception exception) when (exception is InvalidOperationException or HttpRequestException or TaskCanceledException)
        {
            StatusTextBlock.Text = WorkflowFailureGuidance.FromServerException(
                exception,
                "일괄 처리 결과를 다시 확인하지 못했습니다.",
                "이미 성공한 항목, 모든 원천 코멘트와 원래 요청 식별값",
                "서버 연결을 확인한 뒤 같은 버튼을 다시 누르세요.");
        }
    }

    private async Task ExecuteAndApplyBulkAsync(
        ServerFieldCommentBulkReviewRequest request,
        IReadOnlyDictionary<string, FieldCommentReviewRecord> localByServerId,
        string actionLabel)
    {
        if (serverClient is null)
        {
            throw new InvalidOperationException("서버 연결이 필요합니다.");
        }
        var execution = await serverClient.ExecuteFieldCommentBulkReviewAsync(request);
        FieldCommentBulkReviewResultValidator.Validate(execution, request.Items);
        var retryTargetIds = FieldCommentBulkReviewResultValidator.GetRetryTargetIds(execution);
        foreach (var result in execution.Items.Where(item => item.Success == true && item.FieldComment is not null))
        {
            var local = localByServerId[result.CommentId];
            var server = result.FieldComment!;
            fieldComments.ApplyServerReviewResult(
                local.CommentId,
                server.NormalizedContent,
                server.AnalysisContent,
                server.Status,
                server.AssignedTo,
                server.ReviewDueAt,
                server.LastTransitionReason,
                server.ReviewRevision,
                server.ConflictFlag,
                server.ConflictBasis,
                actorName);
        }
        lastBulkRequest = null;
        lastBulkLocalByServerId = null;
        RetryBulkResultButton.IsEnabled = false;
        ReviewChanged = execution.SuccessCount > 0 || ReviewChanged;
        await RefreshQualityIssuesAsync();
        RefreshComments(
            $"{actionLabel} {execution.RequestedCount}건 · 성공 {execution.SuccessCount}건 · 실패 {execution.FailureCount}건. " +
            $"성공 항목은 유지하고 재전송하지 않습니다. 재시도 대상 {retryTargetIds.Count}건만 선택했습니다. " +
            "다음: 항목별 안내를 확인한 뒤 선택된 실패 항목만 다시 처리하세요.");
        SelectBulkRetryTargets(retryTargetIds, localByServerId);
        new FieldCommentBulkPreviewWindow(execution) { Owner = this }.ShowDialog();
    }

    private void SelectBulkRetryTargets(
        IReadOnlyCollection<string> retryTargetIds,
        IReadOnlyDictionary<string, FieldCommentReviewRecord> localByServerId)
    {
        var localIds = retryTargetIds
            .Where(localByServerId.ContainsKey)
            .Select(serverId => localByServerId[serverId].CommentId)
            .ToHashSet(StringComparer.Ordinal);
        FieldCommentGrid.SelectedItems.Clear();
        foreach (var item in workspace.FieldComments.Where(item => localIds.Contains(item.CommentId)))
        {
            FieldCommentGrid.SelectedItems.Add(item);
        }
    }

    private async void TraceabilityButton_Click(object sender, RoutedEventArgs e)
    {
        if (FieldCommentGrid.SelectedItem is not FieldCommentReviewRecord selected)
        {
            StatusTextBlock.Text = "역추적할 FieldComment를 선택하세요.";
            return;
        }
        if (serverClient is null)
        {
            StatusTextBlock.Text = "서버 연결이 없어 역추적 이력을 조회할 수 없습니다.";
            return;
        }
        var serverCommentId = fieldComments.GetServerCommentId(selected.CommentId);
        if (string.IsNullOrWhiteSpace(serverCommentId))
        {
            StatusTextBlock.Text = "아직 서버 FieldComment ID가 연결되지 않았습니다.";
            return;
        }
        try
        {
            var trace = await serverClient.GetFieldCommentTraceabilityAsync(serverCommentId);
            var reportLines = trace.Reports.Count == 0
                ? "보고서 연결 없음"
                : string.Join(Environment.NewLine, trace.Reports.Select(report =>
                    $"- {report.Title} ({report.Status}) → " +
                    (report.GeneratedDocument is null
                        ? "최종 문서 없음"
                        : $"{report.GeneratedDocument.Title} / 버전 {report.GeneratedDocument.GeneratedVersionIds.Count}개")));
            MessageBox.Show(
                this,
                $"원천 hash: {trace.FieldComment.SourceHashSha256}{Environment.NewLine}" +
                $"감사 이력: {trace.Audit.Count}건{Environment.NewLine}" +
                $"보고서 연결: {trace.Reports.Count}건{Environment.NewLine}{reportLines}",
                "FieldComment → 보고서 → 최종 문서 역추적",
                MessageBoxButton.OK,
                MessageBoxImage.Information);
            StatusTextBlock.Text = "서버 감사 이력과 최종 문서 연결을 확인했습니다.";
        }
        catch (Exception exception) when (exception is HttpRequestException or TaskCanceledException or InvalidOperationException)
        {
            StatusTextBlock.Text = BuildPreservedSourceFailureMessage(
                exception,
                "원천 연결을 확인하지 못했습니다.",
                "서버 연결을 확인한 뒤 '원천 연결 확인'을 다시 선택하세요.");
        }
    }

    private void OpenAttachmentButton_Click(object sender, RoutedEventArgs e)
    {
        if (AttachmentGrid.SelectedItem is not FieldCommentAttachmentRecord attachment)
        {
            StatusTextBlock.Text = "열 첨부 파일을 선택하세요.";
            return;
        }

        var path = FlowNoteLocalDatabase.ResolveLocalContentPath(attachment.LocalPath);
        if (!File.Exists(path))
        {
            StatusTextBlock.Text = $"첨부 파일을 찾을 수 없습니다: {path}";
            return;
        }

        Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
    }

    private async Task RefreshQualityIssuesAsync()
    {
        if (serverClient is null)
        {
            qualityIssues = [];
            return;
        }
        try
        {
            var agingDays = int.TryParse(AgingFilterComboBox.SelectedValue?.ToString(), out var selectedDays)
                ? selectedDays
                : 7;
            qualityIssues = await serverClient.ListFieldCommentQualityIssuesAsync(agingDays);
        }
        catch (Exception exception) when (exception is HttpRequestException or TaskCanceledException or InvalidOperationException)
        {
            qualityIssues = [];
            StatusTextBlock.Text = BuildPreservedSourceFailureMessage(
                exception,
                "품질 작업 목록을 확인하지 못했습니다.",
                "서버 연결을 확인한 뒤 목록을 다시 조회하세요.");
        }
    }

    private async void ShowQualityIssuesButton_Click(object sender, RoutedEventArgs e)
    {
        await RefreshQualityIssuesAsync();
        if (qualityIssues.Count == 0)
        {
            StatusTextBlock.Text = "현재 서버 품질 작업함 이슈가 없거나 서버 조회가 불가능합니다.";
            return;
        }
        new FieldCommentQualityIssueWindow(qualityIssues) { Owner = this }.ShowDialog();
    }

    private void RefreshComments(string statusText, string? selectedCommentId = null)
    {
        workspace.FieldComments.Clear();
        var workbench = WorkbenchFilterComboBox.SelectedValue?.ToString();
        var filter = BuildFilter();
        var qualityCommentIds = string.IsNullOrWhiteSpace(filter.QualityIssueType)
            ? null
            : qualityIssues
                .Where(item => item.IssueType == filter.QualityIssueType && !string.IsNullOrWhiteSpace(item.CommentId))
                .Select(item => item.CommentId!)
                .ToHashSet(StringComparer.Ordinal);
        foreach (var comment in fieldComments.ListForReview(filter))
        {
            if (qualityCommentIds is not null)
            {
                var serverCommentId = fieldComments.GetServerCommentId(comment.CommentId);
                if (string.IsNullOrWhiteSpace(serverCommentId) || !qualityCommentIds.Contains(serverCommentId))
                {
                    continue;
                }
            }
            workspace.FieldComments.Add(comment);
        }

        var qualitySummary = string.IsNullOrWhiteSpace(filter.QualityIssueType)
            ? string.Empty
            : $" · 서버 이슈 {qualityIssues.Count(item => item.IssueType == filter.QualityIssueType)}건";
        FilterHintTextBlock.Text =
            $"표시 {workspace.FieldComments.Count}건{qualitySummary} · 상충→기한 초과→담당 없음→근거 누락 순";
        StatusTextBlock.Text = statusText;

        if (!string.IsNullOrWhiteSpace(selectedCommentId))
        {
            FieldCommentGrid.SelectedItem = workspace.FieldComments.FirstOrDefault(item => item.CommentId == selectedCommentId);
        }

        if (FieldCommentGrid.SelectedItem is null)
        {
            FieldCommentGrid.SelectedItem = workspace.FieldComments.FirstOrDefault();
        }

        LoadSelectedComment();
    }

    private FieldCommentReviewFilter BuildFilter()
    {
        var workbench = WorkbenchFilterComboBox.SelectedValue?.ToString();
        return new FieldCommentReviewFilter(
            Status: StatusFilterComboBox.SelectedValue?.ToString(),
            DocumentText: DocumentFilterTextBox.Text,
            AuthorText: AuthorFilterTextBox.Text,
            TagText: TagFilterTextBox.Text,
            AssignedTo: AssignedFilterTextBox.Text,
            LineText: LineFilterTextBox.Text,
            EquipmentText: EquipmentFilterTextBox.Text,
            ProcessText: ProcessFilterTextBox.Text,
            ErrorTypeText: ErrorTypeFilterTextBox.Text,
            OlderThanDays: int.TryParse(AgingFilterComboBox.SelectedValue?.ToString(), out var agingDays) ? agingDays : null,
            HasAttachments: ChoiceToBool(AttachmentFilterComboBox.SelectedValue?.ToString()),
            ReportLinked: workbench == "REPORT_UNLINKED"
                ? false
                : ChoiceToBool(ReportLinkFilterComboBox.SelectedValue?.ToString()),
            Unreviewed: workbench == "UNREVIEWED" ? true : null,
            Overdue: workbench == "OVERDUE" ? true : null,
            Unassigned: workbench == "UNASSIGNED" ? true : null,
            MissingEvidence: workbench == "MISSING_EVIDENCE" ? true : null,
            DuplicateSuspected: workbench == "DUPLICATE_SUSPECTED" ? true : null,
            Conflict: workbench == "CONFLICT" ? true : null,
            QualityIssueType: IsQualityIssueType(workbench) ? workbench : null,
            PriorityOrder: true,
            CreatedFrom: CreatedFromDatePicker.SelectedDate,
            CreatedTo: CreatedToDatePicker.SelectedDate);
    }

    private void ApplyFilter(FieldCommentReviewFilter filter)
    {
        StatusFilterComboBox.SelectedValue = filter.Status ?? "ALL";
        DocumentFilterTextBox.Text = filter.DocumentText ?? string.Empty;
        AuthorFilterTextBox.Text = filter.AuthorText ?? string.Empty;
        TagFilterTextBox.Text = filter.TagText ?? string.Empty;
        AssignedFilterTextBox.Text = filter.AssignedTo ?? string.Empty;
        LineFilterTextBox.Text = filter.LineText ?? string.Empty;
        EquipmentFilterTextBox.Text = filter.EquipmentText ?? string.Empty;
        ProcessFilterTextBox.Text = filter.ProcessText ?? string.Empty;
        ErrorTypeFilterTextBox.Text = filter.ErrorTypeText ?? string.Empty;
        AgingFilterComboBox.SelectedValue = filter.OlderThanDays?.ToString() ?? "ALL";
        AttachmentFilterComboBox.SelectedValue = filter.HasAttachments is true ? "YES" : filter.HasAttachments is false ? "NO" : "ALL";
        ReportLinkFilterComboBox.SelectedValue = filter.ReportLinked is true ? "YES" : filter.ReportLinked is false ? "NO" : "ALL";
        WorkbenchFilterComboBox.SelectedValue = filter.Overdue is true ? "OVERDUE"
            : filter.Conflict is true ? "CONFLICT"
            : filter.Unassigned is true ? "UNASSIGNED"
            : filter.MissingEvidence is true ? "MISSING_EVIDENCE"
            : filter.DuplicateSuspected is true ? "DUPLICATE_SUSPECTED"
            : filter.Unreviewed is true ? "UNREVIEWED"
            : !string.IsNullOrWhiteSpace(filter.QualityIssueType) ? filter.QualityIssueType
            : "ALL";
        CreatedFromDatePicker.SelectedDate = filter.CreatedFrom;
        CreatedToDatePicker.SelectedDate = filter.CreatedTo;
    }

    private void LoadSelectedComment()
    {
        workspace.Attachments.Clear();
        if (FieldCommentGrid.SelectedItem is not FieldCommentReviewRecord selected)
        {
            SelectedTitleTextBlock.Text = "선택된 FieldComment 없음";
            RawContentTextBox.Text = string.Empty;
            NormalizedContentTextBox.Text = string.Empty;
            AnalysisContentTextBox.Text = string.Empty;
            ReviewStatusComboBox.SelectedValue = null;
            TransitionReasonTextBox.Text = string.Empty;
            AssignedToTextBox.Text = string.Empty;
            ReviewDueDatePicker.SelectedDate = null;
            ConflictCheckBox.IsChecked = false;
            ConflictBasisTextBox.Text = string.Empty;
            EvidenceTextBlock.Text = "원천 hash · 첨부 · 문서 버전 · 채널 권한: 서버 조회 전";
            return;
        }

        SelectedTitleTextBlock.Text = $"{selected.DocumentTitle} · {selected.AuthorName} · {FormatStatus(selected.Status)}";
        RawContentTextBox.Text = selected.RawContent;
        NormalizedContentTextBox.Text = selected.NormalizedContent ?? string.Empty;
        AnalysisContentTextBox.Text = selected.AnalysisContent ?? string.Empty;
        ReviewStatusComboBox.SelectedValue = selected.Status;
        TransitionReasonTextBox.Text = string.Empty;
        AssignedToTextBox.Text = selected.AssignedTo ?? string.Empty;
        ReviewDueDatePicker.SelectedDate = selected.ReviewDueAt;
        ConflictCheckBox.IsChecked = selected.ConflictFlag;
        ConflictBasisTextBox.Text = selected.ConflictBasis ?? string.Empty;

        foreach (var attachment in fieldComments.ListAttachments(selected.CommentId))
        {
            workspace.Attachments.Add(attachment);
        }
        _ = LoadServerEvidenceAsync(selected);
    }

    private async Task LoadServerEvidenceAsync(FieldCommentReviewRecord selected)
    {
        var serverCommentId = fieldComments.GetServerCommentId(selected.CommentId);
        if (serverClient is null || string.IsNullOrWhiteSpace(serverCommentId))
        {
            EvidenceTextBlock.Text = $"문서 버전 {selected.DocumentVersionNo?.ToString() ?? "없음"} · 로컬 첨부 {selected.AttachmentCount}건 · 서버 연결 없음";
            return;
        }
        try
        {
            var server = await serverClient.GetFieldCommentAsync(serverCommentId);
            if (FieldCommentGrid.SelectedItem is not FieldCommentReviewRecord current || current.CommentId != selected.CommentId)
            {
                return;
            }
            EvidenceTextBlock.Text = $"hash {server.SourceHashSha256[..Math.Min(12, server.SourceHashSha256.Length)]}… · 첨부 {server.AttachmentCount}건 · 문서 버전 {server.DocumentVersionId ?? "없음"} · 채널 권한 {FormatChannelAccess(server.ChannelAccess)}";
        }
        catch (Exception exception) when (exception is HttpRequestException or TaskCanceledException or InvalidOperationException)
        {
            EvidenceTextBlock.Text = BuildPreservedSourceFailureMessage(
                exception,
                "서버 근거를 표시하지 못했습니다.",
                "서버 연결을 확인한 뒤 같은 코멘트를 다시 선택하세요.");
        }
    }

    private static string BuildPreservedSourceFailureMessage(
        Exception exception,
        string action,
        string retryAction)
    {
        return WorkflowFailureGuidance.FromServerException(
            exception,
            action,
            "원천 코멘트, 기존 검토 이력과 이미 성공한 처리 결과",
            retryAction);
    }

    private static string FormatChannelAccess(string value) => value switch
    {
        "ALLOWED" => "허용",
        "DENIED" => "차단",
        "NOT_LINKED" => "채널 미연결",
        _ => value
    };

    private static string FormatStatus(string status)
    {
        return status switch
        {
            "NEW" => "신규",
            "ASSIGNED" => "담당배정",
            "NEEDS_REVIEW" => "검토필요",
            "ANALYZED" => "분석완료",
            "REVIEWED" => "검토완료",
            "SELECTED" => "보고서선정",
            "EXCLUDED" => "제외",
            "ARCHIVED" => "보관",
            _ => status
        };
    }

    private static bool? ChoiceToBool(string? value) => value switch
    {
        "YES" => true,
        "NO" => false,
        _ => null
    };

    private static bool IsQualityIssueType(string? value) => value is
        "OLD_NEW" or
        "WEAK_SELECTED" or
        "MISSING_REPORT_SOURCE" or
        "INCOMPLETE_REPORT_TRACE" or
        "SOURCE_HASH_MISMATCH" or
        "SOURCE_REVISION_MISMATCH";

    private sealed record StatusOption(string Value, string Label);

    private sealed class ReviewWorkspace
    {
        public ObservableCollection<FieldCommentReviewRecord> FieldComments { get; } = [];

        public ObservableCollection<FieldCommentAttachmentRecord> Attachments { get; } = [];
    }
}
