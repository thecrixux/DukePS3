package net.rpcs3.ui.setup

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.Settings
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.Folder
import androidx.compose.material.icons.outlined.Notifications
import androidx.compose.material.icons.outlined.SystemUpdate
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.compose.runtime.DisposableEffect
import net.rpcs3.ui.settings.AppLanguageButton
import net.rpcs3.FirmwareRepository
import net.rpcs3.Permission
import net.rpcs3.R
import net.rpcs3.ui.theme.SettingsStyle

fun hasStorageAccess(): Boolean =
    Build.VERSION.SDK_INT < Build.VERSION_CODES.R || Environment.isExternalStorageManager()

fun hasFirmware(): Boolean = FirmwareRepository.version.value != null

fun setupComplete(context: Context): Boolean = hasStorageAccess() && hasFirmware()

fun requestStorageAccess(context: Context) {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
        return
    }

    val intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION).apply {
        data = Uri.parse("package:" + context.packageName)
        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    }

    runCatching { context.startActivity(intent) }.onFailure {
        runCatching {
            context.startActivity(
                Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            )
        }
    }
}

@Composable
fun SetupWizard(
    onInstallFirmware: () -> Unit,
    onFinish: () -> Unit,
    onSkip: (() -> Unit)? = null
) {
    val context = LocalContext.current
    var storageGranted by remember { mutableStateOf(hasStorageAccess()) }
    var notificationsGranted by remember {
        mutableStateOf(Permission.PostNotifications.checkPermission(context))
    }

    val firmwareVersion by FirmwareRepository.version
    val firmwareProgress by FirmwareRepository.progressChannel
    val firmwareReady = firmwareVersion != null
    var prepareFirmwareCache by androidx.compose.runtime.saveable.rememberSaveable {
        mutableStateOf(FirmwareInstallOptions.prepareCache(context))
    }

    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                storageGranted = hasStorageAccess()
                notificationsGranted = Permission.PostNotifications.checkPermission(context)
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    Box(modifier = Modifier.fillMaxSize().background(SettingsStyle.BgDeep)) {
        Image(
            painter = painterResource(R.drawable.duke_welcome_background),
            contentDescription = null,
            contentScale = ContentScale.Crop,
            alignment = Alignment.BottomCenter,
            modifier = Modifier.fillMaxSize()
        )
        Column(
            modifier = Modifier
                .fillMaxSize()
                .windowInsetsPadding(WindowInsets.safeDrawing)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 20.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Column(modifier = Modifier.widthIn(max = 520.dp).fillMaxWidth()) {
                AppLanguageButton(modifier = Modifier.align(Alignment.End))
                Text(
                    text = stringResource(R.string.setup_welcome),
                    color = SettingsStyle.TextPrimary,
                    fontSize = 24.sp,
                    fontWeight = FontWeight.Bold
                )
                Spacer(Modifier.height(16.dp))

                SetupStep(
                    index = 1,
                    icon = Icons.Outlined.Folder,
                    title = stringResource(R.string.setup_storage_title),
                    detail = stringResource(R.string.setup_storage_detail),
                    done = storageGranted,
                    actionLabel = stringResource(R.string.setup_allow),
                    onAction = { requestStorageAccess(context) }
                )

                Spacer(Modifier.height(10.dp))

                SetupStep(
                    index = 2,
                    icon = Icons.Outlined.SystemUpdate,
                    title = stringResource(R.string.setup_firmware_title),
                    detail = firmwareVersion?.let { stringResource(R.string.setup_firmware_installed, it) }
                        ?: stringResource(R.string.setup_firmware_detail),
                    done = firmwareReady,
                    busy = firmwareProgress != null,
                    actionLabel = stringResource(R.string.setup_install),
                    onAction = {
                        FirmwareInstallOptions.save(context, prepareFirmwareCache)
                        onInstallFirmware()
                    },
                    extraContent = {
                        if (!firmwareReady) {
                            FirmwareInstallChoices(
                                prepareCache = prepareFirmwareCache,
                                enabled = firmwareProgress == null,
                                onChange = { prepareFirmwareCache = it }
                            )
                        }
                    }
                )

                Spacer(Modifier.height(10.dp))

                SetupStep(
                    index = 3,
                    icon = Icons.Outlined.Notifications,
                    title = stringResource(R.string.setup_notifications_title),
                    detail = stringResource(R.string.setup_notifications_detail),
                    optional = true,
                    done = notificationsGranted,
                    actionLabel = stringResource(R.string.setup_allow),
                    onAction = {
                        (context as? Activity)?.let { Permission.PostNotifications.requestPermission(it) }
                    }
                )

                Spacer(Modifier.height(16.dp))

                val ready = storageGranted && firmwareReady

                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(14.dp))
                        .background(if (ready) SettingsStyle.AccentBlue else SettingsStyle.CardSurface)
                        .border(
                            1.dp,
                            if (ready) Color.Transparent else SettingsStyle.CardBorder,
                            RoundedCornerShape(14.dp)
                        )
                        .clickable(enabled = ready, onClick = onFinish)
                        .padding(vertical = 14.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = stringResource(R.string.setup_next),
                        color = if (ready) SettingsStyle.BgDeep else SettingsStyle.TextDim,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.SemiBold
                    )
                }

                if (onSkip != null) {
                    Spacer(Modifier.height(10.dp))
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(12.dp))
                            .clickable(onClick = onSkip)
                            .padding(vertical = 10.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = stringResource(R.string.setup_skip),
                            color = SettingsStyle.TextSecondary,
                            fontSize = 13.sp
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun SetupStep(
    index: Int,
    icon: ImageVector,
    title: String,
    detail: String,
    done: Boolean,
    actionLabel: String,
    onAction: () -> Unit,
    optional: Boolean = false,
    busy: Boolean = false,
    extraContent: @Composable () -> Unit = {}
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(SettingsStyle.CardSurface.copy(alpha = 0.96f))
            .border(
                1.dp,
                if (done) SettingsStyle.AccentBlue.copy(alpha = 0.5f) else SettingsStyle.CardBorder,
                RoundedCornerShape(16.dp)
            )
            .padding(12.dp),
        verticalAlignment = Alignment.Top
    ) {
        Box(
            modifier = Modifier
                .size(32.dp)
                .clip(RoundedCornerShape(11.dp))
                .background(SettingsStyle.InputSurface),
            contentAlignment = Alignment.Center
        ) {
            Icon(
                imageVector = if (done) Icons.Outlined.CheckCircle else icon,
                contentDescription = null,
                tint = if (done) SettingsStyle.AccentBlue else SettingsStyle.TextSecondary,
                modifier = Modifier.size(20.dp)
            )
        }

        Spacer(Modifier.width(10.dp))

        Column(modifier = Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = stringResource(R.string.setup_step_title, index, title),
                    modifier = Modifier.weight(1f),
                    color = SettingsStyle.TextPrimary,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.SemiBold
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    text = stringResource(
                        if (optional) R.string.setup_optional else R.string.setup_required
                    ),
                    color = if (optional) {
                        SettingsStyle.TextDim
                    } else {
                        SettingsStyle.TextSecondary
                    },
                    fontSize = 10.sp
                )
            }
            Spacer(Modifier.height(3.dp))
            Text(text = detail, color = SettingsStyle.TextSecondary, fontSize = 12.sp)
            extraContent()
        }

        Spacer(Modifier.width(8.dp))

        Box(
            modifier = Modifier
                .clip(RoundedCornerShape(10.dp))
                .background(if (done) Color.Transparent else SettingsStyle.AccentBlue)
                .border(
                    1.dp,
                    if (done) Color.Transparent else SettingsStyle.AccentBlue,
                    RoundedCornerShape(10.dp)
                )
                .clickable(enabled = !done && !busy, onClick = onAction)
                .defaultMinSize(minHeight = 48.dp)
                .padding(horizontal = 10.dp, vertical = 8.dp),
            contentAlignment = Alignment.Center
        ) {
            when {
                busy -> CircularProgressIndicator(
                    modifier = Modifier.size(16.dp),
                    color = SettingsStyle.BgDeep,
                    strokeWidth = 2.dp
                )

                done -> Text(
                    text = stringResource(R.string.setup_done),
                    color = SettingsStyle.AccentBlue,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.SemiBold
                )

                else -> Text(
                    text = actionLabel,
                    color = SettingsStyle.BgDeep,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.SemiBold
                )
            }
        }
    }
}

