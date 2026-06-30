using FlowNote.Windows.Core.Documents;
using FlowNote.Windows.Core.History;
using FlowNote.Windows.Core.Storage;
using Microsoft.Data.Sqlite;

namespace FlowNote.Windows.Core.FileWatching;

public sealed class FileWatchService : IDisposable
{
    private readonly FlowNoteLocalDatabase database;
    private readonly DocumentService documents;
    private readonly object watcherLock = new();
    private FileSystemWatcher? watcher;
    private string? watchedFolderPath;

    public FileWatchService(FlowNoteLocalDatabase database, DocumentService documents)
    {
        this.database = database;
        this.documents = documents;
    }

    public event EventHandler<FileWatchCandidateRecord>? CandidateDetected;

    public bool IsRunning => watcher is not null;

    public string? WatchedFolderPath => watchedFolderPath;

    public void StartWatching(string folderPath, string actorName)
    {
        if (string.IsNullOrWhiteSpace(folderPath))
        {
            throw new ArgumentException("Watch folder is required.", nameof(folderPath));
        }

        var fullPath = Path.GetFullPath(folderPath.Trim());
        if (!Directory.Exists(fullPath))
        {
            throw new DirectoryNotFoundException($"Watch folder not found: {fullPath}");
        }

        lock (watcherLock)
        {
            StopWatchingCore(actorName, recordHistory: false);

            watcher = new FileSystemWatcher(fullPath)
            {
                IncludeSubdirectories = false,
                Filter = "*.*",
                NotifyFilter = NotifyFilters.FileName
                    | NotifyFilters.LastWrite
                    | NotifyFilters.Size
                    | NotifyFilters.CreationTime
            };
            watcher.Created += Watcher_FileChanged;
            watcher.Changed += Watcher_FileChanged;
            watcher.Renamed += Watcher_FileRenamed;
            watcher.EnableRaisingEvents = true;
            watchedFolderPath = fullPath;
        }

        using var connection = database.OpenConnection();
        HistoryService.Record(
            connection,
            "file_watch.started",
            actorName,
            "file_watch_folder",
            fullPath,
            Path.GetFileName(fullPath),
            $"File watch started: {fullPath}",
            DateTime.UtcNow);
    }

    public void StopWatching(string actorName)
    {
        lock (watcherLock)
        {
            StopWatchingCore(actorName, recordHistory: true);
        }
    }

    public FileWatchCandidateRecord CaptureCandidateForPath(string sourcePath, string actorName)
    {
        var fileInfo = new FileInfo(sourcePath);
        if (!fileInfo.Exists)
        {
            throw new FileNotFoundException("Changed file not found.", sourcePath);
        }

        return SaveCandidate(fileInfo, actorName);
    }

    public IReadOnlyList<FileWatchCandidateRecord> ListCandidates(bool includeResolved = false)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = includeResolved
            ? """
              SELECT candidate.id, candidate.candidate_id, candidate.source_path, candidate.file_name,
                     candidate.size_bytes, candidate.last_write_time_utc, candidate.status,
                     candidate.document_id, document.title, candidate.detected_by, candidate.detected_at,
                     candidate.version_label, candidate.change_reason, candidate.resolved_by, candidate.resolved_at
              FROM file_watch_candidates AS candidate
              LEFT JOIN documents AS document ON document.document_id = candidate.document_id
              ORDER BY candidate.detected_at DESC, candidate.id DESC;
              """
            : """
              SELECT candidate.id, candidate.candidate_id, candidate.source_path, candidate.file_name,
                     candidate.size_bytes, candidate.last_write_time_utc, candidate.status,
                     candidate.document_id, document.title, candidate.detected_by, candidate.detected_at,
                     candidate.version_label, candidate.change_reason, candidate.resolved_by, candidate.resolved_at
              FROM file_watch_candidates AS candidate
              LEFT JOIN documents AS document ON document.document_id = candidate.document_id
              WHERE candidate.status = 'PENDING'
              ORDER BY candidate.detected_at DESC, candidate.id DESC;
              """;

        using var reader = command.ExecuteReader();
        var candidates = new List<FileWatchCandidateRecord>();
        while (reader.Read())
        {
            candidates.Add(ReadCandidate(reader));
        }

