using System.Security.Authentication;

namespace FlowNote.Windows.Core.ServerApi;

public static class ServerConnectionGuidance
{
    private const string PreservedLocalState =
        "로컬 문서·FieldComment·보고서 원천과 Files, 동기화 큐, 알림 cursor, " +
        "처리한 message_id와 마지막 정상 위치를 삭제·초기화·덮어쓰지 않습니다.";

    public const string InvalidServerAddressMessage =
        "실패 내용: 설정된 서버 주소가 승인된 FlowNote HTTPS 주소 형식과 일치하지 않아 로그인하지 않았습니다.\n" +
        "누락 항목: 승인된 FlowNote HTTPS 서버 주소\n" +
        "보존된 로컬 상태: " + PreservedLocalState + "\n" +
        "처리 담당자: 현장 관리자 또는 서버 운영 담당자\n" +
        "가능한 다음 행동: FLOWNOTE_API_BASE_URL, 승인 DNS 이름과 포트를 대조해 수정한 뒤 FlowNote를 다시 실행하세요. 주소가 확인되기 전에는 로컬 로그인이나 HTTP로 우회하지 마세요.";

    public const string CertificateFailureMessage =
        "실패 내용: 서버 인증서가 폐기됐거나 인증서 chain·서버 이름·유효기간·폐기 확인에 실패해 로그인하지 않았습니다.\n" +
        "누락 항목: 신뢰할 수 있는 서버 인증서, 승인 서버 이름, 정확한 PC 시간 또는 접근 가능한 CRL/OCSP\n" +
        "보존된 로컬 상태: " + PreservedLocalState + " HTTP나 로컬 계정으로 자동 전환하지 않습니다.\n" +
        "처리 담당자: 서버·인증서 운영 담당자\n" +
        "가능한 다음 행동: PC 날짜·시간과 HTTPS 서버 이름을 확인하고, 인증서 폐기 여부·CRL/OCSP 접근·갱신 인증서와 사내 신뢰 배포를 점검한 뒤 승인된 인증서로 다시 로그인하세요.";

    public const string TimeoutMessage =
        "실패 내용: 서버 응답 시간이 초과되어 로그인하지 않았습니다.\n" +
        "누락 항목: 응답 가능한 FlowNote 서버 연결\n" +
        "보존된 로컬 상태: " + PreservedLocalState + "\n" +
        "처리 담당자: 현장 관리자 또는 서버·네트워크 운영 담당자\n" +
        "가능한 다음 행동: 네트워크, 서버 재부팅 상태, 승인 HTTPS 주소와 방화벽 적용 여부를 확인한 뒤 다시 로그인하세요. 확인 전에는 로컬 로그인으로 우회하지 마세요.";

    public const string UnreachableMessage =
        "실패 내용: 서버에 연결할 수 없어 로그인하지 않았습니다.\n" +
        "누락 항목: 현재 운영 서버로 연결되는 네트워크·방화벽·HTTPS 주소\n" +
        "보존된 로컬 상태: " + PreservedLocalState + "\n" +
        "처리 담당자: 현장 관리자 또는 서버·네트워크 운영 담당자\n" +
        "가능한 다음 행동: FLOWNOTE_API_BASE_URL, DNS, 네트워크·방화벽과 서버 자동 시작을 확인하고 주소가 바뀌었다면 승인값으로 수정한 뒤 FlowNote를 다시 실행하세요. 확인 전에는 로컬 로그인으로 우회하지 마세요.";

    public const string LocalStartupFailureMessage =
        "실패 내용: FlowNote 시작에 필요한 로컬 저장소를 열거나 초기화하지 못했습니다.\n" +
        "누락 항목: 접근 가능한 로컬 DB 경로와 Files 폴더\n" +
        "보존된 로컬 상태: 복구를 위해 로컬 원천, Files, 동기화 큐와 알림 cursor를 자동 삭제·초기화·덮어쓰기하지 않습니다.\n" +
        "처리 담당자: Windows 설치 담당자 또는 현장 데이터 관리자\n" +
        "가능한 다음 행동: FLOWNOTE_LOCAL_DATA_DIR·FLOWNOTE_LOCAL_DATABASE_PATH, 폴더 권한과 디스크 여유를 확인하세요. 기존 DB 교체나 재설치 전에 DB와 Files를 함께 보존하고 담당자 승인을 받으세요.";

    public const string UnknownLoginFailureMessage =
        "실패 내용: 로그인 처리를 완료하지 못했습니다.\n" +
        "보존된 로컬 상태: " + PreservedLocalState + "\n" +
        "처리 담당자: 현장 관리자\n" +
        "가능한 다음 행동: 서버 대상과 계정 상태를 확인한 뒤 다시 시도하고, 계속 실패하면 화면 안내와 발생 시각을 담당자에게 전달하세요.";

    public static string LoginFailure(Exception exception)
    {
        if (IsCertificateFailure(exception))
        {
            return CertificateFailureMessage;
        }

        return exception is TaskCanceledException or TimeoutException
            ? TimeoutMessage
            : UnreachableMessage;
    }

    public static string ReconnectFailure(Exception exception)
    {
        if (IsCertificateFailure(exception))
        {
            return CertificateFailureMessage.Replace(
                "로그인하지 않았습니다.",
                "연결을 중지했습니다.");
        }

        return exception is TaskCanceledException or TimeoutException
            ? "실패 내용: 서버 응답이 늦어 동기화와 알림 확인을 완료하지 못했습니다.\n" +
              "보존된 로컬 상태: " + PreservedLocalState + "\n" +
              "처리 담당자: 서버·네트워크 운영 담당자\n" +
              "가능한 다음 행동: 네트워크와 서버 재부팅 상태를 확인한 뒤 다시 연결하세요. 서버 확인 전에는 안전한 동기화 완료로 판단하지 마세요."
            : "실패 내용: 서버 연결이 끊겨 동기화와 알림 확인을 완료하지 못했습니다.\n" +
              "보존된 로컬 상태: " + PreservedLocalState + "\n" +
              "처리 담당자: 현장 관리자 또는 서버·네트워크 운영 담당자\n" +
              "가능한 다음 행동: 네트워크·방화벽과 현재 서버 주소를 확인하세요. 주소가 변경됐다면 FLOWNOTE_API_BASE_URL을 승인값으로 바꾸고 FlowNote를 다시 실행하세요.";
    }

    private static bool IsCertificateFailure(Exception exception) =>
        Contains<AuthenticationException>(exception) ||
        exception is HttpRequestException
        {
            HttpRequestError: HttpRequestError.SecureConnectionError
        };

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
