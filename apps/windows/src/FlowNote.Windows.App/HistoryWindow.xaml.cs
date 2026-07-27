using System.Net.Http;
using System.Windows;
using FlowNote.Windows.Core.History;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Sync;

namespace FlowNote.Windows.App;

public partial class HistoryWindow : Window
{
    private readonly HistoryService history;
    private readonly ServerSyncService serverSync;
    private readonly ServerReconciliationService serverReconciliation;
    private readonly FlowNoteServerDocumentClient? serverDocumentClient;
    private readonly string? serverUserId;

    public HistoryWindow(
        HistoryService history,
        ServerSyncService serverSync,
        ServerReconciliationService serverReconciliation,
        FlowNoteServerDocumentClient? serverDocumentClient,
        string? serverUserId)
    {
        InitializeComponent();
        this.history = history;
        this.serverSync = serverSync;
        this.serverReconciliation = serverReconciliation;
        this.serverDocumentClient = serverDocumentClient;
        this.serverUserId = serverUserId;
        RefreshAll();
    }

    private void RefreshAll()
    {
        RefreshHistory();
        RefreshSyncQueue();
        RefreshReconciliation();
    }

    private void RefreshReconciliation()
    {
        var items = serverReconciliation.ListItems()
            .Select(ReconciliationRow.FromRecord)
            .ToList();
        ReconciliationGrid.ItemsSource = items;
        var reviewRun = serverReconciliation.GetLatestReviewRunId();
        var binding = serverDocumentClient is null
            ? null
            : serverReconciliation.GetBinding(serverDocumentClient);
        var guidance = ServerRecoveryGuidance.FromBinding(binding);
        ReconciliationSummaryTextBlock.Text = reviewRun is null
            ? $"재결합 판정 이력 {items.Count}건. 검토 대기 run이 없습니다."
            : $"검토 대기 run: {reviewRun}. REBOUND·REQUEUE·CONFLICT 전 항목을 확인한 뒤 승인 사유를 입력하세요.";
        ReconciliationSummaryTextBlock.Text =
            $"{guidance.Status} {ReconciliationSummaryTextBlock.Text}";
        RecoveryBlockCauseTextBlock.Text = guidance.BlockCause;
        RecoveryPreservedSourcesTextBlock.Text = guidance.PreservedSources;
        RecoveryProhibitedActionsTextBlock.Text = guidance.ProhibitedActions;
        RecoveryNextStepTextBlock.Text = guidance.NextStep;
    }

    private async void CreateReconciliationButton_Click(object sender, RoutedEventArgs e)
    {
        if (serverDocumentClient is null)
        {
            ReconciliationSummaryTextBlock.Text = "서버 연결과 관리자 로그인이 필요합니다. 기존 mapping, cursor, message_id와 큐는 보존됩니다.";
            return;
        }
        try
        {
            var actor = string.IsNullOrWhiteSpace(serverUserId) ? "관리자" : serverUserId!;
            var run = await serverReconciliation.CreateRunAsync(serverDocumentClient, actor);
            RefreshReconciliation();
            ReconciliationSummaryTextBlock.Text = $"{run.RunId} 판정 완료: 전체 {run.Items.Count}건. 관리자 승인 전 서버 mutation은 중지된 상태입니다.";
        }
        catch (Exception exception) when (exception is InvalidOperationException or HttpRequestException)
        {
            RefreshReconciliation();
            ReconciliationSummaryTextBlock.Text = exception.Message;
        }
    }

