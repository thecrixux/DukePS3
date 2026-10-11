package net.rpcs3.ui.settings

import androidx.compose.foundation.layout.Column
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import net.rpcs3.R
import net.rpcs3.ui.components.SettingInlineDropdown
import net.rpcs3.ui.components.SettingsHint
import org.json.JSONObject

internal fun isAndroidAudioBackendSetting(path: String): Boolean =
    path.trimStart('@') == "Audio@@Android Audio Backend"

@Composable
internal fun AndroidAudioBackendSetting(
    item: JSONObject,
    path: String,
    titleId: String,
    modifier: Modifier,
    onCommit: (String) -> Boolean
) {
    val values = listOf("auto", "aaudio", "opensl")
    val entries = listOf(
        stringResource(R.string.android_audio_backend_auto), "AAudio", "OpenSL ES"
    )
    var value by remember(path, titleId) { mutableStateOf(item.optString("value")) }
    val default = item.optString("default")
    Column(modifier = modifier) {
        SettingInlineDropdown(
            label = stringResource(R.string.android_audio_backend) + if (value == default) "" else " *",
            entries = entries,
            selectedIndex = values.indexOf(value).coerceAtLeast(0),
            onSelected = { index ->
                val next = values.getOrNull(index) ?: return@SettingInlineDropdown
                if (onCommit(JSONObject.quote(next))) {
                    item.put("value", next)
                    value = next
                }
            }
        )
        SettingsHint(text = stringResource(R.string.android_audio_backend_hint))
    }
}
