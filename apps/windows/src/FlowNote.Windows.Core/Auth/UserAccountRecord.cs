namespace FlowNote.Windows.Core.Auth;

public sealed record UserAccountRecord(
    string UserId,
    string LoginId,
    string DisplayName,
    string Role,
    string Status)
{
    public string RoleLabel => RolePermissionPolicy.FormatUserRole(Role);

    public string StatusLabel => Status switch
    {
        "ACTIVE" => "활성",
        "LOCKED" => "잠김",
        "DISABLED" => "비활성",
        _ => Status
    };
}
