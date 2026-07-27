using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Storage;

internal static class ServerSmokeReconciliation
{
    private static readonly HashSet<string> AllowedActions =
    [
        "REBOUND",
        "REQUEUE",
        "CONFLICT"
    ];

    public static async Task ApproveIfRequiredAsync(
        FlowNoteLocalServices services,
        FlowNoteServerDocumentClient client,
        string administratorUserId,
        string runId)
    {
        RequireTestEnvironment();
        var binding = services.ServerReconciliation.GetBinding(client);
        if (binding is null || !binding.ReconciliationRequired)
        {
            return;
        }

        var run = await services.ServerReconciliation.CreateRunAsync(
            client,
            administratorUserId);
        if (run.Status != "REVIEW_REQUIRED" ||
            run.Items.Any(item => !AllowedActions.Contains(item.ProposedAction)))
        {
            throw new InvalidOperationException(
                "스모크 서버 재결합 판정에 검토할 수 없는 항목이 있습니다.");
        }

        var applied = await services.ServerReconciliation.ApplyRunAsync(
            client,
            run.RunId,
            administratorUserId,
            $"통합 스모크 서버 instance 변경 승인 run={runId}");
        if (applied.Status != "APPLIED")
        {
            throw new InvalidOperationException(
                "스모크 서버 재결합 승인이 적용되지 않았습니다.");
        }

        Console.WriteLine(
            $"Server reconciliation smoke: run={runId}, reconciliation={run.RunId}, " +
            $"items={run.Items.Count}, status={applied.Status}");
    }

    private static void RequireTestEnvironment()
    {
        if (!string.Equals(
                Environment.GetEnvironmentVariable("FLOWNOTE_ENVIRONMENT"),
                "test",
                StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException(
                "스모크 서버 재결합 승인은 FLOWNOTE_ENVIRONMENT=test에서만 허용됩니다.");
        }
    }
}
