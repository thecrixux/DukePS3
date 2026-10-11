#!/usr/bin/env python3
"""Compile production Cubeb setup/callback with an Android/Cubeb fixture.

Exercises PCM output, preference/fallback metadata and real mutex contention.
This does not open an Android device or measure physical output underruns.
"""
from pathlib import Path
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
source = (root / 'rpcs3/Emu/Audio/Cubeb/CubebBackend.cpp').read_text()
def function(signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

prefix = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <functional>
#include <future>
#include <iostream>
#include <mutex>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include "Emu/Audio/AndroidAudioDiagnostics.h"
using u8=std::uint8_t; using u32=std::uint32_t; using f64=double;
#define ensure(x) assert(x)
struct Logger {
    template<class... T> void error(const char*, T&&...) {}
    template<class... T> void notice(const char*, T&&...) {}
    int warning_count=0;
    template<class... T> void warning(const char*, T&&...) { ++warning_count; }
} Cubeb;
namespace fmt { template<class... T> [[noreturn]] void throw_exception(const char*, T&&...) { throw std::runtime_error("layout"); } }
struct ConfigString { std::string value="auto"; std::string to_string() const { return value; } };
struct { struct { ConfigString android_backend; } audio; } g_cfg;
struct cubeb {}; struct cubeb_stream {};
using cubeb_devid=void*; using cubeb_state=int;
constexpr int CUBEB_ERROR=-1, CUBEB_DEVICE_TYPE_OUTPUT=1, CUBEB_LOG_NORMAL=1;
constexpr int CUBEB_SAMPLE_S16NE=1, CUBEB_SAMPLE_FLOAT32NE=2;
constexpr int CUBEB_LAYOUT_MONO=1, CUBEB_LAYOUT_STEREO=2, CUBEB_LAYOUT_STEREO_LFE=3;
constexpr int CUBEB_LAYOUT_QUAD=4, CUBEB_LAYOUT_QUAD_LFE=5, CUBEB_LAYOUT_3F2_LFE=6, CUBEB_LAYOUT_3F4_LFE=8;
constexpr int CUBEB_STREAM_PREF_DISABLE_DEVICE_SWITCHING=1, CUBEB_STREAM_PREF_NONE=0;
struct cubeb_stream_params { int format=0; u32 rate=0, channels=0; int layout=0, prefs=0; };
using AudioFreq=u32; using AudioSampleSize=u32; using AudioChannelCnt=u32;
enum class audio_channel_layout { automatic, mono, stereo, stereo_lfe, quadraphonic, quadraphonic_lfe, surround_5_1, surround_7_1 };
namespace audio_device_enumerator { constexpr std::string_view DEFAULT_DEV_ID="@@@default@@@"; }
template<class T> struct AtomicFixture { T value{}; T observe() const { return value; } void operator=(T v) { value=v; } operator T() const { return value; } };
struct AudioBackend {
    std::timed_mutex m_cb_mutex;
    std::mutex m_state_cb_mutex;
    bool m_playing=false;
    std::function<u32(u32,void*)> m_write_callback;
    AudioFreq m_sampling_rate=48000; AudioSampleSize m_sample_size=4;
    audio_channel_layout m_layout=audio_channel_layout::stereo;
    void setup_channel_layout(u32, u32, audio_channel_layout layout, Logger&) { m_layout=layout; }
    u32 get_channels() const { return 2; }
    u32 get_sample_size() const { return m_sample_size; }
    u32 get_sampling_rate() const { return m_sampling_rate; }
    bool get_convert_to_s16() const { return m_sample_size==2; }
};
struct CubebBackend : AudioBackend {
    CubebBackend();
    static constexpr f64 AUDIO_MIN_LATENCY=512.0/48000;
    cubeb* m_ctx=nullptr; cubeb_stream* m_stream=nullptr;
    bool m_dev_collection_cb_enabled=false;
    std::string m_default_device;
    std::array<u8,32> m_last_sample{};
    AtomicFixture<u32> full_sample_size;
    AtomicFixture<bool> m_reset_req;
    bool Initialized() { return m_ctx!=nullptr; }
    bool Open(std::string_view, AudioFreq, AudioSampleSize, AudioChannelCnt, audio_channel_layout);
    void Close(); void Play(); void Pause();
    static long data_cb(cubeb_stream*, void*, const void*, void*, long);
    static void state_cb(cubeb_stream*, void*, cubeb_state) {}
    static void device_collection_changed_cb(cubeb*, void*) {}
    static void log_cb(const char*, ...) {}
    struct device_handle { cubeb_devid handle=nullptr; std::string id="default"; u32 ch_cnt=2; bool valid=true; };
    device_handle GetDevice(std::string_view={}) { return {}; }
};
cubeb fake_context;
cubeb_stream fake_stream;
std::string requested_backend, actual_backend="aaudio";
u32 minimum_latency=0, opened_latency=0;
bool fail_init=false, log_callback_installed=false;
int cubeb_init(cubeb** ctx, const char*, const char* backend) {
    assert(log_callback_installed); // Preferred-output initialization failures must be captured.
    requested_backend=backend ? backend : "(null)";
    if (fail_init) return CUBEB_ERROR;
    *ctx=&fake_context; return 0;
}
int cubeb_register_device_collection_changed(cubeb*, int, void (*)(cubeb*,void*), void*) { return 0; }
void cubeb_set_log_callback(int, void (*)(const char*,...)) { log_callback_installed=true; }
const char* cubeb_get_backend_id(cubeb*) { return actual_backend.c_str(); }
struct cubeb_backend_names { const char* const* names; std::size_t count; };
cubeb_backend_names cubeb_get_backend_names() {
    static const char* const names[]={"aaudio", "opensl"}; return {names,2};
}
int cubeb_get_min_latency(cubeb*, cubeb_stream_params*, u32* latency) { *latency=minimum_latency; return 0; }
int cubeb_stream_init(cubeb*, cubeb_stream** stream, const char*, void*, void*, cubeb_devid,
    cubeb_stream_params*, u32 latency, long (*)(cubeb_stream*,void*,const void*,void*,long),
    void (*)(cubeb_stream*,void*,cubeb_state), void*) {
    *stream=&fake_stream; opened_latency=latency; return 0;
}
int cubeb_stream_start(cubeb_stream*) { return 0; }
int cubeb_stream_stop(cubeb_stream*) { return 0; }
void cubeb_stream_destroy(cubeb_stream*) {}
int cubeb_stream_set_volume(cubeb_stream*, float) { return 0; }
'''
tests = r'''
int main() {
    using android_audio::g_diagnostics;
    for (const auto& pair : {std::pair{"auto", "(null)"}, {"aaudio", "aaudio"},
                            {"opensl", "opensl"}, {"unknown", "(null)"}}) {
        g_cfg.audio.android_backend.value=pair.first;
        CubebBackend backend;
        assert(requested_backend==pair.second);
        auto snapshot=g_diagnostics.get();
        assert(snapshot.preference==pair.first && snapshot.backend=="aaudio");
    }
    // A preferred backend can fall back: metadata must retain actual identity.
    g_cfg.audio.android_backend.value="opensl";
    CubebBackend backend;
    assert(backend.Open("",48000,4,2,audio_channel_layout::stereo));
    assert(opened_latency==512);
    auto snapshot=g_diagnostics.get();
    assert(snapshot.backend=="aaudio" && snapshot.preference=="opensl");
    assert(Cubeb.warning_count==2); // Both attempts preferring OpenSL fell back.
    actual_backend="opensl";
    CubebBackend actual_opensl;
    assert(g_diagnostics.get().backend=="opensl" && Cubeb.warning_count==2);
    actual_backend="aaudio";
    g_diagnostics.set_backend("opensl", "aaudio");
    assert(snapshot.stream_open && !snapshot.playing);
    assert(snapshot.rate==48000 && snapshot.channels==2 && snapshot.bytes_per_sample==4);
    assert(snapshot.requested_latency_frames==512);
    std::array<float,8> pcm;
    pcm.fill(7);
    auto callback=[&] { return CubebBackend::data_cb(&fake_stream,&backend,nullptr,pcm.data(),4); };
    // Opening/paused silence is excluded.
    assert(callback()==4); for (float value:pcm) assert(value==0);
    assert(g_diagnostics.get().missing_callback_silence_callbacks==0);
    backend.Play();
    backend.m_write_callback=[](u32 bytes,void* output) {
        std::fill_n(static_cast<float*>(output),bytes/4,0.25f); return bytes;
    };
    assert(callback()==4); for (float value:pcm) assert(value==0.25f);
    snapshot=g_diagnostics.get();
    assert(snapshot.delivered_callbacks==1 && snapshot.requested_frames==4 && snapshot.short_read_callbacks==0);
    // Unaligned/short writes keep the existing last-PCM-frame fill behavior.
    backend.m_write_callback=[](u32,void* output) {
        auto p=static_cast<float*>(output); p[0]=1; p[1]=2; p[2]=3; p[3]=4; return 19;
    };
    assert(callback()==4);
    assert((pcm==std::array<float,8>{1,2,3,4,3,4,3,4}));
    snapshot=g_diagnostics.get();
    assert(snapshot.short_read_callbacks==1 && snapshot.missing_frames==2);
    backend.m_write_callback=[](u32,void*) { return 0; };
    assert(callback()==4);
    assert((pcm==std::array<float,8>{3,4,3,4,3,4,3,4}));
    assert(g_diagnostics.get().missing_frames==6);
    // Real timed mutex held by a different thread: zero output and one event.
    std::promise<void> held, release;
    auto future=release.get_future();
    std::thread blocker([&] { std::lock_guard lock(backend.m_cb_mutex); held.set_value(); future.wait(); });
    held.get_future().wait();
    assert(callback()==4); for (float value:pcm) assert(value==0);
    release.set_value(); blocker.join();
    assert(g_diagnostics.get().mutex_timeout_callbacks==1);
    backend.m_reset_req=true; assert(callback()==4); backend.m_reset_req=false;
    assert(g_diagnostics.get().reset_silence_callbacks==1);
    backend.m_write_callback={}; assert(callback()==4);
    assert(g_diagnostics.get().missing_callback_silence_callbacks==1);
    backend.Pause(); assert(callback()==4);
    assert(g_diagnostics.get().missing_callback_silence_callbacks==1);
    assert(!g_diagnostics.get().playing);
    backend.Close(); snapshot=g_diagnostics.get();
    assert(!snapshot.stream_open && !snapshot.playing && snapshot.missing_frames==6);
    // Reopening resets counters and advances the stream identity for deltas.
    minimum_latency=2048;
    assert(backend.Open("",48000,2,2,audio_channel_layout::stereo));
    assert(opened_latency==2048);
    auto next=g_diagnostics.get();
    assert(next.stream_generation==snapshot.stream_generation+1 && next.missing_frames==0);
    assert(next.bytes_per_sample==2 && next.requested_latency_frames==2048);
    backend.Close();
    fail_init=true; CubebBackend failed;
    assert(!failed.Initialized() && g_diagnostics.get().backend.empty());
    assert(CubebBackend::data_cb(&fake_stream,&backend,nullptr,nullptr,4)==CUBEB_ERROR);
    assert(CubebBackend::data_cb(&fake_stream,&backend,nullptr,pcm.data(),0)==0);
    assert(CubebBackend::data_cb(nullptr,&backend,nullptr,pcm.data(),4)==CUBEB_ERROR);
    std::cout<<"PASS: production Cubeb preference/Open/Play/Pause/Close/callback; PCM preserved, real mutex timeout, source shortages, fallback identity and lifecycle\n";
}
'''
functions = [function(signature) for signature in [
    'CubebBackend::CubebBackend()', 'bool CubebBackend::Open(', 'void CubebBackend::Close()',
    'void CubebBackend::Play()', 'void CubebBackend::Pause()', 'long CubebBackend::data_cb(']]
with tempfile.TemporaryDirectory() as directory:
    temp = Path(directory)
    cpp = temp / 'audio.cpp'
    cpp.write_text(prefix + '\n'.join(functions) + tests)
    command = [os.environ.get('CXX', 'c++'), '-std=c++20', '-Wall', '-Wextra', '-Werror',
               '-pthread', '-D__ANDROID__', '-I', str(root / 'rpcs3')]
    subprocess.run(command + [str(cpp), '-o', str(temp / 'audio')], check=True)
    subprocess.run([str(temp / 'audio')], check=True)
