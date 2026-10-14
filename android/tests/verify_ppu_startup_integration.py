#!/usr/bin/env python3
"""Compile the actual Android allocator/worker body with a stub JIT.

Checks production wiring, shared budgets, cancellation and serial fallback.
This is not a full RPCS3/LLVM build or an Android-device performance test.
"""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[2]
source = (root / 'rpcs3/Emu/Cell/PPUThread.cpp').read_text()
native = (root / 'android/app/src/main/cpp/native-lib.cpp').read_text()
config = (root / 'rpcs3/Emu/system_config.h').read_text()

def block(text, signature):
    start = text.index(signature)
    opening = text.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]

phase = block(source, 'static bool ppu_startup_phase()')
priority = block(source, 'static bool ppu_normal_startup_priority()')
allocator = block(source, 'struct jit_core_allocator') + ';'
worker = block(source, 'struct thread_op\n') + ';'

# Confirm that the isolated cache is also used when releasing the JIT.
finalize = block(source, 'extern void ppu_finalize(const ppu_module<lv2_obj>& info, bool force_mem_release)')
initialize = block(source, 'bool ppu_initialize(const ppu_module<lv2_obj>& info, bool check_only, u64 file_size)')
assert 'duke::ppu::select_test_cache' in finalize and 'duke::ppu::select_test_cache' in initialize
assert 'std::string cache_path = info.cache;' in finalize
assert 'duke::ppu::startup_scope ppu_startup;' in native
assert native.index('duke::ppu::startup_scope ppu_startup;') < native.index('g_fxo->init(false, nullptr);', native.index('duke::ppu::startup_scope ppu_startup;'))
assert native.index('ppu_startup.finish();') < native.index('emuLock.unlock();', native.index('duke::ppu::startup_scope ppu_startup;'))
assert 'Duke PPU preparation:' in native
for field in ('android_ppu_compile_profile', 'android_ppu_normal_priority',
              'android_ppu_compile_diagnostics', 'android_ppu_test_cache_slot'):
    assert field in config and field in source

# Resource and route checks do not claim Kotlin/Compose compilation.
resources = {}
for locale in ('values', 'values-es'):
    tree = ET.parse(root / f'android/app/src/main/res/{locale}/ppu_startup_strings.xml')
    resources[locale] = {s.attrib['name'] for s in tree.getroot()}
assert resources['values'] == resources['values-es']
kotlin = (root / 'android/app/src/main/java/net/rpcs3/ui/settings/PpuStartupSettings.kt').read_text()
assert set(re.findall(r'R\.string\.(\w+)', kotlin)) <= resources['values']
for name in re.findall(r'this, "(Android PPU [^"]+)"', config):
    assert 'Core@@' + name in kotlin
for file in ('AdvancedSettingsScreen.kt', 'SettingItem.kt'):
    assert 'isPpuStartupSetting(' in (root / 'android/app/src/main/java/net/rpcs3/ui/settings' / file).read_text()

prefix = r'''
#define __ANDROID__ 1
#include "rpcs3/Emu/Cell/PPUCompilePolicy.h"
#include <atomic>
#include <cerrno>
#include <iostream>
#include <optional>
#include <semaphore>
#include <string>
#include <sys/resource.h>
#include <thread>
#include <utility>
#include <vector>
using u32=std::uint32_t; using u64=std::uint64_t; using s16=std::int16_t;
using s32=std::int32_t; using usz=std::size_t;
struct atomic_wait_timeout { u64 nanos; };
template<class T> struct atomic_t : std::atomic<T> {
    using std::atomic<T>::atomic;
    bool compare_and_swap_test(T from,T to) { return this->compare_exchange_strong(from,to); }
    void release(T v) { this->store(v); }
    void wait(T,atomic_wait_timeout t) { std::this_thread::sleep_for(std::chrono::nanoseconds(t.nanos)); }
};
template<int N> struct semaphore { std::counting_semaphore<N> value; explicit semaphore(int n):value(n){}
    void lock(){value.acquire();} void unlock(){value.release();} };
struct IntCfg { int value; int get()const{return value;} operator int()const{return value;} };
struct CpuCfg { std::string to_string()const{return "generic";} };
struct CoreCfg { IntCfg llvm_threads{0},android_ppu_compile_profile{0};
    bool android_ppu_normal_priority=false,android_ppu_compile_diagnostics=true; CpuCfg llvm_cpu; };
struct Config { CoreCfg core; } g_cfg;
enum class system_state { stopped, loading, stopping, running, paused, frozen, ready, starting };
struct Emulator { std::atomic<system_state> state{system_state::ready};
    system_state GetStatus(bool)const{return state.load();}
    bool IsStopped()const{return state.load()<=system_state::stopping;} } Emu;
std::atomic<u64> available{5120*duke::ppu::mib};
namespace utils { u64 get_avail_memory(){return available.load();}
    u64 get_total_memory(){return 8192*duke::ppu::mib;}
    unsigned get_thread_count(){return 8;} }
namespace thread_ctrl { struct scoped_priority { explicit scoped_priority(int){} }; }
struct Log { template<class... T> void notice(const char*,const T&...){}
    template<class... T> void warning(const char*,const T&...){}
    template<class... T> void success(const char*,const T&...){} } ppu_log;
'''

