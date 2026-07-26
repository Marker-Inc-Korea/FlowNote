namespace FlowNote.Windows.Core.Sync;

public sealed record ServerSyncQueueDiagnosis(
    string Category,
    int Priority,
    string PriorityText,
    string OperatorAction,
    bool IsDependencyHold)
{
    public string ResponsibleRole => OperationalState switch
    {
        "보존 구 형식" => "동기화 관리자",
        "선행 조건 대기" => "문서 운영 담당자",
        "수동 조치 필요" => Category is "서버 URL 미설정" or "인증 만료"
            ? "서버 운영 담당자"
            : "문서 운영 담당자",
        "reconciliation 충돌" => "승인 관리자",
        _ => "동기화 운영 담당자"
    };

    public string HandlingDeadline => OperationalState switch
    {
        "보존 구 형식" => "30일 안에 전환 또는 보존 종결 승인",
        "선행 조건 대기" => "다음 동기화 배치 전 선행 ID 확인",
        "수동 조치 필요" => "1영업일 안에 설정·인증·원본 복구",
        "reconciliation 충돌" => "7일 안에 관리자 승인 종결",
        "완료" => "종결",
        _ => "4시간 안에 최대 5회 자동 재시도"
    };

    public int AutoRetryLimit => OperationalState == "재시도 가능" ? 5 : 0;

    public string ManualClosureCriteria => OperationalState switch
    {
        "보존 구 형식" => "원천과 hash를 보존하고 승인자·사유·전환/보존 결정을 기록",
        "reconciliation 충돌" => "양쪽 hash와 관리자 사유·승인자·KEEP_SERVER/RETRY_LOCAL 종결 상태를 기록",
        "수동 조치 필요" => "설정·인증·원본 복구 증거를 확인하거나 복구 불가 사유로 승인 종결",
        "완료" => "SYNCED 또는 승인된 DISCARDED",
        _ => "지원 대상은 SYNCED까지 재시도하며 임의 폐기하지 않음"
    };

    public string OperationalState
    {
        get
        {
            if (Category is "완료")
            {
                return "완료";
            }

            if (Category is "구 FieldNote 큐" or "구 형식 큐")
            {
                return "보존 구 형식";
            }

            if (Category is "문서 충돌")
            {
                return "reconciliation 충돌";
            }

            if (Category is "선행 문서 버전 미동기화" or "선행 문서 미동기화" or
                "선행 FieldComment 미동기화" or "보고서 근거 미동기화")
            {
                return "선행 조건 대기";
            }

            if (Category is "로컬 파일 누락" or "서버 URL 미설정" or "인증 만료" or
                "서버 검증 거부")
            {
                return "수동 조치 필요";
            }

            return "재시도 가능";
        }
    }
}

