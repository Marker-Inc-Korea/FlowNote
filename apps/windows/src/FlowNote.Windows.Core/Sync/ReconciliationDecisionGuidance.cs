namespace FlowNote.Windows.Core.Sync;

public static class ReconciliationDecisionGuidance
{
    public const string VerdictGuide =
        "CONFIRMED: 서버에서 같은 idempotency 원천을 확인했습니다. 같은 mutation을 다시 보내지 않습니다.\n" +
        "ABSENT: 서버에 해당 원천이 없습니다. 로컬 원천과 큐를 보존한 채 재전송 후보로 둡니다.\n" +
        "DIVERGED: 서버와 로컬의 hash 또는 revision이 다릅니다. 어느 쪽도 자동으로 덮어쓰지 않습니다.";

    public const string ActionGuide =
        "REBOUND: 서버 문서·버전 ID로 매핑을 다시 연결하고 해당 큐를 전송 완료로 기록합니다.\n" +
        "REQUEUE: 기존 서버 매핑을 해제하고 로컬 원천을 PENDING으로 돌려 정상 manifest 확인 뒤 다시 보냅니다.\n" +
        "CONFLICT: 자동 전송을 종결하고 양쪽 hash, 상세 내용, 승인자와 사유를 보존해 별도로 해결합니다.";

    public const string FullGuide = VerdictGuide + "\n" + ActionGuide;

    public static string VerdictText(string verdict) => verdict switch
    {
        "CONFIRMED" => "CONFIRMED · 서버 동일 원천 확인",
        "ABSENT" => "ABSENT · 서버 원천 없음",
        "DIVERGED" => "DIVERGED · 양쪽 원천 불일치",
        _ => verdict
    };

    public static string ActionText(string action) => action switch
    {
        "REBOUND" => "REBOUND · 서버 매핑 재연결",
        "REQUEUE" => "REQUEUE · 로컬 원천 재전송 대기",
        "CONFLICT" => "CONFLICT · 자동 전송 중지·충돌 보존",
        _ => action
    };

    public static string DataEffect(string action) => action switch
    {
        "REBOUND" =>
            "서버 ID 매핑과 큐 상태를 갱신합니다. 로컬 원천과 기존 큐·감사 이력은 삭제하지 않습니다.",
        "REQUEUE" =>
            "서버 매핑을 해제하고 큐를 PENDING으로 되돌립니다. 정상 manifest 확인 전에는 전송하지 않습니다.",
        "CONFLICT" =>
            "큐의 자동 전송을 종결하고 양쪽 hash와 승인 사유를 보존합니다. 원천 파일은 삭제하지 않습니다.",
        _ => "지원 여부를 확인할 수 없는 조치입니다. 승인하지 말고 서버 판정을 다시 확인하세요."
    };

    public static string BuildImpactSummary(
        IReadOnlyCollection<LocalReconciliationItem> items)
    {
        var rebound = items.Count(item => item.ProposedAction == "REBOUND");
        var requeue = items.Count(item => item.ProposedAction == "REQUEUE");
        var conflict = items.Count(item => item.ProposedAction == "CONFLICT");
        return
            $"상태·매핑 변경 대상 {items.Count}건 · 원천 보존 {items.Count}건 · " +
            $"충돌 격리 {conflict}건\n" +
            $"REBOUND {rebound}건 / REQUEUE {requeue}건 / CONFLICT {conflict}건. " +
            "로컬 원천, 기존 큐, 양쪽 hash와 감사 이력은 삭제하지 않습니다.";
    }

    public static string BuildApprovalSummary(
        string runId,
        IReadOnlyCollection<LocalReconciliationItem> items)
    {
        var counts = items
            .GroupBy(item => $"{item.Verdict} → {item.ProposedAction}")
            .OrderBy(group => group.Key, StringComparer.Ordinal)
            .Select(group => $"{group.Key} {group.Count()}건");
        var countSummary = items.Count == 0
            ? "판정 항목 없음"
            : string.Join(", ", counts);
        return
            $"run {runId}의 {items.Count}건을 승인합니다.\n" +
            $"{countSummary}\n" +
            $"{BuildImpactSummary(items)}\n\n" +
            "승인하면 서버 제안 조치를 한 transaction으로 적용합니다. " +
            "REBOUND는 매핑을 다시 연결하고, REQUEUE는 로컬 원천을 재전송 대기로 돌리며, " +
            "CONFLICT는 자동 전송을 종결하고 양쪽 원천과 승인 사유를 보존합니다. " +
            "DIVERGED 항목은 표의 로컬·서버 SHA-256을 승인 전에 대조하세요.\n\n" +
            "승인 적용과 감사 이력은 이 화면에서 되돌릴 수 없습니다. 원천은 삭제하지 않지만 " +
            "다시 판정하려면 별도 운영 절차와 새 run이 필요합니다.\n\n" +
            "승인 뒤에도 서버 정상 종료 → FLOWNOTE_RESTORE_* 표지 제거 → 서버 재시작 → " +
            "정상 manifest 확인 전에는 자동 전송과 알림 polling이 차단됩니다.";
    }
}