middle = r'''
struct jit_core_allocator* current_allocator=nullptr;
struct Registry { template<class T>T& get(){return *static_cast<T*>(current_allocator);} } registry;
auto* g_fxo=&registry;
enum class cpu_flag {exit};
struct CpuState { std::atomic<bool> exit{false}; bool all_of(cpu_flag)const{return exit.load();} };
struct cpu_thread { CpuState state; };
struct lv2_obj {};
template<class T> struct ppu_module {};
std::atomic<unsigned> active_jits{0},peak_jits{0},jobs{0};
struct jit_compiler {
    jit_compiler(std::initializer_list<int>,const std::string&,int) {
        unsigned n=++active_jits, peak=peak_jits;
        while(n>peak && !peak_jits.compare_exchange_weak(peak,n)){}
    }
    ~jit_compiler(){--active_jits;}
};
void ppu_initialize2(jit_compiler&,const ppu_module<lv2_obj>&,const std::string&,const std::string&) {
    ++jobs; std::this_thread::sleep_for(std::chrono::milliseconds(1));
}
atomic_t<u64> g_progr_pdone{0};
'''

tests = r'''
unsigned run(unsigned profile,unsigned user_max,system_state state,bool queue,bool stopped=false) {
    g_cfg.core.android_ppu_compile_profile.value=profile;
    g_cfg.core.llvm_threads.value=user_max;
    g_cfg.core.android_ppu_normal_priority=true;
    Emu.state=state; available=5120*duke::ppu::mib;
    std::optional<duke::ppu::startup_scope> preparing;
    if(queue)preparing.emplace();
    jit_core_allocator alloc;
    current_allocator=&alloc;
    if(queue)assert(ppu_startup_phase());
    assert(ppu_normal_startup_priority()==ppu_startup_phase());
    std::vector<std::pair<std::string,ppu_module<lv2_obj>>> work(30);
    atomic_t<u64> cv{0},done{0};
    cpu_thread cpu; cpu.state.exit=stopped;
    const std::string path="/cache/";
    ppu_module<lv2_obj> main;
    std::vector<std::jthread> threads;
    active_jits=0;peak_jits=0;jobs=0;
    for(int i=0;i<alloc.thread_count;++i) {
        thread_op op(&cv,&done,work,&cpu,main,path,alloc.sem);
        op.core_lock.lock();
        threads.emplace_back([op=std::move(op)]()mutable{op();});
    }
    threads.clear();
    assert(active_jits==0 && jobs==(stopped?0u:30u));
    assert(peak_jits<=static_cast<unsigned>(alloc.thread_count));
    return alloc.thread_count;
}
int main() {
    assert(run(0,0,system_state::ready,false)==2);
    assert(run(1,0,system_state::ready,false)==3);
    assert(run(2,0,system_state::ready,false)==4);
    assert(run(2,1,system_state::ready,false)==1);
    assert(run(2,2,system_state::ready,false)==2);
    // Android preparation is Running but must opt into the startup policy.
    assert(run(2,0,system_state::running,true)==4);
    assert(!duke::ppu::startup_preparation.load());
    // Gameplay retains the conservative policy, even with profile 2 saved.
    assert(run(2,0,system_state::running,false)==2);
    assert(run(2,0,system_state::paused,false)==2);
    assert(run(2,0,system_state::ready,false,true)==4);
    std::cout<<"PASS: actual Android PPU allocator and worker compile, respect global/user limits, recognize preparation, retain runtime limits and cancel jobs.\n";
}
'''

with tempfile.TemporaryDirectory() as temporary:
    folder=Path(temporary)
    cpp=folder/'integration.cpp'
    cpp.write_text(prefix+phase+'\n'+priority+'\n'+allocator+'\n'+middle+'\n'+worker+'\n'+tests)
    binary=folder/'verify'
    subprocess.run([os.environ.get('CXX','c++'),'-std=c++20','-pthread','-Wall','-Wextra',
                    '-Werror','-O2','-I',str(root),str(cpp),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True,timeout=15)
print('PASS: cache release path, Android preparation scope, localized resources and settings routing.')
