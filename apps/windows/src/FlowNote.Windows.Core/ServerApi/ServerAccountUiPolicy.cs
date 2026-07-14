using System.Net;

namespace FlowNote.Windows.Core.ServerApi;

public static class ServerAccountUiPolicy
{
    public static string ConnectedMessage => "서버 로그인 계정으로 서버 계정을 관리합니다.";

    public static string LocalMessage => "서버에 연결되지 않아 이 PC의 로컬 계정만 관리합니다.";

    public static bool CanManageAccounts(string? role) =>
        string.Equals(role, "admin", StringComparison.OrdinalIgnoreCase) ||
        string.Equals(role, "system-admin", StringComparison.OrdinalIgnoreCase);

    public static bool CanManageSystemAdmin(string? role) =>
        string.Equals(role, "system-admin", StringComparison.OrdinalIgnoreCase);

    public static string FormatStatus(string status, bool mustChangePassword) => status switch
    {
        "ACTIVE" when mustChangePassword => "활성 · 비밀번호 변경 필요",
        "ACTIVE" => "활성",
        "LOCKED" => "잠김",
        "DISABLED" => "비활성",
        _ => status
    };

    public static string ErrorMessage(HttpStatusCode statusCode) => statusCode switch
    {
        HttpStatusCode.Unauthorized => "서버 로그인 세션이 만료되었습니다. 다시 로그인하세요.",
        HttpStatusCode.Forbidden => "서버 계정 운영 권한이 없습니다. 관리자 권한을 확인하세요.",
        HttpStatusCode.Conflict => "보호 규칙 때문에 변경할 수 없습니다. 자기 자신 또는 마지막 시스템 관리자 여부를 확인하세요.",
        _ => "서버 계정 작업에 실패했습니다. 서버 상태와 입력값을 확인하세요."
    };
}
