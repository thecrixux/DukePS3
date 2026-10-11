#!/usr/bin/env python3
"""Exercise production settings/JNI and check Android resource/build wiring."""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
VK=ROOT/'rpcs3/Emu/RSX/VK'
JAVA=ROOT/'android/app/src/main/java/net/rpcs3'
cpp=(VK/'VKFrameGeneration.cpp').read_text()
native=(ROOT/'android/app/src/main/cpp/native-lib.cpp').read_text()

def function(text,signature):
    start=text.index(signature); end=text.index('{',start)+1; depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}'); end+=1
    return text[start:end]

prefix=r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <mutex>
#include <string>
#include "settings.h"
namespace vk {
namespace {
std::mutex g_frame_generation_lock;
std::string g_frame_generation_cache;
frame_generation_settings g_frame_generation_settings;
frame_generation_status g_frame_generation_status;
std::atomic<u64> g_frame_generation_presented{0}, g_frame_generation_generated{0}, g_frame_generation_revision{0};
std::atomic<s32> g_frame_generation_refresh_mhz{0};
constexpr u32 dis_min_side_min=128, dis_min_side_max=720;
constexpr u64 acquire_timeout_min_ns=3000000, acquire_timeout_max_ns=12000000;
}
'''
types=r'''
#pragma once
#include <cstdint>
using u32=uint32_t; using u64=uint64_t; using s32=int32_t; using usz=size_t;
using VkSemaphore=int; using VkImage=int; using VkImageLayout=int; using VkCommandBuffer=int;
'''
main=r'''
}
#define JNIEXPORT
#define JNICALL
struct JNIEnv {};
using jobject=void*; using jboolean=unsigned char; using jint=int;
constexpr jboolean JNI_TRUE=1;
'''
tests=r'''
int main() {
    using namespace vk;
    assert(get_frame_generation_shader_cache().empty());
    Java_net_rpcs3_RPCS3_frameGenConfigure(nullptr,nullptr,JNI_TRUE,2,60,40,0,180);
    assert(frame_generation_reserved_images()==0); // LSFG requires its source
    const auto prior=frame_generation_shader_revision();
    set_frame_generation_status({.ready=true});
    Java_net_rpcs3_RPCS3_frameGenConfigure(nullptr,nullptr,JNI_TRUE,2,60,40,1,180);
    assert(get_frame_generation_settings().engine==frame_generation_engine::dis);
    assert(frame_generation_reserved_images()==3); // DIS requires no cache/DLL
    assert(frame_generation_shader_revision()==prior+1);
    assert(!get_frame_generation_status().ready);
    Java_net_rpcs3_RPCS3_frameGenConfigure(nullptr,nullptr,JNI_TRUE,2,60,40,1,180);
    assert(frame_generation_shader_revision()==prior+1);
    Java_net_rpcs3_RPCS3_frameGenConfigure(nullptr,nullptr,JNI_TRUE,2,60,40,1,360);
    assert(frame_generation_shader_revision()==prior+2);
    set_frame_generation_shader_cache({});
    assert(frame_generation_reserved_images()==3);
    Java_net_rpcs3_RPCS3_frameGenConfigure(nullptr,nullptr,JNI_TRUE,2,0,40,1,180);
    assert(frame_generation_reserved_images()==1);
    Java_net_rpcs3_RPCS3_frameGenConfigure(nullptr,nullptr,0,2,60,40,1,180);
    assert(frame_generation_reserved_images()==0);
    Java_net_rpcs3_RPCS3_frameGenConfigure(nullptr,nullptr,JNI_TRUE,-2,-60,-40,1,-180);
    auto config=get_frame_generation_settings();
    assert(config.multiplier==2 && config.target_rate==0 && config.flow_scale_percent==25);
    assert(config.dis_min_side==128);
    Java_net_rpcs3_RPCS3_frameGenConfigure(nullptr,nullptr,JNI_TRUE,200,60,200,1,2000);
    config=get_frame_generation_settings();
    assert(config.multiplier==4 && config.flow_scale_percent==100 && config.dis_min_side==720);
    Java_net_rpcs3_RPCS3_frameGenConfigure(nullptr,nullptr,JNI_TRUE,2,60,40,99,180);
    assert(get_frame_generation_settings().engine==frame_generation_engine::lsfg);
    assert(frame_generation_reserved_images()==0);
    frame_generation_count_generated(42);
    assert(frame_generation_generated_count()==42);
    std::cout << "DIS/LSFG JNI selection, no-DLL reservation, revision, clamping and counter checks passed\n";
}
'''
source=prefix+cpp[cpp.index('\tvoid set_frame_generation_shader_cache'):cpp.index('\tstruct frame_generator::impl')]+main
source+=function(native,'extern "C" JNIEXPORT void JNICALL Java_net_rpcs3_RPCS3_frameGenConfigure(')+tests
with tempfile.TemporaryDirectory() as directory:
    temp=Path(directory)
    header=(VK/'VKFrameGeneration.h').read_text().replace('#include "VulkanAPI.h"','#include "types.h"').replace('#include "util/types.hpp"','')
    (temp/'types.h').write_text(types)
    (temp/'settings.h').write_text(header)
    (temp/'test.cpp').write_text(source)
    subprocess.run([os.environ.get('CXX','c++'),'-std=c++20','-Wall','-Wextra','-Werror',
                    '-Wno-missing-field-initializers',str(temp/'test.cpp'),'-o',str(temp/'test')],check=True)
    subprocess.run([str(temp/'test')],check=True)

defaults={}
for path in (ROOT/'android/app/src/main/res/values').glob('*.xml'):
    for node in ET.parse(path).getroot():
        if node.tag=='string':
            name=node.attrib['name']; assert name not in defaults,(name,path)
            defaults[name]=''.join(node.itertext())
for path in (JAVA/'framegen/FrameGen.kt',JAVA/'ui/framegen/FrameGenPanel.kt'):
    text=path.read_text()
    assert set(re.findall(r'R\.string\.(\w+)',text))<=defaults.keys()
spanish=ET.parse(ROOT/'android/app/src/main/res/values-es/framegen_dis_strings.xml').getroot()
for node in spanish:
    name=node.attrib['name']; assert name in defaults
    assert re.findall(r'%\d+\$[a-z]',node.text or '')==re.findall(r'%\d+\$[a-z]',defaults[name])
framegen=(JAVA/'framegen/FrameGen.kt').read_text()
assert 'get() = this == Lsfg' in framegen
assert 'get() = !engine.needsShaderSource || imported' in framegen
assert 'FrameGenPrefs.isEnabled(prefs) && state.value.usable' in framegen
assert 'engine.value,' in framegen and 'FrameGenPrefs.disPreset(prefs).minSide' in framegen
assert 'val Default = Fast' in framegen
activity=(JAVA/'RPCS3Activity.kt').read_text()
assert 'FrameGen.state.value.usable' in activity
panel=(JAVA/'ui/framegen/FrameGenPanel.kt').read_text()
assert 'if (engine.needsShaderSource)' in panel and 'FrameGenEngine.Dis' in panel
assert 'delay(1000)' in panel and 'state.generatedFrames' in panel
assert '"frame_generation"' in native and '"dis_min_side"' in native
cmake=(ROOT/'rpcs3/Emu/CMakeLists.txt').read_text()
for name in ('dis_flow.cpp','dis_shaders.cpp'):
    assert cmake.count('RSX/VK/dis/'+name)==1
print('Android engine gating, resources, translations, live counter and CMake wiring checks passed')
