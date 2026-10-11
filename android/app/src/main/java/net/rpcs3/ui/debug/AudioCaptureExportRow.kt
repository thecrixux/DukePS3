package net.rpcs3.ui.debug

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Share
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import net.rpcs3.EmulatorState
import net.rpcs3.R
import net.rpcs3.RPCS3
import net.rpcs3.ui.components.PaneNavRow
import java.io.File

@Composable
internal fun AudioCaptureExportRow(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("") }
    var pendingName by rememberSaveable { mutableStateOf<String?>(null) }
    val cache = File(RPCS3.rootDirectory, "cache")

    fun showFailure(error: Throwable) {
        status = when ((error as? AudioCaptureException)?.issue) {
            AudioCaptureIssue.NOT_FOUND -> context.getString(R.string.audio_capture_not_found)
            AudioCaptureIssue.UNFINISHED -> context.getString(R.string.audio_capture_unfinished)
            null -> context.getString(R.string.audio_capture_error, error.message.orEmpty())
        }
    }

    val exporter = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("application/zip")
    ) { uri ->
        val name = pendingName
        pendingName = null
        if (uri != null && name != null) {
            if (RPCS3.getState() != EmulatorState.Stopped) {
                status = context.getString(R.string.audio_capture_stop_game)
            } else {
                busy = true
                scope.launch {
                    try {
                        withContext(Dispatchers.IO) {
                            val output = context.contentResolver.openOutputStream(uri, "wt")
                                ?: error("Cannot open destination")
                            output.use {
                                AudioCaptureExport.writeZip(File(cache, name), File(cache, "RPCS3.log"), it)
                            }
                        }
                        status = context.getString(R.string.audio_capture_saved, name)
                    } catch (error: Exception) {
                        if (error is CancellationException) throw error
                        showFailure(error)
                    } finally {
                        busy = false
                    }
                }
            }
        }
    }

    PaneNavRow(
        title = stringResource(R.string.audio_capture_export),
        description = when {
            busy -> stringResource(R.string.audio_capture_busy)
            status.isNotEmpty() -> status
            else -> stringResource(R.string.audio_capture_description)
        },
        icon = Icons.Outlined.Share,
        modifier = modifier,
        onClick = {
            if (!busy) {
                if (RPCS3.getState() != EmulatorState.Stopped) {
                    status = context.getString(R.string.audio_capture_stop_game)
                } else {
                    busy = true
                    scope.launch {
                        try {
                            val capture = withContext(Dispatchers.IO) { AudioCaptureExport.latest(cache) }
                            pendingName = capture.name
                            exporter.launch("DukePS3-${capture.name.removeSuffix(".wav")}.zip")
                        } catch (error: Exception) {
                            if (error is CancellationException) throw error
                            pendingName = null
                            showFailure(error)
                        } finally {
                            busy = false
                        }
                    }
                }
            }
        }
    )
}
