namespace FlowNote.Windows.Core.Sync;

public sealed record ServerSyncQueueDiagnosis(
    string Category,
    int Priority,
    string PriorityText,
    string OperatorAction,
    bool IsDependencyHold);

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

        if (string.IsNullOrWhiteSpace(lastError))
        {
            return new ServerSyncQueueDiagnosis(
                "재시도 가능",
                50,
                "50 재시도",
                "서버 실행 상태와 로그인 상태를 확인한 뒤 재시도하세요.",
                false);
        }

        if (IsLegacyFieldNote(entityType, action, lastError))
        {
            return new ServerSyncQueueDiagnosis(
                "구 FieldNote 큐",
                80,
                "80 별도 정리",
                "구 FieldNote 큐는 현재 FieldComment 동기화 대상이 아닙니다. 관리자 검토 후 FieldComment 전환 또는 별도 마이그레이션으로 정리하세요.",
                true);
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
                false);
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

        return new ServerSyncQueueDiagnosis(
            "재시도 가능",
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
}
