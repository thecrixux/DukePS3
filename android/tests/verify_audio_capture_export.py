#!/usr/bin/env python3
"""Compile and exercise the production WAV selector and ZIP writer on the JVM."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[2]
source = root / 'android/app/src/main/java/net/rpcs3/ui/debug/AudioCaptureExport.kt'
test = r'''
package net.rpcs3.ui.debug

import java.io.ByteArrayOutputStream
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.zip.ZipInputStream

fun main(args: Array<String>) {
    val cache = File(args[0]).apply { mkdirs() }
    fun expect(issue: AudioCaptureIssue, block: () -> Unit) {
        try { block(); error("Expected $issue") }
        catch (e: AudioCaptureException) { check(e.issue == issue) }
    }
    fun u32(value: Int) = ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt(value).array()
    fun chunk(id: String, data: ByteArray) =
        id.toByteArray() + u32(data.size) + data + if (data.size % 2 != 0) byteArrayOf(0) else byteArrayOf()
    fun wave(floating: Boolean, samples: ByteArray): ByteArray {
        val format = ByteBuffer.allocate(16).order(ByteOrder.LITTLE_ENDIAN)
            .putShort(if (floating) 3 else 1).putShort(2).putInt(48000)
            .putInt(if (floating) 384000 else 192000)
            .putShort(if (floating) 8 else 4).putShort(if (floating) 32 else 16).array()
        val body = "WAVE".toByteArray() + chunk("fmt ", format) +
            chunk("JUNK", byteArrayOf(1, 2, 3)) +
            (if (floating) chunk("fact", u32(samples.size / 8)) else byteArrayOf()) +
            chunk("data", samples)
        return "RIFF".toByteArray() + u32(body.size) + body
    }
    fun unpack(bytes: ByteArray): Map<String, ByteArray> {
        val files = mutableMapOf<String, ByteArray>()
        ZipInputStream(bytes.inputStream()).use { zip ->
            while (true) {
                val entry = zip.nextEntry ?: break
                files[entry.name] = zip.readBytes()
            }
        }
        return files
    }

    expect(AudioCaptureIssue.NOT_FOUND) { AudioCaptureExport.latest(cache) }
    File(cache, "music.wav").writeBytes(wave(false, ByteArray(16)))
    File(cache, "audio_directory.wav").mkdir()
    expect(AudioCaptureIssue.NOT_FOUND) { AudioCaptureExport.latest(cache) }

    val first = File(cache, "audio_BLUS30354_first.wav")
    first.writeBytes(wave(false, byteArrayOf(0, 0, 5, 0, 10, 0, 20, 0)))
    check(first.setLastModified(1000))
    check(AudioCaptureExport.latest(cache) == first)

    val floats = ByteBuffer.allocate(32).order(ByteOrder.LITTLE_ENDIAN)
        .putFloat(0.25f).putFloat(-0.25f).putFloat(0.5f).putFloat(-0.5f)
        .putFloat(Float.NaN).putFloat(Float.POSITIVE_INFINITY).putFloat(0f).putFloat(-0f).array()
    val newest = File(cache, "audio_BLUS30354_latest.wav")
    newest.writeBytes(wave(true, floats))
    check(newest.setLastModified(2000))
    check(AudioCaptureExport.latest(cache) == newest)
    val log = File(cache, "RPCS3.log").apply { writeText("Cubeb: actual backend: aaudio\n") }
    val original = newest.readBytes()
    val output = ByteArrayOutputStream()
    AudioCaptureExport.writeZip(newest, log, output)
    val files = unpack(output.toByteArray())
    check(files.keys == setOf(newest.name, "RPCS3.log"))
    check(files[newest.name]!!.contentEquals(original)) // Preserve all PCM bits, even invalid floats.
    check(files["RPCS3.log"]!!.contentEquals(log.readBytes()))
    check(newest.readBytes().contentEquals(original))
    check(first.isFile && File(cache, "music.wav").isFile)

    log.delete()
    val withoutLog = ByteArrayOutputStream()
    AudioCaptureExport.writeZip(first, log, withoutLog)
    check(unpack(withoutLog.toByteArray()).keys == setOf(first.name))

    // Open AudioDumper files lack their header until the game stops.
    newest.writeBytes(ByteArray(56) + floats)
    check(newest.setLastModified(2000))
    expect(AudioCaptureIssue.UNFINISHED) { AudioCaptureExport.latest(cache) }
    expect(AudioCaptureIssue.UNFINISHED) {
        AudioCaptureExport.writeZip(newest, log, ByteArrayOutputStream())
    }
    newest.writeBytes(original.copyOf(original.size - 1))
    check(newest.setLastModified(2000))
    expect(AudioCaptureIssue.UNFINISHED) { AudioCaptureExport.latest(cache) }
    newest.writeBytes(wave(true, byteArrayOf()))
    check(newest.setLastModified(2000))
    expect(AudioCaptureIssue.UNFINISHED) { AudioCaptureExport.latest(cache) }
    newest.writeBytes(original.copyOf().apply {
        // RPCS3 currently underreports RIFF size; actual data chunk bounds decide completeness.
        u32(size - 20).copyInto(this, 4)
    })
    check(newest.setLastModified(2000))
    check(AudioCaptureExport.latest(cache) == newest)
    newest.delete()
    expect(AudioCaptureIssue.NOT_FOUND) {
        AudioCaptureExport.writeZip(newest, log, ByteArrayOutputStream())
    }
    println("PASS: production Kotlin; latest selection, closed/truncated/empty WAVs, optional log, byte-exact PCM ZIP export, no source changes")
}
'''
with tempfile.TemporaryDirectory() as directory:
    temp = Path(directory)
    (temp / 'main.kt').write_text(test)
    compiler = os.environ.get('KOTLINC', shutil.which('kotlinc') or 'kotlinc')
    result = subprocess.run([compiler, str(source), str(temp / 'main.kt'), '-include-runtime', '-d', str(temp / 'test.jar')],
                            capture_output=True, text=True)
    if result.returncode:
        print(result.stdout, result.stderr)
        raise SystemExit(result.returncode)
    subprocess.run(['java', '-jar', str(temp / 'test.jar'), str(temp / 'cache')], check=True)

keys = None
for locale in ('values', 'values-es'):
    resources = root / ('android/app/src/main/res/' + locale)
    entries = list(ET.parse(resources / 'audio_capture_strings.xml').getroot())
    current = {entry.attrib['name']: re.findall(r'%\d+\$[a-z]', entry.text or '') for entry in entries}
    assert len(entries) == len(current)
    if keys is not None:
        assert keys == current
    keys = current
    for path in resources.glob('*.xml'):
        if path.name == 'audio_capture_strings.xml':
            continue
        assert not current.keys() & {entry.attrib.get('name') for entry in ET.parse(path).getroot()}
print('PASS: unique resources and matching EN/ES placeholders')