@Composable
fun StorageAccessDialog(onGrant: () -> Unit, onDismiss: () -> Unit) {
    androidx.compose.ui.window.Dialog(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(18.dp))
                .background(SettingsStyle.BgDeep)
                .border(1.dp, SettingsStyle.CardBorder, RoundedCornerShape(18.dp))
                .padding(18.dp)
        ) {
            Text(
                text = stringResource(R.string.setup_storage_dialog_title),
                color = SettingsStyle.TextPrimary,
                fontSize = 15.sp,
                fontWeight = FontWeight.SemiBold
            )
            Spacer(Modifier.height(6.dp))
            Text(
                text = stringResource(R.string.setup_storage_dialog_message),
                color = SettingsStyle.TextSecondary,
                fontSize = 12.sp
            )
            Spacer(Modifier.height(16.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.End
            ) {
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(10.dp))
                        .clickable(onClick = onDismiss)
                        .padding(horizontal = 14.dp, vertical = 8.dp)
                ) {
                    Text(
                        stringResource(R.string.setup_storage_dialog_not_now),
                        color = SettingsStyle.TextSecondary,
                        fontSize = 13.sp
                    )
                }
                Spacer(Modifier.width(6.dp))
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(10.dp))
                        .background(SettingsStyle.AccentBlue)
                        .clickable(onClick = onGrant)
                        .padding(horizontal = 16.dp, vertical = 8.dp)
                ) {
                    Text(
                        stringResource(R.string.setup_storage_dialog_open_settings),
                        color = SettingsStyle.BgDeep,
                        fontSize = 13.sp
                    )
                }
            }
        }
    }
}
