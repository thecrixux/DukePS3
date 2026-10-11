#!/usr/bin/env python3
"""Run production swapchain selection and FG dispatch logic with a fake Vulkan device.

No GPU required. This checks control flow, not driver or shader behaviour.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
VK = ROOT / 'rpcs3/Emu/RSX/VK'


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


swap = (VK / 'vkutils/swapchain.cpp').read_text()
present = (VK / 'VKPresent.cpp').read_text()
core = (VK / 'vkutils/swapchain_core.h').read_text()
device = (VK / 'vkutils/device.cpp').read_text()
init = function(swap, 'bool swapchain_WSI::init()')
selection = init[init.index('u32 nb_swap_images ='):init.index('\n\t\tif (old_swapchain)')]
reset = init[init.index('{') + 1:init.index('if (dev.get_present_queue()')]
feature = next(line for line in device.splitlines()
               if 'enabled_features.shaderStorageImageExtendedFormats =' in line)

mode_selection = init[init.index('VkPresentModeKHR swapchain_present_mode ='):init.index('rsx_log.notice("Swapchain: present mode')]
prefix = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <vector>
#define ANDROID 1
#define CHECK_RESULT(x) do { if ((x) != 0) throw std::runtime_error("create failed"); } while (false)
using u32 = uint32_t; using u64 = uint64_t; using usz = size_t;
using VkImage = int; using VkImageLayout = int; using VkSemaphore = int; using VkResult = int;
using VkPresentModeKHR=int;
constexpr int VK_PRESENT_MODE_FIFO_KHR=2, VK_PRESENT_MODE_MAILBOX_KHR=1;
constexpr int VK_PRESENT_MODE_IMMEDIATE_KHR=0, VK_PRESENT_MODE_FIFO_RELAXED_KHR=3;
enum class vsync_mode { off, adaptive, full };
struct { struct { vsync_mode vsync=vsync_mode::off; } video; } g_cfg;
using VkSurfaceTransformFlagBitsKHR = u32;
constexpr u32 VK_IMAGE_USAGE_TRANSFER_SRC_BIT = 1, VK_IMAGE_USAGE_TRANSFER_DST_BIT = 2;
constexpr u32 VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT = 16;
constexpr u32 VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR = 1;
constexpr int VK_SUCCESS = 0, VK_SUBOPTIMAL_KHR = 1, VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR = 100;
constexpr int VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR = 1, VK_SHARING_MODE_EXCLUSIVE = 0;
constexpr u32 umax = UINT32_MAX;
constexpr int VK_ERROR_OUT_OF_DATE_KHR=-1, VK_ERROR_SURFACE_LOST_KHR=-2;
using s32=int32_t; using s64=int64_t;
template<class T> u32 size32(const T& v) { return static_cast<u32>(v.size()); }
struct Log { template<class... T> void warning(T...) {} } rsx_log;
struct Extent { u32 width=1280, height=720; };
struct Surface { u32 minImageCount=2, maxImageCount=8, currentTransform=1, supportedTransforms=1;
    u32 supportedUsageFlags=18; Extent minImageExtent; };
struct VkSwapchainCreateInfoKHR {
    int sType{}, surface{}, imageFormat{}, imageColorSpace{}, preTransform{}, compositeAlpha{};
    int imageArrayLayers{}, imageSharingMode{}, presentMode{}, oldSwapchain{}; bool clipped{};
    u32 minImageCount{}, imageUsage{}; Extent imageExtent;
};
namespace vk {
struct Settings { bool enabled=true; } settings;
struct Status { bool ready=false, unsupported=false; u32 width=0, height=0; } status;
u32 reserved=1; int constructors=0, processes=0, emissions=0, generated=0, presented_count=0, resets=0;
u32 fail_present=umax;
void frame_generation_count_presented(u32 n) { presented_count+=n; }
u32 frame_generation_reserved_images() { return settings.enabled ? reserved : 0; }
Settings get_frame_generation_settings() { return settings; }
void set_frame_generation_status(Status s) { status=s; }
u64 frame_generation_acquire_timeout() { return 0; }
void frame_generation_count_generated(u32 n) { generated+=n; }
struct frame_generator {
    explicit frame_generator(int) { ++constructors; }
    bool is_usable() { return true; }
    void reset() { ++resets; }
    void set_guest_extent(u32, u32) {}
    bool prepare(u32, u32) { return true; }
    u32 plan(u32 cap) { return cap; }
    VkSemaphore next_acquire_semaphore() { return 1; }
    VkSemaphore present_semaphore(u32) { return 2; }
    void process(int, VkImage, VkImageLayout, u32, u32, u32) { ++processes; }
    void emit(int, u32, VkImage, VkImageLayout, u32, u32) { ++emissions; }
};
}
struct FakeSwapchain {
    bool m_transfer_source_enabled=false;
    u32 count=4, acquired=0;
    u32 get_swap_image_count() { return count; }
    VkImage get_image(u32) { return 1; }
    VkResult acquire_next_swapchain_image(VkSemaphore, u64 timeout, u32* index) { assert(timeout==0); *index=acquired++; return 0; }
    VkResult present(VkSemaphore, u32 index) { return index==vk::fail_present ? -1 : 0; }
'''
getter = function(core, 'bool supports_frame_generation() const')
support = r'''
};
struct VKGSRender {
    FakeSwapchain storage; FakeSwapchain* m_swapchain=&storage;
    u32 m_requested_swap_reserve=0, m_reserved_swap_images=0;
    Extent m_swapchain_dims; int device=0, command=0;
    int* m_device=&device; int* m_current_command_buffer=&command;
    std::unique_ptr<vk::frame_generator> m_frame_generator;
    std::vector<u32> m_generated_present_images;
    std::vector<VkSemaphore> m_generated_wait_semaphores, m_generated_signal_semaphores;
    bool swapchain_unavailable=false, surface_lost=false; u64 m_generated_present_failures=0;
    void present_generated_frames();
    u32 available_frame_contexts();
    void discard_generated_frames();
    void run_frame_generation(VkImage, VkImageLayout, VkImageLayout, u32, u32);
};
struct Result { u32 usage, count; bool capable; };
Result negotiate(Surface surface_descriptors, bool fail=false, bool previous=false) {
    bool m_transfer_source_enabled=previous;
'''
setup = r'''
    int dev=0, m_surface=0, m_surface_format=0, m_color_space=0, old_swapchain=0, m_vk_swapchain=0;
    int swapchain_present_mode=0; u32 m_width=1280, m_height=720;
    u32 usage=0, count=0;
    auto _vkCreateSwapchainKHR = [&](int, VkSwapchainCreateInfoKHR* info, void*, int*) {
        usage=info->imageUsage; count=info->minImageCount; return fail ? -1 : 0;
    };
'''
main = r'''
    return {usage, count, m_transfer_source_enabled};
}
int main() {
    Surface s;
    auto no=negotiate(s);
    assert(no.usage==18 && no.count==4 && !no.capable);
    s.supportedUsageFlags |= VK_IMAGE_USAGE_TRANSFER_SRC_BIT;
    auto yes=negotiate(s);
    assert(yes.usage==19 && yes.count==5 && yes.capable);
    s.maxImageCount=4;
    assert(negotiate(s).count==4);
    vk::settings.enabled=false;
    assert(negotiate(s).count==4);
    vk::settings.enabled=true;
    s.supportedUsageFlags=18;
    assert(!negotiate(s, false, true).capable); // recreation loses capability
    try { negotiate(s, true, true); assert(false); } catch (const std::runtime_error&) {}

    VKGSRender render;
    assert(render.available_frame_contexts()==4);
    assert(render.m_requested_swap_reserve==1 && render.m_reserved_swap_images==0);
    render.m_reserved_swap_images=1; // stale reserve must not bypass the dispatch guard
    render.run_frame_generation(1, 0, 0, 1280, 720);
    assert(vk::constructors==0 && vk::processes==0 && render.storage.acquired==0);
    assert(vk::status.unsupported && !vk::status.ready);
    render.storage.m_transfer_source_enabled=true;
    assert(render.available_frame_contexts()==3);
    render.run_frame_generation(1, 0, 0, 1280, 720);
    assert(vk::constructors==1 && vk::processes==1 && vk::emissions==1 && vk::generated==0);
    render.present_generated_frames();
    assert(vk::generated==1 && vk::presented_count==1);
    assert(render.m_generated_present_images.empty());
    render.m_generated_present_images={9,10};
    render.m_generated_signal_semaphores={1,2};
    vk::fail_present=9;
    render.present_generated_frames();
    assert(vk::generated==2 && vk::presented_count==2); // failed present not counted
    assert(render.swapchain_unavailable);
    render.storage.m_transfer_source_enabled=false;
    assert(render.available_frame_contexts()==4);
    render.run_frame_generation(1, 0, 0, 1280, 720);
    assert(vk::processes==1 && vk::resets==1 && vk::status.unsupported);
    assert(render.m_generated_present_images.empty());
    vk::settings.enabled=false;
    render.run_frame_generation(1, 0, 0, 1280, 720);
    assert(!vk::status.unsupported && !vk::status.ready);
    vk::settings.enabled=true;
    render.storage.m_transfer_source_enabled=true;
    render.storage.count=3;
    assert(render.available_frame_contexts()==3 && render.m_reserved_swap_images==0);
    render.run_frame_generation(1, 0, 0, 1280, 720);
    assert(vk::processes==1 && !vk::status.unsupported);
'''
feature_test = r'''
    struct Features { int shaderStorageImageExtendedFormats=0; } enabled_features;
    struct GPU { Features features; } gpu; auto* pgpu=&gpu;
    for (int supported : {0, 1}) {
        pgpu->features.shaderStorageImageExtendedFormats=supported;
'''
end = r'''
        assert(enabled_features.shaderStorageImageExtendedFormats==supported);
    }
    std::cout << "Vulkan capability, recreation, dispatch and optional-feature checks passed\n";
}
'''
mode_function = 'int choose_mode(Surface surface_descriptors) { std::vector<int> present_modes={1,2};\n'+mode_selection+'return swapchain_present_mode; }\n'
main = main.replace('    VKGSRender render;', '\n    Surface caps; caps.supportedUsageFlags |= VK_IMAGE_USAGE_TRANSFER_SRC_BIT;\n    assert(choose_mode(caps)==VK_PRESENT_MODE_FIFO_KHR);\n    vk::settings.enabled=false;\n    assert(choose_mode(caps)==VK_PRESENT_MODE_MAILBOX_KHR);\n    vk::settings.enabled=true; caps.supportedUsageFlags &= ~VK_IMAGE_USAGE_TRANSFER_SRC_BIT;\n    assert(choose_mode(caps)==VK_PRESENT_MODE_MAILBOX_KHR);\n    VKGSRender render;')
# mode_function must be defined after vk settings but before main's invocation.
source = prefix + getter + support
source = source[:source.index('struct Result {')] + mode_function + source[source.index('struct Result {'):]
source += reset + setup + selection + main
source += feature_test + feature + end
source += '\n' + function(present, 'u32 VKGSRender::available_frame_contexts()')
source += '\n' + function(present, 'void VKGSRender::discard_generated_frames()')
source += '\n' + function(present, 'void VKGSRender::run_frame_generation(')
source += '\n' + function(present, 'void VKGSRender::present_generated_frames()')
with tempfile.TemporaryDirectory() as temp:
    cpp, binary = Path(temp)/'test.cpp', Path(temp)/'test'
    cpp.write_text(source)
    subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++20', '-Wall', '-Wextra',
                    '-Werror', '-pedantic', str(cpp), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
