package net.rpcs3.ui.settings

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import net.rpcs3.R
import net.rpcs3.ui.components.SettingInlineDropdown
import net.rpcs3.ui.components.SettingSwitch
import org.json.JSONObject

private const val profilePath = "Core@@Android PPU Compile Profile"
private const val priorityPath = "Core@@Android PPU Normal Startup Priority"
private const val diagnosticsPath = "Core@@Android PPU Compile Diagnostics"
private const val cachePath = "Core@@Android PPU Test Cache Slot"

fun isPpuStartupSetting(path: String): Boolean =
    path.trimStart('@') in setOf(profilePath, priorityPath, diagnosticsPath, cachePath)

@Composable
fun PpuStartupSetting(
    item: JSONObject,
    path: String,
    modifier: Modifier = Modifier,
    commit: (String) -> Boolean
) {
    val key = path.trimStart('@')
    val hint = when (key) {
        profilePath -> R.string.ppu_profile_hint
        priorityPath -> R.string.ppu_priority_hint
        diagnosticsPath -> R.string.ppu_diagnostics_hint
        else -> R.string.ppu_cache_hint
    }
    Column(modifier) {
        when (key) {
            profilePath, cachePath -> {
                var value by remember(path) { mutableStateOf(item.optInt("value")) }
                val entries = if (key == profilePath) listOf(
                    stringResource(R.string.ppu_profile_current),
                    stringResource(R.string.ppu_profile_balanced),
                    stringResource(R.string.ppu_profile_experimental)
                ) else listOf(stringResource(R.string.ppu_cache_normal)) + (1..9).map { it.toString() }
                SettingInlineDropdown(
                    label = stringResource(if (key == profilePath) R.string.ppu_profile_label else R.string.ppu_cache_label),
                    entries = entries,
                    selectedIndex = value.coerceIn(entries.indices),
                    fieldWidth = 160.dp,
                    onSelected = { next ->
                        if (next in entries.indices && commit(next.toString())) {
                            item.put("value", next)
                            value = next
                        }
                    }
                )
            }
            priorityPath, diagnosticsPath -> {
                var value by remember(path) { mutableStateOf(item.optBoolean("value")) }
                SettingSwitch(
                    label = stringResource(if (key == priorityPath) R.string.ppu_priority_label else R.string.ppu_diagnostics_label),
                    checked = value,
                    onCheckedChange = { next ->
                        if (commit(next.toString())) {
                            item.put("value", next)
                            value = next
                        }
                    }
                )
            }
        }
        Spacer(Modifier.height(6.dp))
        Text(
            text = stringResource(hint),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}
