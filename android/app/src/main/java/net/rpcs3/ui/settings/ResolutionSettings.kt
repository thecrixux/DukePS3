package net.rpcs3.ui.settings

import androidx.compose.foundation.layout.Column
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import net.rpcs3.R
import net.rpcs3.ui.components.SettingInlineDropdown
import net.rpcs3.ui.components.SettingSlider
import net.rpcs3.ui.components.SettingsHint
import org.json.JSONObject

internal fun isResolutionSetting(path: String): Boolean =
    path.trimStart('@') == "Video@@Resolution" ||
        path.trimStart('@') == "Video@@Resolution Scale"

@Composable
internal fun VideoOutputSetting(
    item: JSONObject,
    path: String,
    titleId: String,
    modifier: Modifier,
    onCommit: (String) -> Boolean
) {
    val array = item.optJSONArray("variants")
    val variants = remember(path, titleId) {
        if (array == null) emptyList() else List(array.length()) { array.optString(it) }
    }
    var value by remember(path, titleId) { mutableStateOf(item.optString("value")) }
    val default = item.optString("default")
    Column(modifier = modifier) {
        SettingInlineDropdown(
            label = stringResource(R.string.video_output_mode) + if (value == default) "" else " *",
            entries = variants,
            selectedIndex = variants.indexOf(value).coerceAtLeast(0),
            onSelected = { index ->
                val next = variants.getOrNull(index) ?: return@SettingInlineDropdown
                if (onCommit(JSONObject.quote(next))) {
                    item.put("value", next)
                    value = next
                }
            }
        )
        SettingsHint(text = stringResource(R.string.video_output_mode_hint))
    }
}

@Composable
internal fun ResolutionScaleSetting(
    item: JSONObject,
    path: String,
    titleId: String,
    modifier: Modifier,
    onCommit: (String) -> Boolean
) {
    val min = item.optLong("min", 25L)
    val max = item.optLong("max", 800L)
    val default = item.optLong("default", 100L)
    var value by remember(path, titleId) { mutableFloatStateOf(item.optLong("value").toFloat()) }
    // Preserve the configured Android default (currently 70%), and any custom
    // value. Presets write the same scale setting, never the PS3 video mode.
    val presets = remember(min, max, default) {
        (listOf(default) + listOf(100L, 150L, 200L, 300L)).distinct().sorted()
            .filter { it in min..max }
    }
    val selected = presets.indexOf(value.toLong())
    val custom = selected < 0
    val labels = presets.map { percent ->
        when (percent) {
            100L -> stringResource(R.string.render_scale_100)
            150L -> stringResource(R.string.render_scale_150)
            200L -> stringResource(R.string.render_scale_200)
            300L -> stringResource(R.string.render_scale_300)
            else -> "$percent%"
        }
    }
    val entries = if (custom) listOf(stringResource(R.string.render_scale_custom, value.toLong())) + labels else labels
    Column(modifier = modifier) {
        SettingInlineDropdown(
            label = stringResource(R.string.render_scale_presets),
            entries = entries,
            selectedIndex = if (custom) 0 else selected,
            onSelected = { index ->
                val next = presets.getOrNull(index - if (custom) 1 else 0) ?: return@SettingInlineDropdown
                if (onCommit(next.toString())) {
                    item.put("value", next)
                    value = next.toFloat()
                }
            }
        )
        SettingSlider(
            label = stringResource(R.string.render_scale) + if (value.toLong() == default) "" else " *",
            value = value,
            valueRange = min.toFloat()..max.toFloat(),
            valueText = "${value.toLong()}%",
            enabled = min < max,
            onValueChange = { value = it },
            onValueChangeFinished = {
                val next = value.toLong().coerceIn(min, max)
                if (onCommit(next.toString())) {
                    item.put("value", next)
                    value = next.toFloat()
                }
            }
        )
        SettingsHint(text = stringResource(R.string.render_scale_hint))
    }
}
