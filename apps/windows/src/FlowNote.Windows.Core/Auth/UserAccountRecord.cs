namespace FlowNote.Windows.Core.Auth;

public sealed record UserAccountRecord(
    string UserId,
    string LoginId,
    string DisplayName,
    string Role,
    string Status)
{
    public string RoleLabel => Role switch
    {
        "admin" => "관리자",
        "manager" => "관리자",
        "system-admin" => "시스템 관리자",
        "document-admin" => "문서 관리자",
        "assistant-manager" => "차장",
        "department-manager" => "부서장",
        "line-foreman" => "반장",
        "team-lead" => "조장",
        "team-member" => "조원",
        "viewer" => "열람자",
        _ => Role
    };

    public string StatusLabel => Status switch
    {
        "ACTIVE" => "활성",
        "LOCKED" => "잠김",
        "DISABLED" => "비활성",
        _ => Status
    };
}
