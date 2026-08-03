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

    private static readonly HashSet<string> DocumentGovernanceRoles = new(StringComparer.OrdinalIgnoreCase)
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

    private static readonly HashSet<string> ReportWriteRoles = new(StringComparer.OrdinalIgnoreCase)
    {
        "admin",
        "manager",
        "system-admin",
        "document-admin",
        "assistant-manager",
        "department-manager"
    };

    private static readonly HashSet<string> AccessLogReadRoles = new(StringComparer.OrdinalIgnoreCase)
    {
        "admin",
        "system-admin"
    };

    private static readonly HashSet<string> UserManagementRoles = new(StringComparer.OrdinalIgnoreCase)
    {
        "admin",
        "system-admin"
    };

    private static readonly HashSet<string> GroundTruthApprovalRoles = new(StringComparer.OrdinalIgnoreCase)
    {
        "admin", "system-admin", "document-admin", "department-manager"
    };

    public static bool CanRegisterDocuments(string? role)
    {
        return !string.IsNullOrWhiteSpace(role) && DocumentRegistrationRoles.Contains(role);
    }

    public static bool CanDownloadDocuments(string? role)
    {
        return !string.IsNullOrWhiteSpace(role) && DocumentDownloadRoles.Contains(role);
    }

    public static bool CanGovernDocuments(string? role)
    {
        return !string.IsNullOrWhiteSpace(role) && DocumentGovernanceRoles.Contains(role);
    }

    public static bool CanWriteFieldComments(string? role)
    {
        return IsAllowedUserRole(role);
    }

    public static bool CanManageFileWatch(string? role)
    {
        return !string.IsNullOrWhiteSpace(role) && FileWatchManagementRoles.Contains(role);
    }

    public static bool CanWriteReports(string? role)
    {
        return !string.IsNullOrWhiteSpace(role) && ReportWriteRoles.Contains(role);
    }

    public static bool CanReadAccessLogs(string? role)
    {
        return !string.IsNullOrWhiteSpace(role) && AccessLogReadRoles.Contains(role);
    }

    public static bool CanReadChangeHistory(string? role) => CanGovernDocuments(role);

    public static bool CanManageUsers(string? role)
    {
        return !string.IsNullOrWhiteSpace(role) && UserManagementRoles.Contains(role);
    }

    public static bool CanOperateGroundTruth(string? role) => CanWriteReports(role);

    public static bool CanApproveGroundTruth(string? role)
    {
        return !string.IsNullOrWhiteSpace(role) && GroundTruthApprovalRoles.Contains(role);
    }

    public static bool CanOperateAIOperations(string? role) =>
        string.Equals(role, "system-admin", StringComparison.OrdinalIgnoreCase);

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
