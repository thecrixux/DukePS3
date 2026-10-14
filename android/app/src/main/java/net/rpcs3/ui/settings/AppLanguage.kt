package net.rpcs3.ui.settings

import android.content.Context
import android.content.res.Configuration
import android.os.LocaleList
import androidx.appcompat.app.AppCompatDelegate
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
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.core.os.LocaleListCompat
import net.rpcs3.R

/** Activity locales are stored by AppCompat on Android 12 and by Android on 13+. */
object AppLanguage {
    fun contextFor(base: Context): Context {
        val locales = AppCompatDelegate.getApplicationLocales()
        if (locales.isEmpty) return base
        val config = Configuration(base.resources.configuration)
        config.setLocales(LocaleList.forLanguageTags(locales.toLanguageTags()))
        return base.createConfigurationContext(config)
    }

    fun select(tag: String) {
        require(tag in setOf("", "en", "es"))
        AppCompatDelegate.setApplicationLocales(LocaleListCompat.forLanguageTags(tag))
    }
}

@Composable
fun AppLanguageDialog(onDismiss: () -> Unit) {
    // Reading the configuration makes the current selection refresh on locale changes.
    val configuration = LocalConfiguration.current
    val tag = remember(configuration) {
        AppCompatDelegate.getApplicationLocales().toLanguageTags()
            .substringBefore(',').substringBefore('-')
    }
    val choices = listOf(
        "" to stringResource(R.string.app_language_system),
        "es" to "Español",
        "en" to "English"
    )
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.app_language_title)) },
        text = {
            Column {
                Text(stringResource(R.string.app_language_hint))
                choices.forEach { (value, label) ->
                    Row(
                        modifier = Modifier.fillMaxWidth()
                            .selectable(selected = tag == value, role = Role.RadioButton) {
                                onDismiss()
                                AppLanguage.select(value)
                            }.padding(vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        RadioButton(selected = tag == value, onClick = null)
                        Text(label, modifier = Modifier.padding(start = 12.dp))
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) { Text(stringResource(R.string.action_close)) }
        }
    )
}

@Composable
fun AppLanguageButton(modifier: Modifier = Modifier) {
    var show by remember { mutableStateOf(false) }
    TextButton(onClick = { show = true }, modifier = modifier) {
        Text(stringResource(R.string.app_language_title))
    }
    if (show) AppLanguageDialog { show = false }
}
