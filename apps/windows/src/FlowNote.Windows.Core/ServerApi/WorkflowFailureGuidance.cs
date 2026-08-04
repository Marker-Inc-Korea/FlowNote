namespace FlowNote.Windows.Core.ServerApi;

public static class WorkflowFailureGuidance
{
    public static string FromOutcome<T>(MutationOutcome<T> outcome) =>
        Format(
            outcome.Message,
            outcome.SourcePreserved ? "원천 데이터와 이미 완료된 변경" : "원천 데이터 보존 여부를 확인해야 합니다.",
            outcome.ResponsibleRole ?? "현재 사용자",
            outcome.ActionRoute is null
                ? "오류 내용을 확인한 뒤 다시 시도하세요."
                : $"안내된 화면에서 실패 항목만 처리하세요: {outcome.ActionRoute}");

    public static string Format(
        string failure,
        string preserved,
        string owner,
        string nextAction) =>
        $"무엇이 실패했는지: {failure}{Environment.NewLine}" +
        $"무엇이 보존됐는지: {preserved}{Environment.NewLine}" +
        $"누가 처리해야 하는지: {owner}{Environment.NewLine}" +
        $"사용자가 지금 할 수 있는 일: {nextAction}";

    public static string FromServerException(
        Exception exception,
        string failedAction,
        string preserved,
        string retryAction)
    {
        return exception switch
        {
            FlowNoteServerAuthenticationException => Format(
                $"로그인이 만료되어 {failedAction}",
                preserved,
                "현재 사용자",
                "다시 로그인한 뒤 같은 작업을 실행하세요."),
            FlowNoteServerAccessException => Format(
                $"현재 계정 권한이 부족해 {failedAction}",
                preserved,
                "현장 관리자",
                "현장 관리자에게 로그인 ID와 필요한 업무 권한을 전달하세요."),
            FlowNoteServerConflictException => Format(
                $"서버 최신 revision과 달라 {failedAction}",
                preserved,
                "현재 사용자와 검토 담당자",
                "목록을 다시 조회해 서버 원문과 로컬 입력을 비교한 뒤 적용할 내용을 다시 선택하세요."),
            HttpRequestException or TaskCanceledException => Format(
                $"서버 연결이 끊겨 {failedAction}",
                preserved,
                "현재 사용자",
                retryAction),
            _ => Format(
                failedAction,
                preserved,
                "현재 사용자",
                retryAction)
        };
    }
}
