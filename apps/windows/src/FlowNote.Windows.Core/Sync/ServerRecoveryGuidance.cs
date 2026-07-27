namespace FlowNote.Windows.Core.Sync;

public sealed record ServerRecoveryGuidance(
    string Status,
    string BlockCause,
    string PreservedSources,
    string ProhibitedActions,
    string NextStep)
{
    private const string Preserved =
        "로컬 문서·FieldComment·보고서 원천과 Files, 동기화 큐, 서버 ID 매핑, " +
        "알림 cursor, 처리한 message_id, 실패·재결합 이력을 그대로 보존합니다.";

    private const string Prohibited =
        "관리자 승인 전에는 자동 전송, 알림 polling, cursor 단독 초기화, " +
        "서버 ID 매핑 교체, 실패 증거 삭제·덮어쓰기를 할 수 없습니다.";

    private const string RejoinStep =
        "DB와 파일이 같은 backup-set-id·restore-approval-id인지 비교한 뒤 " +
        "판정 실행 → 모든 REBOUND·REQUEUE·CONFLICT 검토 → 승인 사유 입력 → 승인 적용 순서로 진행하세요.";

    public static ServerRecoveryGuidance FromBinding(ServerBindingRecord? binding)
    {
        if (binding is null)
        {
            return new ServerRecoveryGuidance(
                "서버 복구 경계를 아직 확인하지 못했습니다.",
                "서버 연결과 관리자 로그인이 없어 현재 차단 원인을 확정할 수 없습니다.",
                Preserved,
                Prohibited,
                "승인된 서버 주소와 로그인을 확인한 뒤 manifest를 다시 조회하세요. " + RejoinStep);
        }
        if (!binding.ReconciliationRequired)
        {
            return new ServerRecoveryGuidance(
                "현재 서버 binding은 정상입니다.",
                "복구 경계 차단이 없습니다.",
                Preserved,
                "정상 상태에서도 원천·큐·복구 증거를 임의로 삭제하거나 덮어쓰지 마세요.",
                "자동 전송과 알림 polling 상태를 확인하고 정상 업무를 계속하세요.");
        }

        var faultCode = InferFaultCode(binding.BlockReason);
        var fault = ForFault(faultCode, binding.BlockReason);
        return fault with
        {
            Status = "복구 경계가 차단되었습니다. 관리자 승인형 재결합이 필요합니다."
        };
    }

    public static ServerRecoveryGuidance ForFault(string faultCode, string? detail = null)
    {
        var cause = faultCode switch
        {
            "partial_restore" =>
                "DB 또는 파일 원천 중 일부만 복원된 부분 복구가 감지되었습니다.",
            "old_database_new_files" =>
                "이전 시점 DB와 더 새로운 파일 원천이 결합된 상태가 감지되었습니다.",
            "missing_file" =>
                "DB가 참조하는 원천 파일이 복구 파일 집합에 없습니다.",
            "wrong_server_epoch" =>
                "승인된 복구 경계와 다른 서버 epoch가 감지되었습니다.",
            _ =>
                "서버 instance·URL·epoch 또는 알림 cursor가 기존 binding과 다릅니다."
        };
        if (!string.IsNullOrWhiteSpace(detail))
        {
            cause = $"{cause} 확인 내용: {detail.Trim()}";
        }
        return new ServerRecoveryGuidance(
            "복구 경계 검토가 필요합니다.",
            cause,
            Preserved,
            Prohibited,
            RejoinStep);
    }

    public static string InferFaultCode(string? reason)
    {
        if (string.IsNullOrWhiteSpace(reason))
        {
            return "partial_restore";
        }
        if (reason.Contains("파일", StringComparison.Ordinal))
        {
            return "missing_file";
        }
        if (reason.Contains("cursor", StringComparison.OrdinalIgnoreCase))
        {
            return "old_database_new_files";
        }
        if (reason.Contains("epoch", StringComparison.OrdinalIgnoreCase))
        {
            return "wrong_server_epoch";
        }
        return "partial_restore";
    }
}