    private async void ApplyReconciliationButton_Click(object sender, RoutedEventArgs e)
    {
        var runId = serverReconciliation.GetLatestReviewRunId();
        if (serverDocumentClient is null || runId is null)
        {
            ReconciliationSummaryTextBlock.Text = "승인할 검토 대기 run 또는 서버 연결이 없습니다.";
            return;
        }
        var reason = ReconciliationReasonTextBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(reason))
        {
            ReconciliationSummaryTextBlock.Text = "관리자 승인 사유를 입력하세요.";
            return;
        }
        try
        {
            var actor = string.IsNullOrWhiteSpace(serverUserId) ? "관리자" : serverUserId!;
            var run = await serverReconciliation.ApplyRunAsync(
                serverDocumentClient, runId, actor, reason);
            var syncResult = await serverSync.RetryPendingAsync(serverDocumentClient, serverUserId);
            RefreshAll();
            ReconciliationSummaryTextBlock.Text =
                $"{run.RunId} 승인 적용 완료. cursor를 0부터 재추적하며 신규 전송을 재개했습니다. {syncResult.Message}";
        }
        catch (Exception exception) when (exception is InvalidOperationException or HttpRequestException)
        {
            RefreshAll();
            ReconciliationSummaryTextBlock.Text = exception.Message;
        }
    }

    private void RefreshHistory()
    {
        var items = history.ListHistory();
        HistoryGrid.ItemsSource = items;
        SummaryTextBlock.Text = $"전체 이력 {items.Count}건";
    }

    private void RefreshSyncQueue()
    {
        var items = serverSync.ListQueueItems()
            .Select(SyncQueueRow.FromRecord)
            .OrderBy(item => item.Priority)
            .ThenBy(item => item.StatusOrder)
            .ThenByDescending(item => item.LastAttemptAt ?? DateTime.MinValue)
            .ToList();
        SyncQueueGrid.ItemsSource = items;

        var summary = serverSync.GetQueueSummary();
        var metrics = serverSync.GetOperationalMetrics();
        var firstAction = items.FirstOrDefault(item => item.Status != "SYNCED")?.OperatorAction ?? "조치할 항목이 없습니다.";
        SyncQueueSummaryTextBlock.Text =
            $"전체 {summary.Total}건(목록 {items.Count}건 표시), 처리 대기 {metrics.QueueDepth}건, 최장 대기 {metrics.OldestWaitingText}, 최근 1시간 처리 {metrics.SyncedLastHour}건, 실패 분포: {metrics.FailureDistributionText}. 먼저 처리: {firstAction} 로컬 데이터는 삭제되지 않습니다.";
    }

    private void RefreshButton_Click(object sender, RoutedEventArgs e)
    {
        RefreshAll();
    }

    private async void RetrySyncButton_Click(object sender, RoutedEventArgs e)
    {
        if (serverDocumentClient is null)
        {
            RefreshSyncQueue();
            SyncQueueSummaryTextBlock.Text = "서버 URL 또는 로그인 정보가 없어 재시도할 수 없습니다. 설정 화면에서 서버 URL을 입력하고 다시 로그인한 뒤 재시도하세요. 로컬 데이터와 동기화 큐는 삭제되지 않습니다.";
            return;
        }

        var result = await serverSync.RetryPendingAsync(serverDocumentClient, serverUserId);
        RefreshAll();
        SyncQueueSummaryTextBlock.Text = result.Message;
    }

    private async void RetryConflictButton_Click(object sender, RoutedEventArgs e)
    {
        if (SyncQueueGrid.SelectedItem is not SyncQueueRow { Status: "CONFLICT" } selected)
        {
            SyncQueueSummaryTextBlock.Text = "로컬 변경을 다시 보낼 충돌 항목을 선택하세요.";
            return;
        }
        if (serverDocumentClient is null)
        {
            SyncQueueSummaryTextBlock.Text = "서버 연결과 로그인이 필요합니다. 충돌 기록은 로컬 DB에 보존됩니다.";
            return;
        }
        var reason = ConflictReasonTextBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(reason))
        {
            SyncQueueSummaryTextBlock.Text = "관리자 선택 사유를 입력하세요.";
            return;
        }

        try
        {
            var actor = string.IsNullOrWhiteSpace(serverUserId) ? "관리자" : serverUserId;
            var result = await serverSync.RetryConflictUsingLatestServerAsync(
                selected.Id,
                serverDocumentClient,
                actor!,
                reason,
                serverUserId);
            RefreshAll();
            SyncQueueSummaryTextBlock.Text = result.Message;
        }
        catch (InvalidOperationException exception)
        {
            RefreshAll();
            SyncQueueSummaryTextBlock.Text = exception.Message;
        }
    }

    private void DiscardConflictButton_Click(object sender, RoutedEventArgs e)
    {
        if (SyncQueueGrid.SelectedItem is not SyncQueueRow { Status: "CONFLICT" } selected)
        {
            SyncQueueSummaryTextBlock.Text = "서버본 유지로 폐기할 충돌 항목을 선택하세요.";
            return;
        }
        var reason = ConflictReasonTextBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(reason))
        {
            SyncQueueSummaryTextBlock.Text = "폐기 사유를 입력하세요.";
            return;
        }

        try
        {
            serverSync.DiscardConflict(
                selected.Id,
                string.IsNullOrWhiteSpace(serverUserId) ? "관리자" : serverUserId!,
                reason);
            RefreshAll();
            SyncQueueSummaryTextBlock.Text = "서버본 유지로 로컬 전송 요청을 폐기했으며 사유와 감사 이력을 저장했습니다.";
        }
        catch (InvalidOperationException exception)
        {
            RefreshAll();
            SyncQueueSummaryTextBlock.Text = exception.Message;
        }
    }

    private void CloseButton_Click(object sender, RoutedEventArgs e)
    {
        Close();
    }

    private sealed record SyncQueueRow(
        long Id,
        string Status,
        string StatusText,
        int StatusOrder,
        int Priority,
        string PriorityText,
        string OperationalState,
        string Category,
        string EntityText,
        string ActionText,
        int AttemptCount,
        DateTime? LastAttemptAt,
        string OperatorAction,
        bool IsDependencyHold,
        string LastError,
        string ConflictCode)
    {
        public static SyncQueueRow FromRecord(ServerSyncQueueRecord record)
        {
            var diagnosis = record.Diagnosis;
            return new SyncQueueRow(
                record.Id,
                record.Status,
                FormatStatus(record.Status),
                FormatStatusOrder(record.Status),
                diagnosis.Priority,
                diagnosis.PriorityText,
                diagnosis.OperationalState,
                diagnosis.Category,
                $"{FormatEntityType(record.EntityType)} / {record.EntityId}",
                FormatAction(record.Action),
                record.AttemptCount,
                record.LastAttemptAt,
                diagnosis.OperatorAction,
                diagnosis.IsDependencyHold,
                record.LastError ?? "-",
                record.ConflictCode ?? "-");
        }

        private static string FormatStatus(string status)
        {
            return status switch
            {
                "PENDING" => "대기",
                "FAILED" => "실패",
                "SYNCED" => "완료",
                "CONFLICT" => "충돌",
                "DISCARDED" => "폐기",
                _ => status
            };
        }

        private static int FormatStatusOrder(string status)
        {
            return status switch
            {
                "FAILED" => 0,
                "PENDING" => 1,
                "SYNCED" => 2,
                "CONFLICT" => 0,
                "DISCARDED" => 3,
                _ => 3
            };
        }

        private static string FormatEntityType(string entityType)
        {
            return entityType switch
            {
                "document" => "문서",
                "document_version" => "문서 버전",
                "document_publish" => "문서 공개",
                "document_status" => "문서 상태",
                "field_comment" => "FieldComment",
                "field_comment_review" => "FieldComment 검토",
                "field_comment_attachment" => "FieldComment 첨부",
                "document_access_log" => "접근 로그",
                "report" => "보고서",
                "field_note" => "구 FieldNote",
                "field_note_attachment" => "구 FieldNote 첨부",
                "document_view_log" => "구 문서 열람 로그",
                _ => entityType
            };
        }

        private static string FormatAction(string action)
        {
            return action switch
            {
                "register_document" => "문서 전송",
                "register_document_version" => "버전 전송",
                "publish_document_version" => "공개 전송",
                "update_document_status" => "상태 전송",
                "register_field_comment" => "FieldComment 전송",
                "update_field_comment_review" => "FieldComment 검토 전송",
                "register_field_comment_attachment" => "첨부 전송",
                "register_access_log_started" => "열람 시작 전송",
                "register_access_log_closed" => "열람 종료 전송",
                "register_access_log_auto_closed" => "자동 종료 전송",
                "register_access_log_download_blocked" => "다운로드 차단 전송",
                "register_report" => "보고서 서버 저장",
                "register_field_note" => "구 FieldNote 전송",
                "register_field_note_attachment" => "구 FieldNote 첨부 전송",
                "create" => "구 형식 생성 기록",
                _ => action
            };
        }
    }

    private sealed record ReconciliationRow(
        string RunId,
        string VerdictText,
        string ActionText,
        string TargetText,
        string ServerDocumentId,
        string ServerVersionId,
        string Details)
    {
        public static ReconciliationRow FromRecord(LocalReconciliationItem item) => new(
            item.RunId,
            item.Verdict switch
            {
                "CONFIRMED" => "확인",
                "ABSENT" => "없음",
                "DIVERGED" => "불일치",
                _ => item.Verdict
            },
            item.ProposedAction switch
            {
                "REBOUND" => "재결합",
                "REQUEUE" => "재전송",
                "CONFLICT" => "충돌 보존",
                _ => item.ProposedAction
            },
            $"{item.EntityType} / {item.LocalId} / v{item.LocalVersionNo}",
            item.ServerDocumentId ?? "-",
            item.ServerVersionId ?? "-",
            item.Details ?? "-");
    }
}
