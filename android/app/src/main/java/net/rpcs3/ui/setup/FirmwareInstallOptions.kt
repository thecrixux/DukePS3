package net.rpcs3.ui.setup

import android.content.Context
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import net.rpcs3.ui.theme.SettingsStyle
import net.rpcs3.R

object FirmwareInstallOptions {
    private const val PREFERENCES = "firmware-install"
    private const val PREPARE_CACHE = "prepare-cache"
    fun prepareCache(context: Context): Boolean =
        context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE).getBoolean(PREPARE_CACHE, true)
    fun save(context: Context, value: Boolean) {
        context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE).edit()
            .putBoolean(PREPARE_CACHE, value).apply()
    }
}

@Composable
fun FirmwareInstallChoices(
    prepareCache: Boolean,
    onChange: (Boolean) -> Unit,
    enabled: Boolean = true
) {
    Column {
        listOf(
            Triple(true, R.string.firmware_install_complete, R.string.firmware_install_complete_detail),
            Triple(false, R.string.firmware_install_fast, R.string.firmware_install_fast_detail)
        ).forEach { (value, label, detail) ->
            Row(
                modifier = Modifier.fillMaxWidth()
                    .selectable(
                        selected = prepareCache == value,
                        enabled = enabled,
                        role = Role.RadioButton,
                        onClick = { onChange(value) }
                    ).padding(vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                RadioButton(selected = prepareCache == value, enabled = enabled, onClick = null)
                Column(modifier = Modifier.weight(1f).padding(start = 8.dp)) {
                    Text(stringResource(label), color = SettingsStyle.TextPrimary, fontSize = 12.sp)
                    Text(stringResource(detail), color = SettingsStyle.TextSecondary, fontSize = 12.sp)
                }
            }
        }
    }
}

@Composable
fun FirmwareInstallDialog(onSelect: () -> Unit, onDismiss: () -> Unit) {
    val context = LocalContext.current
    var prepareCache by remember { mutableStateOf(FirmwareInstallOptions.prepareCache(context)) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.firmware_install_title)) },
        text = {
            Column {
                Text(stringResource(R.string.firmware_install_hint))
                FirmwareInstallChoices(prepareCache = prepareCache, onChange = { prepareCache = it })
            }
        },
        confirmButton = {
            TextButton(onClick = {
                FirmwareInstallOptions.save(context, prepareCache)
                onSelect()
            }) { Text(stringResource(R.string.firmware_select_file)) }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text(stringResource(R.string.action_cancel)) }
        }
    )
}
