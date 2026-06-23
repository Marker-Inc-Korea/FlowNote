using FlowNote.Windows.Core.Auth;
using FlowNote.Windows.Core.Documents;
using FlowNote.Windows.Core.Folders;
using FlowNote.Windows.Core.Notifications;

namespace FlowNote.Windows.Core.Storage;

public sealed class FlowNoteLocalServices
{
    public FlowNoteLocalServices(string databasePath)
    {
        Database = new FlowNoteLocalDatabase(databasePath);
        Database.Initialize();
        Auth = new AuthService(Database);
        Folders = new FolderService(Database);
        Documents = new DocumentService(Database);
        Notifications = new NotificationService(Database);
        DocumentPlacement = new DocumentPlacementService(Folders);
    }

    public FlowNoteLocalDatabase Database { get; }

    public AuthService Auth { get; }

    public FolderService Folders { get; }

    public DocumentService Documents { get; }

    public NotificationService Notifications { get; }

    public DocumentPlacementService DocumentPlacement { get; }
}
