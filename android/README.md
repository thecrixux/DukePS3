# DukePS3 — Android

Android front end and build integration for **DukePS3 1.0.0**, based on RPCS3, RPCS3-Android and PS3Native.

[Project overview and features](../README.md) · [Español](../README.es.md)

The historical RPCS3-Android port is discontinued; **this directory belongs to the actively maintained DukePS3 fork**, not that archived release.

## Build requirements

- JDK 17, Android SDK 35, NDK `29.0.14206865`, CMake `3.31.6`.
- Repository submodules initialized.
- LLVM and FFmpeg cross-compiled for `arm64-v8a` in `android/prebuilt/`.
- A Bash-capable environment for the dependency build scripts.

From the repository root:

```bash
git submodule update --init --recursive
cd android
./build-ffmpeg-android.sh
./build-llvm-android.sh
./gradlew assembleStandardDebug
```

The dependency scripts are the expensive step. Reuse their outputs unless their sources/build configuration change.

With the Android SDK and prebuilt dependencies prepared, PowerShell can build with:

```powershell
cd android
.\gradlew.bat assembleStandardDebug
```

For release builds, use `assembleStandardRelease` and configure signing in the app build. APK output is under `app/build/outputs/apk/`.

The [Android APK workflow](../.github/workflows/android.yml) supports manual dispatch, debug/release builds and dependency/compiler caching.

## App identity

| Setting | Value |
| --- | --- |
| Display name | DukePS3 |
| Android version | 1.0.0 |
| Application ID | `com.crixux.dukeps3` |
| Minimum Android | 12 / API 31 |
| Architecture | `arm64-v8a` |
| Normal build flavor | `standard` |

All retained flavor task aliases use the same application ID. The code namespace remains `net.rpcs3` to preserve native JNI bindings; it is independent of the installed package identity.

Games, PS3 firmware and proprietary Lossless Scaling shaders are not bundled. DIS is built into the app. See the main README for setup, supported engines, device-test results and current limits.

## Credits and licenses

See the [project credits](../README.md#credits), [root license](../LICENSE), [Android license](LICENSE) and individual file/component headers. Original copyright and attribution notices are retained.
