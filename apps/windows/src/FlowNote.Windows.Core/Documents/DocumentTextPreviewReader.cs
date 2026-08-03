using System.Text;

namespace FlowNote.Windows.Core.Documents;

public sealed record DocumentTextPreviewResult(
    string Text,
    string EncodingName,
    bool IsTruncated,
    int TruncatedLineCount);

public static class DocumentTextPreviewReader
{
    public const int MaxDisplayedCharacters = 512 * 1024;
    public const int MaxDisplayedLineCharacters = 4096;

    static DocumentTextPreviewReader()
    {
        Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);
    }

    public static DocumentTextPreviewResult Read(string path)
    {
        using var stream = new FileStream(
            path,
            FileMode.Open,
            FileAccess.Read,
            FileShare.ReadWrite | FileShare.Delete,
            bufferSize: 4096,
            FileOptions.SequentialScan);
        var encoding = DetectEncoding(stream);
        stream.Position = 0;

        using var reader = new StreamReader(
            stream,
            encoding,
            detectEncodingFromByteOrderMarks: true,
            bufferSize: 4096,
            leaveOpen: false);
        var builder = new StringBuilder(Math.Min(MaxDisplayedCharacters, 64 * 1024));
        var truncated = false;
        var truncatedLines = 0;
        var lineCharacters = 0;
        var previousWasCarriageReturn = false;
        var stopReading = false;
        var buffer = new char[4096];
        while (!stopReading && builder.Length < MaxDisplayedCharacters)
        {
            var count = reader.Read(buffer, 0, buffer.Length);
            if (count == 0)
            {
                break;
            }

            for (var index = 0; index < count; index++)
            {
                var character = buffer[index];
                if (character == '\n')
                {
                    if (!previousWasCarriageReturn)
                    {
                        builder.AppendLine();
                    }

                    previousWasCarriageReturn = false;
                    lineCharacters = 0;
                    continue;
                }

                if (character == '\r')
                {
                    builder.AppendLine();
                    previousWasCarriageReturn = true;
                    lineCharacters = 0;
                    continue;
                }

                previousWasCarriageReturn = false;
                if (lineCharacters >= MaxDisplayedLineCharacters)
                {
                    builder.Append(" … [긴 행 일부 생략]");
                    truncated = true;
                    truncatedLines++;
                    stopReading = true;
                    break;
                }

                builder.Append(character);
                lineCharacters++;
                if (builder.Length >= MaxDisplayedCharacters)
                {
                    truncated = true;
                    stopReading = true;
                    break;
                }
            }
        }

        truncated |= stopReading || !reader.EndOfStream;

        if (truncated)
        {
            builder.AppendLine();
            builder.Append("[안전한 미리보기를 위해 긴 행 또는 문서 뒷부분을 생략했습니다. 원본은 변경되지 않았습니다.]");
        }

        return new DocumentTextPreviewResult(
            builder.ToString(),
            encoding.WebName,
            truncated,
            truncatedLines);
    }

    private static Encoding DetectEncoding(Stream stream)
    {
        var sample = new byte[Math.Min(64 * 1024, checked((int)Math.Min(stream.Length, 64 * 1024L)))];
        var length = stream.Read(sample, 0, sample.Length);
        var bytes = sample.AsSpan(0, length);

        if (bytes.StartsWith(new byte[] { 0xEF, 0xBB, 0xBF }))
        {
            return new UTF8Encoding(encoderShouldEmitUTF8Identifier: true, throwOnInvalidBytes: true);
        }

        if (bytes.StartsWith(new byte[] { 0xFF, 0xFE }))
        {
            return new UnicodeEncoding(bigEndian: false, byteOrderMark: true, throwOnInvalidBytes: true);
        }

        if (bytes.StartsWith(new byte[] { 0xFE, 0xFF }))
        {
            return new UnicodeEncoding(bigEndian: true, byteOrderMark: true, throwOnInvalidBytes: true);
        }

        if (LooksLikeUtf16(bytes, evenBytesAreNull: false))
        {
            return new UnicodeEncoding(bigEndian: false, byteOrderMark: false, throwOnInvalidBytes: true);
        }

        if (LooksLikeUtf16(bytes, evenBytesAreNull: true))
        {
            return new UnicodeEncoding(bigEndian: true, byteOrderMark: false, throwOnInvalidBytes: true);
        }

        var utf8 = new UTF8Encoding(encoderShouldEmitUTF8Identifier: false, throwOnInvalidBytes: true);
        try
        {
            _ = utf8.GetString(bytes);
            return utf8;
        }
        catch (DecoderFallbackException)
        {
            return Encoding.GetEncoding(
                949,
                EncoderFallback.ExceptionFallback,
                DecoderFallback.ExceptionFallback);
        }
    }

    private static bool LooksLikeUtf16(ReadOnlySpan<byte> bytes, bool evenBytesAreNull)
    {
        if (bytes.Length < 4)
        {
            return false;
        }

        var examinedPairs = Math.Min(bytes.Length / 2, 256);
        var nullCount = 0;
        for (var pair = 0; pair < examinedPairs; pair++)
        {
            var index = pair * 2 + (evenBytesAreNull ? 0 : 1);
            if (bytes[index] == 0)
            {
                nullCount++;
            }
        }

        return nullCount >= examinedPairs * 3 / 4;
    }
}