        return candidates;
    }

    public DocumentRecord ConfirmCandidate(
        string candidateId,
        string documentId,
        string versionLabel,
        string changeReason,
        string actorName)
    {
        if (string.IsNullOrWhiteSpace(versionLabel))
        {
            throw new ArgumentException("Version label is required.", nameof(versionLabel));
        }

        if (string.IsNullOrWhiteSpace(changeReason))
        {
            throw new ArgumentException("Change reason is required.", nameof(changeReason));
        }

        var candidate = GetCandidate(candidateId);
        if (!string.Equals(candidate.Status, "PENDING", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("Only pending watch candidates can be confirmed.");
        }

        if (!File.Exists(candidate.SourcePath))
        {
            throw new FileNotFoundException("Changed file no longer exists.", candidate.SourcePath);
        }

        var fileInfo = new FileInfo(candidate.SourcePath);
        var storedRelativePath = CopyFileToAppStorage(fileInfo, DateTime.Now);
        var document = documents.AddFileVersion(
            documentId,
            fileInfo.Name,
            storedRelativePath,
            versionLabel,
            changeReason,
            actorName);

        var now = DateTime.UtcNow;
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            UPDATE file_watch_candidates
            SET status = 'CONFIRMED',
                document_id = $document_id,
                version_label = $version_label,
                change_reason = $change_reason,
                resolved_by = $resolved_by,
                resolved_at = $resolved_at
            WHERE candidate_id = $candidate_id;
            """;
        command.Parameters.AddWithValue("$document_id", documentId);
        command.Parameters.AddWithValue("$version_label", versionLabel.Trim());
        command.Parameters.AddWithValue("$change_reason", changeReason.Trim());
        command.Parameters.AddWithValue("$resolved_by", actorName);
        command.Parameters.AddWithValue("$resolved_at", now.ToString("O"));
        command.Parameters.AddWithValue("$candidate_id", candidateId);
        command.ExecuteNonQuery();

        HistoryService.Record(
            connection,
            "file_watch.candidate_confirmed",
            actorName,
            "file_watch_candidate",
            candidateId,
            candidate.FileName,
            $"File watch candidate confirmed: {candidate.FileName} -> {document.Title} {versionLabel.Trim()}",
            now);

        return document;
    }

    public void IgnoreCandidate(string candidateId, string actorName)
    {
        var candidate = GetCandidate(candidateId);
        if (!string.Equals(candidate.Status, "PENDING", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("Only pending watch candidates can be ignored.");
        }

        var now = DateTime.UtcNow;
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            UPDATE file_watch_candidates
            SET status = 'IGNORED',
                resolved_by = $resolved_by,
                resolved_at = $resolved_at
            WHERE candidate_id = $candidate_id;
            """;
        command.Parameters.AddWithValue("$resolved_by", actorName);
        command.Parameters.AddWithValue("$resolved_at", now.ToString("O"));
        command.Parameters.AddWithValue("$candidate_id", candidateId);
        command.ExecuteNonQuery();

        HistoryService.Record(
            connection,
            "file_watch.candidate_ignored",
            actorName,
            "file_watch_candidate",
            candidateId,
            candidate.FileName,
            $"File watch candidate ignored: {candidate.FileName}",
            now);
    }

    public void Dispose()
    {
        lock (watcherLock)
        {
            StopWatchingCore("system", recordHistory: false);
        }
    }

    private void Watcher_FileChanged(object sender, FileSystemEventArgs e)
    {
        TryCaptureWatcherEvent(e.FullPath);
    }

    private void Watcher_FileRenamed(object sender, RenamedEventArgs e)
    {
        TryCaptureWatcherEvent(e.FullPath);
    }

    private void TryCaptureWatcherEvent(string path)
    {
        try
        {
            if (Directory.Exists(path) || !File.Exists(path))
            {
                return;
            }

            var candidate = SaveCandidate(new FileInfo(path), "file-watcher");
            CandidateDetected?.Invoke(this, candidate);
        }
        catch (IOException)
        {
            // Some editors emit change events before the file handle is released.
        }
        catch (UnauthorizedAccessException)
        {
        }
    }

    private FileWatchCandidateRecord SaveCandidate(FileInfo fileInfo, string actorName)
    {
        fileInfo.Refresh();
        var now = DateTime.UtcNow;
        var sourcePath = fileInfo.FullName;
        var matchedDocumentId = FindDocumentIdByFileName(fileInfo.Name);

        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            INSERT INTO file_watch_candidates (
                candidate_id,
                source_path,
                file_name,
                size_bytes,
                last_write_time_utc,
                status,
                document_id,
                detected_by,
                detected_at
            )
            VALUES (
                $candidate_id,
                $source_path,
                $file_name,
                $size_bytes,
                $last_write_time_utc,
                'PENDING',
                $document_id,
                $detected_by,
                $detected_at
            )
            ON CONFLICT(source_path, status) DO UPDATE SET
                file_name = excluded.file_name,
                size_bytes = excluded.size_bytes,
                last_write_time_utc = excluded.last_write_time_utc,
                document_id = COALESCE(excluded.document_id, file_watch_candidates.document_id),
                detected_by = excluded.detected_by,
                detected_at = excluded.detected_at;
            """;
        command.Parameters.AddWithValue("$candidate_id", $"watch-candidate-{Guid.NewGuid():N}");
        command.Parameters.AddWithValue("$source_path", sourcePath);
        command.Parameters.AddWithValue("$file_name", fileInfo.Name);
        command.Parameters.AddWithValue("$size_bytes", fileInfo.Length);
        command.Parameters.AddWithValue("$last_write_time_utc", fileInfo.LastWriteTimeUtc.ToString("O"));
        command.Parameters.AddWithValue("$document_id", string.IsNullOrWhiteSpace(matchedDocumentId) ? DBNull.Value : matchedDocumentId);
        command.Parameters.AddWithValue("$detected_by", actorName);
        command.Parameters.AddWithValue("$detected_at", now.ToString("O"));
        command.ExecuteNonQuery();

        var candidate = GetPendingCandidateByPath(connection, sourcePath)
            ?? throw new InvalidOperationException("File watch candidate was not saved.");

        HistoryService.Record(
            connection,
            "file_watch.candidate_created",
            actorName,
            "file_watch_candidate",
            candidate.CandidateId,
            candidate.FileName,
            $"File watch candidate created: {candidate.FileName}",
            now);

        return candidate;
    }

    private FileWatchCandidateRecord GetCandidate(string candidateId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT candidate.id, candidate.candidate_id, candidate.source_path, candidate.file_name,
                   candidate.size_bytes, candidate.last_write_time_utc, candidate.status,
                   candidate.document_id, document.title, candidate.detected_by, candidate.detected_at,
                   candidate.version_label, candidate.change_reason, candidate.resolved_by, candidate.resolved_at
            FROM file_watch_candidates AS candidate
            LEFT JOIN documents AS document ON document.document_id = candidate.document_id
            WHERE candidate.candidate_id = $candidate_id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$candidate_id", candidateId);

        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            throw new InvalidOperationException($"File watch candidate not found: {candidateId}");
        }

        return ReadCandidate(reader);
    }

    private FileWatchCandidateRecord? GetPendingCandidateByPath(SqliteConnection connection, string sourcePath)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT candidate.id, candidate.candidate_id, candidate.source_path, candidate.file_name,
                   candidate.size_bytes, candidate.last_write_time_utc, candidate.status,
                   candidate.document_id, document.title, candidate.detected_by, candidate.detected_at,
                   candidate.version_label, candidate.change_reason, candidate.resolved_by, candidate.resolved_at
            FROM file_watch_candidates AS candidate
            LEFT JOIN documents AS document ON document.document_id = candidate.document_id
            WHERE candidate.source_path = $source_path AND candidate.status = 'PENDING'
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$source_path", sourcePath);

        using var reader = command.ExecuteReader();
        return reader.Read() ? ReadCandidate(reader) : null;
    }

    private string? FindDocumentIdByFileName(string fileName)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT document_id
            FROM documents
            WHERE file_name = $file_name
            ORDER BY updated_at DESC, id DESC
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$file_name", fileName);
        var value = command.ExecuteScalar();
        return value is null or DBNull ? null : Convert.ToString(value);
    }

    private string CopyFileToAppStorage(FileInfo sourceFile, DateTime createdAt)
    {
        var dataDirectory = Path.GetDirectoryName(database.DatabasePath)!;
        var uploadRoot = Path.Combine(dataDirectory, "Files", "Uploads", createdAt.ToString("yyyy-MM-dd"));
        Directory.CreateDirectory(uploadRoot);

        var targetPath = GetUniqueTargetPath(uploadRoot, sourceFile.Name);
        File.Copy(sourceFile.FullName, targetPath);
        return Path.GetRelativePath(dataDirectory, targetPath);
    }

    private static string GetUniqueTargetPath(string directory, string fileName)
    {
        var candidate = Path.Combine(directory, fileName);
        if (!File.Exists(candidate))
        {
            return candidate;
        }

        var name = Path.GetFileNameWithoutExtension(fileName);
        var extension = Path.GetExtension(fileName);
        var index = 1;
        do
        {
            candidate = Path.Combine(directory, $"{name}-{index:00}{extension}");
            index++;
        }
        while (File.Exists(candidate));

        return candidate;
    }

    private void StopWatchingCore(string actorName, bool recordHistory)
    {
        var previousPath = watchedFolderPath;
        if (watcher is not null)
        {
            watcher.EnableRaisingEvents = false;
            watcher.Created -= Watcher_FileChanged;
            watcher.Changed -= Watcher_FileChanged;
            watcher.Renamed -= Watcher_FileRenamed;
            watcher.Dispose();
            watcher = null;
        }

        watchedFolderPath = null;

        if (!recordHistory || string.IsNullOrWhiteSpace(previousPath))
        {
            return;
        }

        using var connection = database.OpenConnection();
        HistoryService.Record(
            connection,
            "file_watch.stopped",
            actorName,
            "file_watch_folder",
            previousPath,
            Path.GetFileName(previousPath),
            $"File watch stopped: {previousPath}",
            DateTime.UtcNow);
    }

    private static FileWatchCandidateRecord ReadCandidate(SqliteDataReader reader)
    {
        return new FileWatchCandidateRecord(
            reader.GetInt64(0),
            reader.GetString(1),
            reader.GetString(2),
            reader.GetString(3),
            reader.GetInt64(4),
            DateTime.Parse(reader.GetString(5)),
            reader.GetString(6),
            reader.IsDBNull(7) ? null : reader.GetString(7),
            reader.IsDBNull(8) ? null : reader.GetString(8),
            reader.GetString(9),
            DateTime.Parse(reader.GetString(10)),
            reader.IsDBNull(11) ? null : reader.GetString(11),
            reader.IsDBNull(12) ? null : reader.GetString(12),
            reader.IsDBNull(13) ? null : reader.GetString(13),
            reader.IsDBNull(14) ? null : DateTime.Parse(reader.GetString(14)));
    }
}
