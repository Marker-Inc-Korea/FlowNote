using System.Globalization;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using FlowNote.Windows.Core.ServerApi;
using Microsoft.Win32;

namespace FlowNote.Windows.App;

public partial class AIOperationsWindow : Window
{
    private readonly FlowNoteServerAIOperationsClient? client;

    public AIOperationsWindow(FlowNoteServerAIOperationsClient? client)
    {
        InitializeComponent();
        this.client = client;
        Loaded += async (_, _) => await RefreshAsync();
    }

    private async Task RefreshAsync()
    {
        if (client is null) { StatusTextBlock.Text = "서버 URL과 시스템 관리자 로그인이 필요합니다."; return; }
        try
        {
            var policies = await client.ListPoliciesAsync();
            PolicyGrid.ItemsSource = policies;
            ApprovalGrid.ItemsSource = await client.ListApprovalsAsync();
            PromptGrid.ItemsSource = await client.ListPromptsAsync();
            AuditGrid.ItemsSource = await client.ListQueryAuditAsync();
            StatusTextBlock.Text = $"정책 {policies.Count}개와 외부 AI 운영 감사 메타데이터를 조회했습니다.";
        }
        catch (Exception ex) { StatusTextBlock.Text = ex.Message; }
    }

    private async void Refresh_Click(object sender, RoutedEventArgs e) => await RefreshAsync();