public static class ServerSyncQueueDiagnostics
{
    public static ServerSyncQueueDiagnosis Classify(
        string status,
        string entityType,
        string action,
        string? lastError)
    {
        if (string.Equals(status, "SYNCED", StringComparison.OrdinalIgnoreCase))
        {
            return new ServerSyncQueueDiagnosis(
                "완료",
                90,
                "90 완료",
                "이미 서버 동기화가 완료된 항목입니다.",
                false);
        }

        if (string.Equals(status, "DISCARDED", StringComparison.OrdinalIgnoreCase))
        {
            return new ServerSyncQueueDiagnosis(
                "관리자 폐기",
                91,
                "91 해결 완료",
                "관리자가 서버본 유지를 선택해 로컬 전송 요청을 폐기한 항목입니다.",
                false);
        }

        if (string.Equals(status, "CONFLICT", StringComparison.OrdinalIgnoreCase))
        {
            return new ServerSyncQueueDiagnosis(
                "문서 충돌",
                5,
                "05 관리자 선택",
                "충돌 작업함에서 서버 최신 기준으로 로컬 변경을 재시도하거나, 사유를 남기고 서버본 유지로 폐기하세요.",
                true);
        }

        if (IsLegacyFieldNote(entityType, action, lastError ?? string.Empty))
        {
            return new ServerSyncQueueDiagnosis(
                "구 FieldNote 큐",
                80,
                "80 별도 정리",
                "구 FieldNote 큐는 현재 FieldComment 동기화 대상이 아닙니다. 관리자 검토 후 FieldComment 전환 또는 별도 마이그레이션으로 정리하세요.",
                true);
        }

        if (IsLegacyCreateAction(action, lastError ?? string.Empty))
        {
            return new ServerSyncQueueDiagnosis(
                "구 형식 큐",
                81,
                "81 별도 전환",
                "현재 서버 동기화 action으로 자동 변환하지 않습니다. 원본 이력을 보존하고 관리자 검토 후 별도 마이그레이션하세요.",
                true);
        }

        if (string.IsNullOrWhiteSpace(lastError))
        {
            return new ServerSyncQueueDiagnosis(
                "재시도 가능",
                50,
                "50 재시도",
                "서버 실행 상태와 로그인 상태를 확인한 뒤 재시도하세요.",
                false);
        }

        if (lastError.Contains("서버 URL", StringComparison.Ordinal))
        {
            return new ServerSyncQueueDiagnosis(
                "서버 URL 미설정",
                10,
                "10 설정 필요",
                "설정 화면에서 서버 URL을 입력하고 다시 로그인한 뒤 재시도하세요.",
                false);
        }

        if (lastError.Contains("로그인", StringComparison.Ordinal) ||
            lastError.Contains("인증", StringComparison.Ordinal))
        {
            return new ServerSyncQueueDiagnosis(
                "인증 만료",
                11,
                "11 로그인 필요",
                "다시 로그인한 뒤 동기화 큐를 재시도하세요.",
                false);
        }

        if (lastError.Contains("연결하지 못했습니다", StringComparison.Ordinal) ||
            lastError.Contains("응답 시간이 초과", StringComparison.Ordinal))
        {
            return new ServerSyncQueueDiagnosis(
                "네트워크 실패",
                12,
                "12 연결 확인",
                "서버 PC 실행 상태, 서버 URL, 네트워크 연결을 확인한 뒤 재시도하세요.",
                false);
        }

        if (lastError.Contains("로컬 파일을 찾을 수 없어", StringComparison.Ordinal))
        {
            return new ServerSyncQueueDiagnosis(
                "로컬 파일 누락",
                20,
                "20 파일 확인",
                "문서 또는 첨부 원본 파일 위치를 복구한 뒤 재시도하세요.",
                true);
        }

        if (lastError.Contains("선행 문서 버전", StringComparison.Ordinal) ||
            lastError.Contains("공개할 서버 버전 ID", StringComparison.Ordinal) ||
            lastError.Contains("공개 버전의 서버 매핑", StringComparison.Ordinal) ||
            lastError.Contains("로컬 공개 버전", StringComparison.Ordinal))
        {
            return new ServerSyncQueueDiagnosis(
                "선행 문서 버전 미동기화",
                31,
                "31 버전 먼저",
                "같은 문서의 버전 전송 또는 공개 전송 항목을 먼저 동기화한 뒤 재시도하세요.",
                true);
        }

        if (lastError.Contains("선행 문서가 아직 서버에 전송", StringComparison.Ordinal))
        {
            return new ServerSyncQueueDiagnosis(
                "선행 문서 미동기화",
                30,
                "30 문서 먼저",
                "같은 문서의 문서 전송 항목을 먼저 동기화한 뒤 재시도하세요.",
                true);
        }

        if (lastError.Contains("선행 FieldComment", StringComparison.Ordinal))
        {
            return new ServerSyncQueueDiagnosis(
                "선행 FieldComment 미동기화",
                32,
                "32 FieldComment 먼저",
                "FieldComment 전송 항목을 먼저 동기화한 뒤 첨부 또는 검토 항목을 재시도하세요.",
                true);
        }

        if (lastError.Contains("보고서 근거", StringComparison.Ordinal))
        {
            return new ServerSyncQueueDiagnosis(
                "보고서 근거 미동기화",
                33,
                "33 근거 먼저",
                "보고서 근거 문서, FieldComment, 작업순서 이력을 먼저 서버에 등록한 뒤 재시도하세요.",
                true);
        }

        if (lastError.Contains("422 Unprocessable Entity", StringComparison.Ordinal) ||
            lastError.Contains("403 Forbidden", StringComparison.Ordinal))
        {
            return new ServerSyncQueueDiagnosis(
                "서버 검증 거부",
                21,
                "21 입력 확인",
                "서버 권위 규칙과 권한을 확인하고 원천 상태를 바로잡거나 관리자 사유로 종결하세요.",
                true);
        }

        return new ServerSyncQueueDiagnosis(
            "실제 서버 오류",
            50,
            "50 재시도",
            "실패 사유를 확인하고 서버 실행 상태, 로그인 상태, 네트워크 상태를 조치한 뒤 재시도하세요.",
            false);
    }

    private static bool IsLegacyFieldNote(string entityType, string action, string lastError)
    {
        return entityType.Contains("field_note", StringComparison.OrdinalIgnoreCase) ||
            action.Contains("field_note", StringComparison.OrdinalIgnoreCase) ||
            lastError.Contains("register_field_note", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsLegacyCreateAction(string action, string lastError)
    {
        return string.Equals(action, "create", StringComparison.OrdinalIgnoreCase) ||
            lastError.Contains("구 형식 create 큐", StringComparison.OrdinalIgnoreCase);
    }
}
