using System.Security.Authentication;

namespace FlowNote.Windows.Core.ServerApi;

public static class ServerConnectionGuidance
{
    public const string InvalidServerAddressMessage =
        "서버 주소 설정이 올바르지 않아 로그인하지 않았습니다. " +
        "현장 관리자에게 FLOWNOTE_API_BASE_URL의 HTTPS 주소를 확인해 달라고 요청한 뒤 FlowNote를 다시 실행하세요. " +
        "로컬 데이터와 동기화 대기 기록은 삭제되지 않습니다.";

    public const string CertificateFailureMessage =
        "서버 보안 인증서를 확인할 수 없어 로그인하지 않았습니다. " +
        "PC 날짜와 시간을 먼저 확인하고, FLOWNOTE_API_BASE_URL이 인증서의 운영 서버 이름과 같은지 확인하세요. " +
        "계속 실패하면 현장 관리자에게 인증서 갱신 상태와 사내 인증서 신뢰 배포를 요청하세요. " +
        "보안 오류이므로 HTTP나 로컬 계정으로 자동 전환하지 않으며 로컬 데이터는 보존됩니다.";

    public const string TimeoutMessage =
        "서버 응답 시간이 초과되어 로그인하지 않았습니다. " +
        "네트워크 연결과 서버 재부팅 여부를 확인한 뒤 다시 시도하세요. " +
        "서버 주소가 바뀌었다면 현장 관리자에게 새 HTTPS 주소와 방화벽 적용 여부를 확인해 달라고 요청하세요. " +
        "로컬 데이터와 동기화 대기 기록은 삭제되지 않습니다.";

    public const string UnreachableMessage =
        "서버에 연결할 수 없어 로그인하지 않았습니다. " +
        "네트워크와 방화벽을 확인하고, FLOWNOTE_API_BASE_URL이 현재 운영 서버의 HTTPS 주소인지 확인하세요. " +
        "서버 주소가 변경됐다면 설정을 바꾼 뒤 FlowNote를 다시 실행하세요. " +
        "로컬 데이터와 동기화 대기 기록은 삭제되지 않습니다.";

    public static string LoginFailure(Exception exception)
    {
        if (Contains<AuthenticationException>(exception))
        {
            return CertificateFailureMessage;
        }

        return exception is TaskCanceledException or TimeoutException
            ? TimeoutMessage
            : UnreachableMessage;
    }

    public static string ReconnectFailure(Exception exception)
    {
        if (Contains<AuthenticationException>(exception))
        {
            return CertificateFailureMessage;
        }

        return exception is TaskCanceledException or TimeoutException
            ? "서버 응답이 늦어 재연결을 기다리고 있습니다. 네트워크와 서버 상태를 확인하세요. " +
              "로컬 기록과 마지막 알림 위치는 보존되며 연결 복구 후 이어서 처리합니다."
            : "서버 연결이 끊겨 재연결을 기다리고 있습니다. 네트워크·방화벽과 현재 서버 주소를 확인하세요. " +
              "주소가 변경됐다면 FLOWNOTE_API_BASE_URL을 바꾸고 FlowNote를 다시 실행하세요. " +
              "로컬 기록과 마지막 알림 위치는 보존됩니다.";
    }

    private static bool Contains<TException>(Exception exception)
        where TException : Exception
    {
        for (var current = exception; current is not null; current = current.InnerException)
        {
            if (current is TException)
            {
                return true;
            }
        }

        return false;
    }
}