    private void PolicyGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (PolicyGrid.SelectedItem is not ServerAIPolicyResponse p) return;
        SelectTag(PolicyScopeComboBox, p.ScopeType); KillSwitchCheckBox.IsChecked = p.KillSwitchEnabled;
        RequestLimitTextBox.Text = p.MaxRequestsPerDay.ToString(); ConcurrencyTextBox.Text = p.MaxConcurrency.ToString();
        TimeoutTextBox.Text = p.TimeoutSeconds.ToString(); CostBudgetTextBox.Text = p.DailyCostBudgetMicros.ToString();
        QueryRetentionTextBox.Text = p.QueryPayloadRetentionDays.ToString(); ResponseRetentionTextBox.Text = p.ResponseRetentionDays.ToString();
        AuditRetentionTextBox.Text = p.AuditRetentionDays.ToString(); AllowExportCheckBox.IsChecked = p.AllowAuditExport;
        PolicyReasonTextBox.Text = p.Reason;
    }

    private async void SavePolicy_Click(object sender, RoutedEventArgs e)
    {
        if (client is null) return;
        if (!TryInt(RequestLimitTextBox, out var requests) || !TryInt(ConcurrencyTextBox, out var concurrency) ||
            !TryInt(TimeoutTextBox, out var timeout) || !long.TryParse(CostBudgetTextBox.Text, out var cost) ||
            !TryInt(QueryRetentionTextBox, out var queryDays) || !TryInt(ResponseRetentionTextBox, out var responseDays) ||
            !TryInt(AuditRetentionTextBox, out var auditDays) || string.IsNullOrWhiteSpace(PolicyReasonTextBox.Text))
        { StatusTextBlock.Text = "모든 한도와 변경 사유를 올바르게 입력하세요."; return; }
        try
        {
            await client.SavePolicyAsync(new ServerAIPolicyUpdateRequest { ScopeType = SelectedTag(PolicyScopeComboBox), KillSwitchEnabled = KillSwitchCheckBox.IsChecked == true,
                MaxRequestsPerDay = requests, MaxConcurrency = concurrency, TimeoutSeconds = timeout, DailyCostBudgetMicros = cost,
                QueryPayloadRetentionDays = queryDays, ResponseRetentionDays = responseDays, AuditRetentionDays = auditDays,
                AllowAuditExport = AllowExportCheckBox.IsChecked == true, Reason = PolicyReasonTextBox.Text.Trim() });
            await RefreshAsync(); StatusTextBlock.Text = "외부 AI 운영 정책을 저장하고 감사 이력을 남겼습니다.";
        } catch (Exception ex) { StatusTextBlock.Text = ex.Message; }
    }

    private async void CreateApproval_Click(object sender, RoutedEventArgs e)
    {
        if (client is null) return;
        if (!DateTimeOffset.TryParse(ApprovalExpiryTextBox.Text, CultureInfo.CurrentCulture, DateTimeStyles.AssumeLocal, out var expires))
        { StatusTextBlock.Text = "승인 만료 날짜를 확인하세요."; return; }
        try
        {
            await client.CreateApprovalAsync(new ServerAIApprovalCreateRequest { CustomerScope = ApprovalCustomerTextBox.Text.Trim(), SiteScope = ApprovalSiteTextBox.Text.Trim(),
                Provider = ApprovalProviderTextBox.Text.Trim(), ModelScope = ApprovalModelTextBox.Text.Trim(), ExpiresAt = expires,
                Purposes = Split(ApprovalPurposeTextBox.Text), SourceTypes = Split(ApprovalSourcesTextBox.Text),
                DataHandlingPolicyVersion = ApprovalPolicyVersionTextBox.Text.Trim(), Reason = ApprovalReasonTextBox.Text.Trim() });
            await RefreshAsync(); StatusTextBlock.Text = "범위가 고정된 전송 승인을 생성했습니다.";
        } catch (Exception ex) { StatusTextBlock.Text = ex.Message; }
    }

    private async void RevokeApproval_Click(object sender, RoutedEventArgs e)
    {
        if (client is null || ApprovalGrid.SelectedItem is not ServerAIApprovalResponse selected) { StatusTextBlock.Text = "폐기할 승인을 선택하세요."; return; }
        try { await client.RevokeApprovalAsync(selected.ApprovalId, ApprovalReasonTextBox.Text.Trim()); await RefreshAsync(); StatusTextBlock.Text = "승인을 즉시 폐기했습니다."; }
        catch (Exception ex) { StatusTextBlock.Text = ex.Message; }
    }

    private void PromptGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (PromptGrid.SelectedItem is not ServerAIPromptResponse p) return;
        PromptNameTextBox.Text = p.Name; PromptVersionTextBox.Text = p.Version; PromptTemplateTextBox.Text = p.TemplateText;
        SelectTag(PromptPurposeComboBox, p.AllowedPurpose);
    }

    private async void CreatePrompt_Click(object sender, RoutedEventArgs e)
    {
        if (client is null) return;
        try { await client.CreatePromptAsync(new ServerAIPromptCreateRequest { Name = PromptNameTextBox.Text.Trim(), Version = PromptVersionTextBox.Text.Trim(),
            TemplateText = PromptTemplateTextBox.Text, AllowedPurpose = SelectedTag(PromptPurposeComboBox) }); await RefreshAsync(); StatusTextBlock.Text = "새 불변 프롬프트 버전을 등록했습니다."; }
        catch (Exception ex) { StatusTextBlock.Text = ex.Message; }
    }

    private async void PromptAction_Click(object sender, RoutedEventArgs e)
    {
        if (client is null || PromptGrid.SelectedItem is not ServerAIPromptResponse selected || sender is not Button { Tag: string action })
        { StatusTextBlock.Text = "상태를 변경할 프롬프트를 선택하세요."; return; }
        try { await client.ChangePromptAsync(selected.PromptVersionId, action, PromptReasonTextBox.Text.Trim()); await RefreshAsync(); StatusTextBlock.Text = "프롬프트 lifecycle 상태를 변경했습니다."; }
        catch (Exception ex) { StatusTextBlock.Text = ex.Message; }
    }

    private async void ExportAudit_Click(object sender, RoutedEventArgs e)
    {
        if (client is null) return;
        var dialog = new SaveFileDialog { Filter = "CSV 파일 (*.csv)|*.csv", FileName = $"FlowNote-AI-감사-{DateTime.Now:yyyyMMdd-HHmmss}.csv" };
        if (dialog.ShowDialog(this) != true) return;
        try { await File.WriteAllBytesAsync(dialog.FileName, await client.ExportAuditAsync()); StatusTextBlock.Text = "정책에 따라 원문 없는 감사 메타데이터를 내보냈습니다."; }
        catch (Exception ex) { StatusTextBlock.Text = ex.Message; }
    }

    private async void RunRetention_Click(object sender, RoutedEventArgs e)
    {
        if (client is null) return;
        try { var result = await client.RunRetentionAsync(); await RefreshAsync(); StatusTextBlock.Text = $"보존 작업 완료: 질의 비식별화 {result.QueryPayloadsDeidentified}건, 응답 삭제 {result.ResponsesDeleted}건"; }
        catch (Exception ex) { StatusTextBlock.Text = ex.Message; }
    }

    private static List<string> Split(string value) => value.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).ToList();
    private static bool TryInt(TextBox box, out int value) => int.TryParse(box.Text, out value) && value >= 0;
    private static string SelectedTag(ComboBox box) => (box.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? string.Empty;
    private static void SelectTag(ComboBox box, string value) { foreach (var item in box.Items.OfType<ComboBoxItem>()) if (string.Equals(item.Tag?.ToString(), value, StringComparison.Ordinal)) { box.SelectedItem = item; break; } }
}
