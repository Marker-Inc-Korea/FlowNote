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

    private void FieldCommentReviewWindow_Loaded(object sender, RoutedEventArgs e)
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
        foreach (var combo in new[] { AgingFilterComboBox, AttachmentFilterComboBox, ReportLinkFilterComboBox })
        {
            combo.DisplayMemberPath = nameof(StatusOption.Label);
            combo.SelectedValuePath = nameof(StatusOption.Value);
            combo.SelectedValue = "ALL";
        }
        RefreshComments("FieldComment 검토 목록을 조회했습니다.");
    }

    private void RefreshButton_Click(object sender, RoutedEventArgs e)
    {
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
                ReviewDueDatePicker.SelectedDate);
            var syncResult = await serverSync.QueueAndTrySyncFieldCommentReviewAsync(
                updated,
                serverClient,
                serverUserId,
                changedAt);
            ReviewChanged = true;
            RefreshComments(syncResult.Success
                ? $"FieldComment 검토 내용을 저장하고 서버에 반영했습니다: {FormatStatus(status)}"
                : $"FieldComment 검토 내용을 로컬에 저장했습니다: {FormatStatus(status)}. 서버 동기화는 큐에 남겼습니다. {syncResult.Message}",
                selected.CommentId);
        }
        catch (Exception exception) when (exception is InvalidOperationException or ArgumentOutOfRangeException or HttpRequestException or TaskCanceledException)
        {
            StatusTextBlock.Text = $"검토 저장에 실패했습니다. {exception.Message}";
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

        var status = ReviewStatusComboBox.SelectedValue?.ToString();
        if (string.IsNullOrWhiteSpace(status))
        {
            StatusTextBlock.Text = "일괄 변경할 상태를 선택하세요.";
            return;
        }

        try
        {
            var synced = 0;
            foreach (var item in selected)
            {
                var updated = fieldComments.UpdateReview(
                    item.CommentId,
                    NormalizedContentTextBox.Text,
                    AnalysisContentTextBox.Text,
                    status,
                    actorName,
                    TransitionReasonTextBox.Text,
                    AssignedToTextBox.Text,
                    ReviewDueDatePicker.SelectedDate);
                var result = await serverSync.QueueAndTrySyncFieldCommentReviewAsync(
                    updated,
                    serverClient,
                    serverUserId,
                    DateTime.UtcNow);
                if (result.Success)
                {
                    synced++;
                }
            }
            ReviewChanged = true;
            RefreshComments($"선택 {selected.Count}건을 {FormatStatus(status)} 상태로 저장했습니다. 서버 반영 {synced}건.");
        }
        catch (Exception exception) when (exception is InvalidOperationException or ArgumentOutOfRangeException or HttpRequestException or TaskCanceledException)
        {
            StatusTextBlock.Text = $"일괄 검토 저장에 실패했습니다. {exception.Message}";
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

    private void RefreshComments(string statusText, string? selectedCommentId = null)
    {
        workspace.FieldComments.Clear();
        var filter = new FieldCommentReviewFilter(
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
            ReportLinked: ChoiceToBool(ReportLinkFilterComboBox.SelectedValue?.ToString()),
            CreatedFrom: CreatedFromDatePicker.SelectedDate,
            CreatedTo: CreatedToDatePicker.SelectedDate);
        foreach (var comment in fieldComments.ListForReview(filter))
        {
            workspace.FieldComments.Add(comment);
        }

        FilterHintTextBlock.Text = $"표시 {workspace.FieldComments.Count}건 · 보고서선정/검토완료/분석완료는 보고서 후보에서 우선 사용";
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

        foreach (var attachment in fieldComments.ListAttachments(selected.CommentId))
        {
            workspace.Attachments.Add(attachment);
        }
    }

    private static string FormatStatus(string status)
    {
        return status switch
        {
            "NEW" => "신규",
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

    private sealed record StatusOption(string Value, string Label);

    private sealed class ReviewWorkspace
    {
        public ObservableCollection<FieldCommentReviewRecord> FieldComments { get; } = [];

        public ObservableCollection<FieldCommentAttachmentRecord> Attachments { get; } = [];
    }
}
