#!/usr/bin/env python3
"""Configure the pinned Cubeb project with the Android backend build settings.

Requires CMake and a materialized Cubeb source (CUBEB_SOURCE, or submodule).
Does not compile an APK or open an Android audio device.
"""
from pathlib import Path
import os
import re
import subprocess
import tempfile

root=Path(__file__).resolve().parents[2]
cubeb=Path(os.environ.get('CUBEB_SOURCE',str(root/'3rdparty/cubeb/cubeb'))).resolve()
if not (cubeb/'CMakeLists.txt').exists():
    raise SystemExit('Initialize the Cubeb submodule or set CUBEB_SOURCE to its source directory.')
app=(root/'android/app/src/main/cpp/CMakeLists.txt').read_text()
start=app.index('set(USE_SYSTEM_LIBUSB off)')
end=app.index('add_subdirectory(${RPCS3_SOURCE_DIR}',start)
settings=app[start:end]
cmake=os.environ.get('CMAKE','cmake')
with tempfile.TemporaryDirectory() as directory:
    temp=Path(directory)
    (temp/'android-settings.cmake').write_text(settings)
    path=cubeb.as_posix().replace('"','\\"')
    (temp/'CMakeLists.txt').write_text('''cmake_minimum_required(VERSION 3.19)
project(audio_backend_build_test LANGUAGES C CXX)
set(USE_OPENSL OFF CACHE BOOL "Simulate an older Android build cache")
set(USE_OPENSL OFF)
include(${CMAKE_CURRENT_SOURCE_DIR}/android-settings.cmake)
set(ANDROID TRUE)
set(USE_AAUDIO ON)
set(BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(BUILD_TOOLS OFF CACHE BOOL "" FORCE)
set(BUILD_RUST_LIBS OFF CACHE BOOL "" FORCE)
set(USE_SANITIZERS OFF CACHE BOOL "" FORCE)
set(BUNDLE_SPEEX ON CACHE BOOL "" FORCE)
set(LAZY_LOAD_LIBS ON CACHE BOOL "" FORCE)
add_subdirectory("'''+path+'''" cubeb)
get_target_property(src cubeb SOURCES)
get_target_property(defs cubeb COMPILE_DEFINITIONS)
get_target_property(libs cubeb LINK_LIBRARIES)
file(WRITE ${CMAKE_BINARY_DIR}/audio-target.txt "SOURCES=${src}\\nDEFINES=${defs}\\nLIBS=${libs}\\n")
''')
    build=temp/'build'
    result=subprocess.run([cmake,'-S',str(temp),'-B',str(build)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    if result.returncode:
        print(result.stdout)
        raise SystemExit(result.returncode)
    manifest=(build/'audio-target.txt').read_text()
    assert 'src/cubeb_opensl.cpp' in manifest,manifest
    assert 'src/cubeb-jni.cpp' in manifest,manifest
    assert 'src/cubeb_aaudio.cpp' in manifest,manifest
    assert re.search(r'DEFINES=.*\bUSE_OPENSL\b',manifest),manifest
    assert re.search(r'DEFINES=.*\bUSE_AAUDIO\b',manifest),manifest
    assert re.search(r'LIBS=.*\bOpenSLES\b',manifest),manifest
    # Ensure the old cache entry was present: the normal Android setting wins.
    assert 'USE_OPENSL:BOOL=OFF' in (build/'CMakeCache.txt').read_text()
    print('PASS: real Android build settings + pinned Cubeb CMake: both outputs, JNI source and OpenSLES link; old OFF cache overridden')
