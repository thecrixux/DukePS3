#!/usr/bin/env python3
"""Compile the production pacer with a deterministic clock and simulate frame timings."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PACER = ROOT / 'rpcs3/Emu/RSX/VK/lsfg'
CLOCK = r'''
#pragma once
#include <chrono>
struct TestClock {
    using duration = std::chrono::nanoseconds;
    using rep = duration::rep;
    using period = duration::period;
    using time_point = std::chrono::time_point<TestClock>;
    static constexpr bool is_steady = true;
    static inline time_point value{};
    static time_point now() { return value; }
    static void advance(double seconds) {
        value += std::chrono::duration_cast<duration>(std::chrono::duration<double>(seconds));
    }
};
'''
MAIN = r'''
#include "lsfg_pacer.hpp"
#include <cassert>
#include <cmath>
#include <iostream>

lsfg::LsfgPacer make(unsigned target, float refresh, unsigned multiplier=2) {
    TestClock::value={};
    lsfg::LsfgPacer p;
    lsfg::LsfgPacerConfig c;
    c.multiplier=multiplier; c.target_rate=target;
    c.refresh_rate=refresh; c.source_rate=60.f;
    p.SetConfig(c);
    return p;
}
void tick(lsfg::LsfgPacer& p, unsigned frame, double seconds, size_t cap=3) {
    TestClock::advance(seconds);
    auto plan=p.Plan(cap, frame);
    assert(plan.generations<=cap && plan.generations<=p.MaxGenerations());
}
double stable(float fps, unsigned target, float refresh, double expected, unsigned mult=2) {
    auto p=make(target,refresh,mult);
    unsigned total=0;
    for (unsigned frame=0;frame<1000;++frame) {
        TestClock::advance(1.0/fps);
        auto plan=p.Plan(3,frame);
        assert(plan.generations<=3);
        if(frame>=400) total+=plan.generations;
    }
    const double average=total/600.0;
    assert(std::abs(average-expected)<0.025);
    assert(std::abs(p.Stats().source_rate-fps)<0.1);
    assert(p.Stats().rates_settled);
    std::cout << fps << " source FPS, " << refresh << " Hz, target=" << target
              << ": " << average << " generated per original\n";
    return average;
}
int main() {
    std::cout << std::unitbuf;
    stable(40,60,60,0.5);
    stable(30,60,60,1);
    stable(60,60,60,0);
    stable(40,120,120,2);
    stable(40,120,60,0.5); // target clamped to display
    stable(40,0,60,0); // fixed 2x cannot fit in 60Hz
    stable(40,0,120,1);
    stable(30,0,120,3,4);
    stable(45,90,90,1);
    stable(40,120,0,2); // unknown refresh

    auto p=make(60,60);
    unsigned total=0;
    for(unsigned i=0;i<1000;++i) {
        TestClock::advance(i%2 ? 0.030 : 0.020);
        const auto plan=p.Plan(1,i);
        assert(plan.generations<=1);
        if(i>=400) total+=plan.generations;
    }
    assert(std::abs(total/600.0-0.5)<0.025);
    TestClock::advance(0.8);
    assert(p.Plan(1,1000).generations==0); // no credit burst after pause
    for(unsigned i=1001;i<1120;++i) tick(p,i,0.025,1);
    assert(p.Stats().rates_settled && std::abs(p.Stats().source_rate-40)<0.1);
    assert(p.Plan(0,1120).generations==0);
    assert(!p.Stats().rates_settled && p.Stats().source_frames==0);
    assert(!p.Plan(1,1120).warm);

    p=make(60,120);
    for(unsigned i=0;i<240;++i) tick(p,i,1.0/60);
    for(unsigned i=240;i<360;++i) tick(p,i,1.0/30);
    assert(std::abs(p.Stats().source_rate-30)<0.1);
    assert(p.Stats().rate_jumps>0);
    for(unsigned i=360;i<600;++i) tick(p,i,1.0/60);
    assert(std::abs(p.Stats().source_rate-60)<0.1);

    // Emulate a GPU-bound loop: each generated frame costs an extra 12ms.
    p=make(0,120);
    size_t previous=0;
    unsigned frames=0, probes=0, disabled=0;
    while(std::chrono::duration<double>(TestClock::value.time_since_epoch()).count()<30) {
        TestClock::advance(0.025 + 0.012*previous);
        auto plan=p.Plan(1,frames++);
        previous=plan.generations;
        probes+=p.Stats().probing;
        if(frames>200 && plan.generations==0) ++disabled;
    }
    std::cout << "GPU-cost simulation: " << probes << " probe samples, "
              << disabled << " frames with interpolation held back\n";
    assert(probes>0 && disabled>0);
    // A slower game scene alone must not permanently suppress a useful 2x mode.
    p=make(0,120);
    for(unsigned i=0;i<240;++i) tick(p,i,1.0/60,1);
    for(unsigned i=240;i<600;++i) tick(p,i,1.0/30,1);
    assert(p.Stats().limit==1 && !p.Stats().probing);
    p.Reset();
    assert(p.Stats().source_rate==0 && p.Stats().cost_limit==0);
    std::cout << "Pacer jitter, pause, capacity, rate-change and cost checks passed\n";
}
'''
with tempfile.TemporaryDirectory() as directory:
    temp = Path(directory)
    (temp/'clock.hpp').write_text(CLOCK)
    for name in ('lsfg_pacer.hpp', 'lsfg_pacer.cpp'):
        text = (PACER/name).read_text()
        assert text.count('using Clock = std::chrono::steady_clock;') == 1
        (temp/name).write_text(text.replace('using Clock = std::chrono::steady_clock;',
                                            'using Clock = TestClock;'))
    (temp/'main.cpp').write_text(MAIN)
    command = [os.environ.get('CXX','c++'), '-std=c++20', '-Wall', '-Wextra', '-Werror',
               '-pedantic', '-include', str(temp/'clock.hpp')]
    if os.environ.get('SANITIZE') == '1':
        command += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    command += [str(temp/'lsfg_pacer.cpp'), str(temp/'main.cpp'), '-o', str(temp/'test')]
    subprocess.run(command, check=True)
    subprocess.run([str(temp/'test')], check=True)
