namespace FlowNote.Windows.Core.Auth;

public static class RolePermissionPolicy
{
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

    public static bool CanRegisterDocuments(string? role)
    {
        return !string.IsNullOrWhiteSpace(role) && DocumentRegistrationRoles.Contains(role);
    }

    public static bool CanDownloadDocuments(string? role)
    {
        return !string.IsNullOrWhiteSpace(role) && DocumentDownloadRoles.Contains(role);
    }
}
