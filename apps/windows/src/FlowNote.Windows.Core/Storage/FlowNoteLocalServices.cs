using FlowNote.Windows.Core.Auth;
using FlowNote.Windows.Core.Audit;
using FlowNote.Windows.Core.Documents;
using FlowNote.Windows.Core.FieldNotes;
using FlowNote.Windows.Core.FileWatching;
using FlowNote.Windows.Core.Folders;
using FlowNote.Windows.Core.History;
using FlowNote.Windows.Core.Notifications;
using FlowNote.Windows.Core.Sync;
using FlowNote.Windows.Core.Tags;
using FlowNote.Windows.Core.WorkSequences;

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
        DocumentViewLogs = new DocumentViewLogService(Database);
        FieldNotes = new FieldNoteService(Database);
        History = new HistoryService(Database);
        Notifications = new NotificationService(Database);
        Tags = new TagService(Database);
        WorkSequences = new WorkSequenceService(Database);
        ServerSync = new ServerSyncService(Database);
        DocumentPlacement = new DocumentPlacementService(Folders);
        FileWatch = new FileWatchService(Database, Documents);
    }

    public FlowNoteLocalDatabase Database { get; }

    public AuthService Auth { get; }

    public FolderService Folders { get; }

    public DocumentService Documents { get; }

    public DocumentViewLogService DocumentViewLogs { get; }

    public FieldNoteService FieldNotes { get; }

    public HistoryService History { get; }

    public NotificationService Notifications { get; }

    public TagService Tags { get; }

    public WorkSequenceService WorkSequences { get; }

    public ServerSyncService ServerSync { get; }

    public DocumentPlacementService DocumentPlacement { get; }

    public FileWatchService FileWatch { get; }
}
