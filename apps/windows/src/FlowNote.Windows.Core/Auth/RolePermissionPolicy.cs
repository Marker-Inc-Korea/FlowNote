namespace FlowNote.Windows.Core.Auth;

public static class RolePermissionPolicy
{
    public static readonly IReadOnlyList<UserRoleOption> UserRoleOptions =
    [
        new("admin", "관리자"),
        new("system-admin", "시스템 관리자"),
        new("document-admin", "문서 관리자"),
        new("manager", "관리자"),
        new("assistant-manager", "차장"),
        new("department-manager", "부서장"),
        new("line-foreman", "반장"),
        new("team-lead", "조장"),
        new("team-member", "조원"),
        new("viewer", "열람자")
    ];

    private static readonly HashSet<string> DocumentRegistrationRoles = new(StringComparer.OrdinalIgnoreCase)
    {
        "admin",
        "manager",
        "system-admin",
        "document-admin",
        "assistant-manager",
        "department-manager",
        "line-foreman",
        "team-lead"
    };

    private static readonly HashSet<string> DocumentDownloadRoles = new(StringComparer.OrdinalIgnoreCase)
    {
        "admin",
        "manager",
        "system-admin",
        "document-admin",
        "assistant-manager",
        "department-manager"
    };

    private static readonly HashSet<string> FileWatchManagementRoles = new(StringComparer.OrdinalIgnoreCase)
    {
        "admin",
        "manager",
        "system-admin",
        "document-admin",
        "assistant-manager",
        "department-manager"
    };

    private static readonly HashSet<string> UserManagementRoles = new(StringComparer.OrdinalIgnoreCase)
    {
        "admin",
        "system-admin"
    };

    public static bool CanRegisterDocuments(string? role)
    {
        return !string.IsNullOrWhiteSpace(role) && DocumentRegistrationRoles.Contains(role);
    }

    public static bool CanDownloadDocuments(string? role)
    {
        return !string.IsNullOrWhiteSpace(role) && DocumentDownloadRoles.Contains(role);
    }

    public static bool CanManageFileWatch(string? role)
    {
        return !string.IsNullOrWhiteSpace(role) && FileWatchManagementRoles.Contains(role);
    }

    public static bool CanManageUsers(string? role)
    {
        return !string.IsNullOrWhiteSpace(role) && UserManagementRoles.Contains(role);
    }

    public static bool IsAllowedUserRole(string? role)
    {
        return !string.IsNullOrWhiteSpace(role) &&
            UserRoleOptions.Any(option => string.Equals(option.Role, role, StringComparison.OrdinalIgnoreCase));
    }

    public static string FormatUserRole(string? role)
    {
        return UserRoleOptions.FirstOrDefault(option =>
                string.Equals(option.Role, role, StringComparison.OrdinalIgnoreCase))
            ?.Label ?? role ?? string.Empty;
    }
}
