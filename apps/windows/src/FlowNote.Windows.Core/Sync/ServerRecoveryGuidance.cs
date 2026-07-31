namespace FlowNote.Windows.Core.Sync;

public sealed record ServerRecoveryGuidance(
    string ConnectionStatus,
    string Status,
    string BlockCause,
    string PreservedSources,
    string ProhibitedActions,
    string ResponsibleOwner,
    string EvidenceBinding,
    string NextStep)
{
    public const string RestartConditions =
        "승인 적용만으로 업무를 재개하지 않습니다. 복구 서버 정상 종료 → " +
        "FLOWNOTE_RESTORE_* 장애 표지 제거 → 서버 재시작 → 승인한 instance·epoch의 " +
        "정상 manifest 확인 → 자동 전송·알림 polling 재개 순서가 모두 필요합니다. " +
        "DB·파일·중복 mutation·권한 우회 증거 통과 전에는 안전 수렴 완료로 보지 않습니다.";

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
                "서버 연결 미확인",
                "서버 복구 경계를 아직 확인하지 못했습니다.",
                "서버 연결과 관리자 로그인이 없어 현재 차단 원인을 확정할 수 없습니다.",
                Preserved,
                Prohibited,
                "담당자 미확인",
                "복구 run·백업 세트·복구 승인 ID 미확인",
                "승인된 서버 주소와 로그인을 확인한 뒤 manifest를 다시 조회하세요. " + RejoinStep);
        }
        if (!binding.ReconciliationRequired)
        {
            var convergence = binding.ConvergenceStatus is
                "POST_APPROVAL_RESTART_REQUIRED" or
                "POST_APPROVAL_VERIFICATION_REQUIRED"
                ? "관리자 승인은 적용됐지만 안전 수렴은 아직 별도 검증이 필요합니다."
                : "복구 차단이 없는 정상 운영 상태입니다.";
            return new ServerRecoveryGuidance(
                "서버 연결 확인",
                convergence,
                "복구 경계 차단이 없습니다.",
                Preserved,
                "정상 상태에서도 원천·큐·복구 증거를 임의로 삭제하거나 덮어쓰지 마세요.",
                binding.RestoreResponsibleOwner ?? "일반 운영 담당자",
                FormatEvidenceBinding(binding),
                "자동 전송과 알림 polling 상태를 확인하고 정상 업무를 계속하세요.");
        }

        var faultCode = string.IsNullOrWhiteSpace(binding.RestoreFaultCode)
            ? InferFaultCode(binding.BlockReason)
            : binding.RestoreFaultCode.Trim().ToLowerInvariant();
        var fault = ForFault(faultCode, binding.BlockReason);
        var markerStep = string.IsNullOrWhiteSpace(binding.RestorePilotRunId)
            ? string.Empty
            : " 승인 적용 뒤에는 복구 연습 서버를 정상 종료하고 FLOWNOTE_RESTORE_* " +
              "장애 표지를 제거해 다시 시작한 다음 manifest 정상 여부를 확인하세요.";
        return fault with
        {
            ConnectionStatus = "서버 응답은 확인됐지만 안전 수렴은 확인되지 않았습니다.",
            Status = "복구 경계가 차단되었습니다. 관리자 승인형 재결합이 필요합니다.",
            ResponsibleOwner = binding.RestoreResponsibleOwner ?? "복구 담당자 미지정",
            EvidenceBinding = FormatEvidenceBinding(binding),
            NextStep = fault.NextStep + markerStep
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
            "서버 응답 확인",
            "복구 경계 검토가 필요합니다.",
            cause,
            Preserved,
            Prohibited,
            "복구 담당자 미지정",
            "복구 run·백업 세트·복구 승인 ID 미확인",
            RejoinStep);
    }

    private static string FormatEvidenceBinding(ServerBindingRecord binding) =>
        $"run: {binding.RestorePilotRunId ?? "미확인"} / " +
        $"backup set: {binding.RestoreBackupSetId ?? "미확인"} / " +
        $"복구 승인: {binding.RestoreApprovalId ?? "미확인"}";

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
