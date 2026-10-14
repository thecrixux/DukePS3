package net.rpcs3.ui.settings

import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import android.content.Context
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import net.rpcs3.dialogs.AlertDialogQueue
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import net.rpcs3.R
import net.rpcs3.RPCS3
import net.rpcs3.ui.components.SettingInlineDropdown
import net.rpcs3.ui.components.SettingSlider
import net.rpcs3.ui.components.InfoRow
import net.rpcs3.ui.components.SettingSwitch
import net.rpcs3.ui.components.SettingTextField
import org.json.JSONArray
import org.json.JSONObject

private fun variantsOf(item: JSONObject): List<String> {
    val array: JSONArray = item.optJSONArray("variants") ?: return emptyList()
    return List(array.length()) { array.optString(it, "") }
}

private val settingsWriter = CoroutineScope(SupervisorJob() + Dispatchers.IO)

private fun commit(
    context: Context,
    path: String,
    value: String,
    titleId: String,
    label: String
): Boolean {
    settingsWriter.launch {
        if (!RPCS3.instance.settingsSet(path, value, titleId)) {
            withContext(Dispatchers.Main) {
                AlertDialogQueue.showDialog(
                    context.getString(R.string.settings_error_title),
                    context.getString(R.string.settings_error_assign, label)
                )
            }
            return@launch
        }

        RPCS3.instance.settingsFlush()

        RPCS3.instance.takeSettingsSaveFailure()?.let { target ->
            withContext(Dispatchers.Main) {
                AlertDialogQueue.showDialog(
                    context.getString(R.string.settings_not_saved_title),
                    context.getString(R.string.settings_not_saved_message, target)
                )
            }
        }
    }
    return true
}

@Composable
fun SettingItem(
    label: String,
    item: JSONObject,
    path: String,
    titleId: String,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val displayLabel = ConfigText.label(context, label)

    if (path.trimStart('@') == "Video@@Resolution" && item.optString("type") == "enum") {
        VideoOutputSetting(item, path, titleId, modifier) { next ->
            commit(context, path, next, titleId, context.getString(R.string.video_output_mode))
        }
        return
    }
    if (path.trimStart('@') == "Video@@Resolution Scale" && item.optString("type") in listOf("uint", "int")) {
        ResolutionScaleSetting(item, path, titleId, modifier) { next ->
            commit(context, path, next, titleId, context.getString(R.string.render_scale))
        }
        return
    }

    if (isAndroidAudioBackendSetting(path) && item.optString("type") == "string") {
        AndroidAudioBackendSetting(item, path, titleId, modifier) { next ->
            commit(context, path, next, titleId, context.getString(R.string.android_audio_backend))
        }
        return
    }

    if (isPpuStartupSetting(path)) {
        PpuStartupSetting(item, path, modifier) { next ->
            commit(context, path, next, titleId, context.getString(R.string.ppu_startup_title))
        }
        return
    }

    when (item.optString("type", "")) {
        "bool" -> {
            var value by remember(path) { mutableStateOf(item.optBoolean("value")) }
            val default = item.optBoolean("default")
            SettingSwitch(
                label = displayLabel + if (value == default) "" else " *",
                checked = value,
                modifier = modifier,
                onCheckedChange = { next ->
                    if (commit(context, path, if (next) "true" else "false", titleId, displayLabel)) {
                        item.put("value", next)
                        value = next
                    }
                }
            )
        }

        "enum" -> {
            val variants = remember(path) { variantsOf(item) }
            var value by remember(path) { mutableStateOf(item.optString("value")) }
            val default = item.optString("default")
            val index = variants.indexOf(value).coerceAtLeast(0)
            SettingInlineDropdown(
                label = displayLabel + if (value == default) "" else " *",
                entries = variants.map { ConfigText.label(context, it) },
                selectedIndex = index,
                modifier = modifier,
                onSelected = { next ->
                    val chosen = variants.getOrNull(next) ?: return@SettingInlineDropdown
                    if (commit(context, path, JSONObject.quote(chosen), titleId, displayLabel)) {
                        item.put("value", chosen)
                        value = chosen
                    }
                }
            )
        }

        "uint", "int" -> {
            val min = item.optLong("min", 0L)
            val max = item.optLong("max", 100L)
            var value by remember(path) { mutableFloatStateOf(item.optLong("value").toFloat()) }
            val default = item.optLong("default")

            if (min < max) {
                SettingSlider(
                    label = displayLabel + if (value.toLong() == default) "" else " *",
                    value = value,
                    valueRange = min.toFloat()..max.toFloat(),
                    valueText = value.toLong().toString(),
                    modifier = modifier,
                    onValueChange = { value = it },
                    onValueChangeFinished = {
                        val next = value.toLong()
                        if (commit(context, path, next.toString(), titleId, displayLabel)) {
                            item.put("value", next)
                        }
                    }
                )
            } else {
                var text by remember(path) { mutableStateOf(item.optLong("value").toString()) }
                SettingTextField(
                    label = displayLabel,
                    value = text,
                    modifier = modifier,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    onValueChange = { next ->
                        text = next
                        next.toLongOrNull()?.let {
                            if (commit(context, path, it.toString(), titleId, displayLabel)) {
                                item.put("value", it)
                            }
                        }
                    }
                )
            }
        }

        "float" -> {
            val min = item.optDouble("min", 0.0).toFloat()
            val max = item.optDouble("max", 1.0).toFloat()
            var value by remember(path) { mutableFloatStateOf(item.optDouble("value").toFloat()) }
            val default = item.optDouble("default").toFloat()

            SettingSlider(
                label = displayLabel + if (value == default) "" else " *",
                value = value,
                valueRange = min..max,
                valueText = String.format("%.2f", value),
                modifier = modifier,
                onValueChange = { value = it },
                onValueChangeFinished = {
                    if (commit(context, path, value.toString(), titleId, displayLabel)) {
                        item.put("value", value.toDouble())
                    }
                }
            )
        }

        "string" -> {
            var value by remember(path) { mutableStateOf(item.optString("value")) }
            val default = item.optString("default")
            SettingTextField(
                label = displayLabel + if (value == default) "" else " *",
                value = value,
                placeholder = default,
                modifier = modifier,
                onValueChange = { next ->
                    value = next
                    if (commit(context, path, JSONObject.quote(next), titleId, displayLabel)) {
                        item.put("value", next)
                    }
                }
            )
        }

        else -> {
            val raw = item.opt("value")?.toString().orEmpty()
            if (raw.isNotEmpty()) {
                InfoRow(label = displayLabel, value = raw.take(80))
            }
        }
    }
}

