#!/usr/bin/env python3
"""Compile actual diagnostic snapshots and benchmark JNI with device/Emu fixtures.

No Vulkan device is created. Checks Android API wiring, lifetime-safe copies,
consistent dimensions across concurrent reads, and JSON with FG disabled.
Set JSON_INCLUDE if nlohmann/json.hpp is not on the default include path.
"""
from pathlib import Path
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
vk = root / 'rpcs3/Emu/RSX/VK'
native = (root / 'android/app/src/main/cpp/native-lib.cpp').read_text()
start = native.index('Java_net_rpcs3_RPCS3_benchmarkContext(')
end = native.index('\n}', start) + 2
function = native[start:end]
helpers = (vk / 'VKHelpers.cpp').read_text()
start = helpers.index('\t\tg_renderer_diagnostics.set_device(')
identity = helpers[start:helpers.index('\n#endif', start)]
present = (vk / 'VKPresent.cpp').read_text()
start = present.index('\tvk::g_renderer_diagnostics.set_present(')
present_call = present[start:present.index(';', start) + 1]

prefix = r'''
#include <atomic>
#include <cassert>
#include <iostream>
#include <thread>
#include <nlohmann/json.hpp>
#include "VKDiagnostics.h"
#include "Emu/Audio/AndroidAudioDiagnostics.h"
using u32 = std::uint32_t;
using jstring = std::string; using jobject = void*;
struct JNIEnv {};
std::string wrap(JNIEnv*, std::string s) { return s; }
namespace rpcs3 { std::string get_verbose_version() { return "test"; } }
struct { std::string GetTitleID() { return "TEST00001"; } } Emu;
struct Resolution { std::string to_string() { return "720p"; } };
struct Scale { u32 get() { return 150; } };
struct { struct { Resolution resolution; Scale resolution_scale_percent; } video;
    std::string to_string() { return "Resolution: 720p\nResolution Scale: 150"; }
} g_cfg;
namespace vk {
enum class frame_generation_engine { lsfg, dis };
struct Settings { bool enabled=false; frame_generation_engine engine=frame_generation_engine::dis;
    u32 target_rate=60, multiplier=2, flow_scale_percent=40, dis_min_side=128; };
struct Status { bool ready=false, unsupported=false;
    u32 width=0, height=0, flow_width=0, flow_height=0, guest_width=0, guest_height=0; };
float frame_generation_refresh_rate() { return 60; }
Settings get_frame_generation_settings() { return {}; }
Status get_frame_generation_status() { return {}; }
u32 frame_generation_presented_count() { return 0; }
u32 frame_generation_generated_count() { return 0; }
}
struct GPU {
    std::string get_driver_name() { return "Mali test"; }
    std::string get_driver_version() { return "1"; }
    std::string get_driver_vk_version() { return "1.3"; }
};
void init_device() {
    using vk::g_renderer_diagnostics;
    GPU gpu; std::string gpu_name="Mali-G615"; u32 g_driver_vendor=13;
'''
fixture = r'''
}
void record_present() {
    u32 guest_width=1280, guest_height=720, buffer_pitch=5120;
    u32 buffer_width=1920, buffer_height=1080;
    struct { u32 width=2400, height=1080; } m_swapchain_dims;
    void* image_to_flip=reinterpret_cast<void*>(1);
'''
tests = r'''
int main() {
    using namespace vk;
    init_device(); record_present();
    android_audio::g_diagnostics.set_backend("opensl", "aaudio");
    android_audio::g_diagnostics.opened(48000, 2, 4, 512);
    android_audio::g_diagnostics.set_playing(true);
    android_audio::g_diagnostics.delivered(128, 96);
    auto report=nlohmann::json::parse(Java_net_rpcs3_RPCS3_benchmarkContext(nullptr,nullptr));
    assert(!report["frame_generation"]["enabled"].get<bool>());
    assert(report["video"]["ps3_video_mode"]=="720p");
    assert(report["video"]["render_scale_percent"]==150);
    auto audio=report["audio"];
    assert(audio["preference"]=="opensl" && audio["actual_backend"]=="aaudio");
    assert(audio["requested_latency_frames"]==512 && audio["sampling_rate"]==48000);
    assert(audio["missing_frames"]==32 && audio["short_read_callbacks"]==1);
    assert(audio["mutex_timeout_callbacks"]==0);
    assert(audio["stream_generation"]==1 && audio["stream_open"]==true);
    auto video=report["video"]["runtime"];
    assert(video["available"]==true && video["gpu"]=="Mali-G615");
    assert(video["driver"]=="Mali test" && video["guest_pitch_bytes"]==5120);
    assert(video["guest_width"]==1280 && video["source_width"]==1920);
    assert(video["source_height"]==1080 && video["output_width"]==2400);
    auto saved=g_renderer_diagnostics.get();
    g_renderer_diagnostics.reset();
    assert(saved.gpu_name=="Mali-G615" && saved.source_width==1920);
    report=nlohmann::json::parse(Java_net_rpcs3_RPCS3_benchmarkContext(nullptr,nullptr));
    assert(report["video"]["runtime"]["available"]==false);
    assert(report["video"]["runtime"]["guest_width"]==0);
    init_device();
    std::atomic<bool> done=false;
    std::thread writer([&] {
        for (u32 i=1; i<=100000; ++i)
            g_renderer_diagnostics.set_present(i,i*2,i*4,i*3,i*6,i*5,i*10,true);
        done=true;
    });
    do {
        const auto s=g_renderer_diagnostics.get();
        assert(s.guest_height==s.guest_width*2 && s.guest_pitch_bytes==s.guest_width*4);
        assert(s.source_width==s.guest_width*3 && s.source_height==s.guest_width*6);
        assert(s.output_width==s.guest_width*5 && s.output_height==s.guest_width*10);
    } while (!done.load());
    writer.join();
    std::cout<<"PASS: Android device/present API wiring, FG-off JSON, teardown and coherent concurrent copies\n";
}
'''
with tempfile.TemporaryDirectory() as directory:
    temp = Path(directory)
    cpp = temp / 'diagnostics.cpp'
    cpp.write_text(prefix + identity + fixture + present_call + '\n}\n'
                   + 'jstring ' + function + '\n' + tests)
    command = [os.environ.get('CXX', 'c++'), '-std=c++20', '-Wall', '-Wextra', '-Werror',
               '-Wno-missing-field-initializers', '-pthread', '-I', str(vk), '-I', str(root / 'rpcs3')]
    if os.environ.get('JSON_INCLUDE'):
        command += ['-I', os.environ['JSON_INCLUDE']]
    subprocess.run(command + [str(cpp), '-o', str(temp / 'diagnostics')], check=True)
    subprocess.run([str(temp / 'diagnostics')], check=True)
