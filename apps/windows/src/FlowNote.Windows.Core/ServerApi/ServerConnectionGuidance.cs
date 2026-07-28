using System.Security.Authentication;

namespace FlowNote.Windows.Core.ServerApi;

public static class ServerConnectionGuidance
{
    public const string InvalidServerAddressMessage =
        "서버 주소 설정이 올바르지 않아 로그인하지 않았습니다.\n" +
        "누락 항목: 승인된 FlowNote HTTPS 서버 주소\n" +
        "보존된 데이터: 로컬 DB, 고객 파일, 동기화 대기 기록은 삭제되지 않았습니다.\n" +
        "담당자: 현장 관리자 또는 서버 운영 담당자\n" +
        "다음 조치: FLOWNOTE_API_BASE_URL을 승인된 HTTPS 주소로 수정한 뒤 FlowNote를 다시 실행하세요.";

    public const string CertificateFailureMessage =
        "서버 보안 인증서를 확인할 수 없어 로그인하지 않았습니다.\n" +
        "누락 항목: 신뢰할 수 있는 서버 인증서, 올바른 서버 이름 또는 정확한 PC 날짜와 시간\n" +
        "보존된 데이터: 로컬 DB, 고객 파일, 동기화 대기 기록은 삭제되지 않았습니다. HTTP나 로컬 계정으로 자동 전환하지 않습니다.\n" +
        "담당자: 서버·인증서 운영 담당자\n" +
        "다음 조치: PC 날짜·시간과 HTTPS 서버 이름을 확인하고, 계속 실패하면 인증서 갱신과 사내 신뢰 인증서 배포를 요청하세요.";

    public const string TimeoutMessage =
        "서버 응답 시간이 초과되어 로그인하지 않았습니다.\n" +
        "누락 항목: 응답 가능한 FlowNote 서버 연결\n" +
        "보존된 데이터: 로컬 DB, 고객 파일, 동기화 대기 기록은 삭제되지 않았습니다.\n" +
        "담당자: 현장 관리자 또는 서버·네트워크 운영 담당자\n" +
        "다음 조치: 네트워크, 서버 재부팅 상태, 새 HTTPS 주소와 방화벽 적용 여부를 확인한 뒤 다시 로그인하세요.";

    public const string UnreachableMessage =
        "서버에 연결할 수 없어 로그인하지 않았습니다.\n" +
        "누락 항목: 현재 운영 서버로 연결되는 네트워크·방화벽·HTTPS 주소\n" +
        "보존된 데이터: 로컬 DB, 고객 파일, 동기화 대기 기록은 삭제되지 않았습니다.\n" +
        "담당자: 현장 관리자 또는 서버·네트워크 운영 담당자\n" +
        "다음 조치: FLOWNOTE_API_BASE_URL과 네트워크·방화벽을 확인하고, 주소가 바뀌었다면 수정한 뒤 FlowNote를 다시 실행하세요.";

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
