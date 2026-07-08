using System.Windows;
using FlowNote.Windows.Core.History;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Sync;

namespace FlowNote.Windows.App;

public partial class HistoryWindow : Window
{
    private readonly HistoryService history;
    private readonly ServerSyncService serverSync;
    private readonly FlowNoteServerDocumentClient? serverDocumentClient;
    private readonly string? serverUserId;

    public HistoryWindow(
        HistoryService history,
        ServerSyncService serverSync,
        FlowNoteServerDocumentClient? serverDocumentClient,
        string? serverUserId)
    {
        InitializeComponent();
        this.history = history;
        this.serverSync = serverSync;
        this.serverDocumentClient = serverDocumentClient;
        this.serverUserId = serverUserId;
        RefreshAll();
    }

    private void RefreshAll()
    {
        RefreshHistory();
        RefreshSyncQueue();
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

        var pendingCount = items.Count(item => item.Status == "PENDING");
        var failedCount = items.Count(item => item.Status == "FAILED");
        var syncedCount = items.Count(item => item.Status == "SYNCED");
        var holdCount = items.Count(item => item.IsDependencyHold && item.Status != "SYNCED");
        var firstAction = items.FirstOrDefault(item => item.Status != "SYNCED")?.OperatorAction ?? "조치할 항목이 없습니다.";
        SyncQueueSummaryTextBlock.Text =
            $"대기 {pendingCount}건, 실패 {failedCount}건, 보류 {holdCount}건, 완료 {syncedCount}건. 먼저 처리: {firstAction} 로컬 데이터는 삭제되지 않습니다.";
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

    private void CloseButton_Click(object sender, RoutedEventArgs e)
    {
        Close();
    }

    private sealed record SyncQueueRow(
        string Status,
        string StatusText,
        int StatusOrder,
        int Priority,
        string PriorityText,
        string Category,
        string EntityText,
        string ActionText,
        int AttemptCount,
        DateTime? LastAttemptAt,
        string OperatorAction,
        bool IsDependencyHold,
        string LastError)
    {
        public static SyncQueueRow FromRecord(ServerSyncQueueRecord record)
        {
            var diagnosis = record.Diagnosis;
            return new SyncQueueRow(
                record.Status,
                FormatStatus(record.Status),
                FormatStatusOrder(record.Status),
                diagnosis.Priority,
                diagnosis.PriorityText,
                diagnosis.Category,
                $"{FormatEntityType(record.EntityType)} / {record.EntityId}",
                FormatAction(record.Action),
                record.AttemptCount,
                record.LastAttemptAt,
                diagnosis.OperatorAction,
                diagnosis.IsDependencyHold,
                record.LastError ?? "-");
        }

        private static string FormatStatus(string status)
        {
            return status switch
            {
                "PENDING" => "대기",
                "FAILED" => "실패",
                "SYNCED" => "완료",
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
                _ => action
            };
        }
    }
}
