package net.rpcs3.ui.debug

import java.io.File
import java.io.IOException
import java.io.OutputStream
import java.io.RandomAccessFile
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

internal enum class AudioCaptureIssue { NOT_FOUND, UNFINISHED }

internal class AudioCaptureException(val issue: AudioCaptureIssue) : IOException(issue.name)

internal object AudioCaptureExport {
    fun latest(cacheDirectory: File): File {
        val capture = cacheDirectory.listFiles()
            ?.filter { it.isFile && it.name.startsWith("audio_") && it.name.endsWith(".wav") }
            ?.sortedWith(compareBy<File> { it.lastModified() }.thenBy { it.name })
            ?.lastOrNull()
            ?: throw AudioCaptureException(AudioCaptureIssue.NOT_FOUND)
        // Never silently export an older capture if the newest one is still open.
        requireComplete(capture)
        return capture
    }

    private fun requireComplete(capture: File) {
        if (!capture.isFile) throw AudioCaptureException(AudioCaptureIssue.NOT_FOUND)
        RandomAccessFile(capture, "r").use { input ->
            val length = input.length()
            if (length >= 12 && input.readInt() == 0x52494646) { // RIFF
                input.skipBytes(4)
                if (input.readInt() == 0x57415645) { // WAVE
                    var formatFound = false
                    while (input.filePointer + 8 <= length) {
                        val chunk = input.readInt()
                        val size = Integer.reverseBytes(input.readInt()).toLong() and 0xffffffffL
                        val end = input.filePointer + size
                        if (end > length) break
                        if (chunk == 0x666d7420 && size >= 16) formatFound = true // fmt
                        if (chunk == 0x64617461) { // data
                            if (formatFound && size > 0) return
                            break
                        }
                        input.seek(end + (size and 1L))
                    }
                }
            }
        }
        // AudioDumper writes the WAV header when the recording is closed.
        throw AudioCaptureException(AudioCaptureIssue.UNFINISHED)
    }

    fun writeZip(capture: File, log: File, output: OutputStream) {
        requireComplete(capture)
        ZipOutputStream(output.buffered()).use { zip ->
            fun add(file: File) {
                zip.putNextEntry(ZipEntry(file.name))
                file.inputStream().use { it.copyTo(zip) }
                zip.closeEntry()
            }
            add(capture)
            if (log.isFile && log.length() > 0) add(log)
        }
    }
}
