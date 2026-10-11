#!/usr/bin/env python3
"""Exercise production audio waiting decisions with ready/late/idle port sequences.

Compiles the actual hysteresis and buffering decision block from cellAudio.cpp.
Fixtures supply clock, port-tag observations and queue/wait operations. This is
not an Android playback test and does not reproduce the device scheduler.
"""
from pathlib import Path
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
source = (root / 'rpcs3/Emu/Cell/Modules/cellAudio.cpp').read_text()
start = source.index('\tu32 untouched_expected = 0;')
policy = source[start:source.index('\n\t// Producer-side counters:', start)]
start = source.index('\t\t\t// Fast path for 0 ports active')
end = source.index('\n\t\t// Mix', start)
decisions = source[start:end].rstrip()
assert decisions.endswith('\t\t}')
decisions = decisions[:-len('\t\t}')]
start = source.index('\t\tmixed_blocks++;')
pcm_check = source[start:source.index('\n\t\t// Enqueue', start)]

prefix = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <limits>
using u32=std::uint32_t; using u64=std::uint64_t;
constexpr u32 AUDIO_BUFFER_SAMPLES=256;
enum class Action { mixed, silence, skipped, waited };
namespace thread_ctrl { void wait_for(u64) { throw Action::waited; } }
struct Logger { template<class... T> void trace(const char*, T...) {} } cellAudio;
struct { struct { bool disable_sampling_skip=false; } audio; } g_cfg;
struct Config {
    u64 fully_untouched_timeout=10666, partially_untouched_timeout=21332;
    u32 audio_channels=2;
    struct { bool dump_to_file=false; } raw;
} cfg;
struct Ring { void enqueue_silence() { throw Action::silence; } } queue;
'''

tests = r'''
    u64 silence_no_ports=0, silence_untouched=0, skipped_untouched=0;
    u64 partial_mix=0, incomplete_mix=0;
    auto* ringbuffer=&queue;
    auto advance=[](u64) { throw Action::skipped; };
    auto step=[&](u32 active_ports, u32 untouched, u32 in_progress=0,
                  u64 time_since_last_period=5333, u32 incomplete=0) {
        const u64 timestamp=0, enqueued_buffers=8;
        // Same clamp applied before the production decision block.
        untouched_expected=std::min(untouched_expected,active_ports);
        try {
            for (;;) {
'''

# Silence needs to allow the statements after enqueue_silence() to run: the
# decision loop's next advance distinguishes silence from skipped periods.
prefix = prefix.replace(
    'struct Ring { void enqueue_silence() { throw Action::silence; } } queue;',
    'struct Ring { bool silent=false; void enqueue_silence() { silent=true; } } queue;')
tests = tests.replace(
    'auto advance=[](u64) { throw Action::skipped; };',
    'auto advance=[&](u64) { auto action=queue.silent ? Action::silence : Action::skipped; '
    'queue.silent=false; throw action; };')

tests_end = r'''
                return Action::mixed;
            }
        } catch (Action action) { return action; }
    };

    // Startup timeout identifies an idle port. Seven ready periods retain the
    // expectation, but the eighth restores waiting for a late audio block.
    assert(step(1,1,0,11000)==Action::skipped);
    assert(untouched_expected==1 && skipped_untouched==1);
    assert(step(1,0)==Action::mixed);
    const auto streak=untouched_below_streak;
    for(int i=0;i<100;++i) assert(step(1,0,1)==Action::waited);
    assert(untouched_below_streak==streak); // Polls are not elapsed periods.
    for(int i=0;i<6;++i) assert(step(1,0)==Action::mixed);
    assert(untouched_expected==1);
    assert(step(1,0)==Action::mixed && untouched_expected==0);
    assert(step(1,1)==Action::waited);
    assert(step(1,0)==Action::mixed); // Late write arrives while still waiting.

    // A permanently idle second port may flicker touched once. Do not make
    // the next quiet period incur the full partial-port timeout repeatedly.
    assert(step(2,1,0,22000)==Action::mixed);
    assert(partial_mix==1 && untouched_expected==1);
    for(int i=0;i<30;++i) {
        assert(step(2,0)==Action::mixed);
        assert(step(2,1)==Action::mixed);
    }
    assert(untouched_expected==1);

    // A disappearing port cannot keep the expectation above the active count.
    assert(step(3,2,0,22000)==Action::mixed && untouched_expected==2);
    assert(step(1,0)==Action::mixed && untouched_expected<=1);
    assert(step(0,0)==Action::silence);
    assert(untouched_expected==0 && untouched_below_streak==0);
    assert(silence_no_ports==1);
    assert(step(1,1)==Action::waited); // New port gets a fresh waiting policy.

    // Preserve partial mixing when one port has PCM and another times out.
    assert(step(2,1,1,22000,1)==Action::mixed);
    assert(partial_mix==3 && incomplete_mix==1);
    assert(step(2,2)==Action::waited);
    assert(step(2,2,0,22000)==Action::skipped);
    assert(step(2,2)==Action::silence && silence_untouched==1);

    // Repeated late periods separated by ready audio: the ready streak must
    // restore waiting each time, instead of repeatedly renewing a long hold.
    assert(step(0,0)==Action::silence);
    for(int burst=0;burst<100;++burst) {
        assert(step(1,1,0,11000)==Action::skipped);
        for(int i=0;i<14;++i) assert(step(1,0)==Action::mixed);
        assert(step(1,1)==Action::waited);
        assert(step(1,0)==Action::mixed);
    }

    // Execute the actual post-mix PCM inspection. It counts natural silence
    // without mutating samples; inspection is disabled outside a WAV capture.
    u64 mixed_blocks=0, empty_mixes=0, checked_mixes=0;
    std::array<float,512> pcm{};
    float* buf=pcm.data();
    const auto inspect=[&] {
'''

tail = r'''
    };
    inspect();
    assert(mixed_blocks==1 && checked_mixes==0 && empty_mixes==0);
    cfg.raw.dump_to_file=true;
    inspect();
    assert(checked_mixes==1 && empty_mixes==1);
    pcm.fill(-0.0f);
    inspect();
    assert(empty_mixes==2);
    pcm[256]=0.02f;
    const auto original=pcm;
    inspect();
    assert(empty_mixes==2 && pcm==original);
    pcm[256]=std::numeric_limits<float>::quiet_NaN();
    inspect();
    assert(empty_mixes==2); // Do not misclassify non-finite PCM as silence.
    std::cout << "PASS: production waiting decisions, late/idle/closed ports, "
        "partial mixing, polling and non-mutating PCM inspection.\n";
}
'''

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    cpp = path / 'audio_producer.cpp'
    cpp.write_text(prefix + '\nint main() {\n' + policy + tests + decisions +
                   tests_end + pcm_check + tail)
    subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++20', '-Wall',
                    '-Wextra', '-Werror', '-O2', str(cpp), '-o',
                    str(path / 'verify_audio_producer')], check=True)
    subprocess.run([str(path / 'verify_audio_producer')], check=True)
