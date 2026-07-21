using FlowNote.Windows.Core.ServerApi;

namespace FlowNote.Windows.Core.WorkSequences;

public static class WorkSequenceServerPolicy
{
    public const string OfflineReadOnlyMessage =
        "서버 미연결: 기존 로컬 작업순서는 읽기 캐시/초안입니다. 확정 생성, 순서 변경, 상태 변경을 할 수 없습니다.";

    public const string StaleRevisionMessage =
        "다른 사용자가 작업순서를 먼저 변경했습니다. 서버 최신 내용을 새로고침했습니다. 내용을 확인한 뒤 다시 시도하세요.";

    public static bool CanMutate(FlowNoteServerDocumentClient? serverClient, bool hasAuthoritativeSnapshot) =>
        serverClient is not null && hasAuthoritativeSnapshot;

    public static string ConflictMessage(FlowNoteServerConflictException exception) =>
        string.Equals(exception.ConflictCode, "WORK_SEQUENCE_STALE_REVISION", StringComparison.Ordinal)
            ? StaleRevisionMessage
            : exception.Message;

    public static async Task<T> RunWithResponseLossRetryAsync<T>(Func<Task<T>> action)
    {
        try
        {
            return await action();
        }
        catch (Exception exception) when (exception is HttpRequestException or TaskCanceledException)
        {
            return await action();
        }
    }
}
