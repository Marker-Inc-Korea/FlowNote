using FlowNote.Windows.Core.Folders;
using FlowNote.Windows.Core.Storage;

namespace FlowNote.Windows.Core.Documents;

public sealed class DocumentPlacementService(FolderService folders)
{
    public DocumentRegistrationPlan PrepareDocumentRegistration(
        long selectedFolderId,
        string fileName,
        DateTime createdAt,
        string? actorName = null)
    {
        var selectedFolder = folders.GetFolder(selectedFolderId);
        var title = CreateTitle(selectedFolder, fileName);
        var targetFolder = ResolveTargetFolder(selectedFolder, fileName, title, createdAt, actorName);
        return new DocumentRegistrationPlan(targetFolder, title);
    }

    private DocumentFolder ResolveTargetFolder(
        DocumentFolder selectedFolder,
        string fileName,
        string title,
        DateTime createdAt,
        string? actorName)
    {
        if (selectedFolder.Name is FlowNoteLocalDatabase.HandoverFolderName or FlowNoteLocalDatabase.PhotosFolderName)
        {
            return folders.GetOrCreateChildFolder(createdAt.ToString("yyyy-MM-dd"), selectedFolder.Id, actorName: actorName);
        }

        if (selectedFolder.Name == FlowNoteLocalDatabase.DocumentsFolderName && selectedFolder.Path == $"/{FlowNoteLocalDatabase.DocumentsFolderName}")
        {
            var categoryName = FlowNoteLocalDatabase.ResolveDocumentCategoryName(title, fileName, string.Empty);
            return folders.GetOrCreateChildFolder(categoryName, selectedFolder.Id, isSystem: true, actorName: actorName);
        }

        return selectedFolder;
    }

    private static string CreateTitle(DocumentFolder selectedFolder, string fileName)
    {
        var title = Path.GetFileNameWithoutExtension(fileName);
        if (string.IsNullOrWhiteSpace(title))
        {
            title = fileName;
        }

        return title;
    }
}
