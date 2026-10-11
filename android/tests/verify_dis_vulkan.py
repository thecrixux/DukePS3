#!/usr/bin/env python3
"""Compile and run the production DIS engine against a real Vulkan device.

Requires C++20, Vulkan headers/loader, glslangValidator, spirv-val and the
Khronos validation layer. Software Vulkan (lavapipe) is suitable. Only RPCS3's
device/log/compiler interfaces are adapted; DIS resources and dispatches are
the production code. Does not validate Android presentation or Adreno speed.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
DIS = ROOT/'rpcs3/Emu/RSX/VK/dis'
INTERFACE = r'''
#pragma once
#include <vulkan/vulkan.h>
#include <array>
#include <cstdint>
#include <cstddef>
#include <cstdio>
#include <vector>
#include <string>
#include <fstream>
#include <stdexcept>
#include <cstdlib>
#include <algorithm>
using u8=uint8_t; using u32=uint32_t; using s32=int32_t; using u64=uint64_t; using usz=size_t;
#define VK_GET_SYMBOL(func) func
struct Log {
    template<class... A> void notice(const char* text, A&&...) { std::puts(text); }
    template<class... A> void error(const char* text, A&&...) { std::fprintf(stderr,"%s\n",text); }
    template<class... A> void warning(const char* text, A&&...) { std::fprintf(stderr,"%s\n",text); }
};
inline Log rsx_log;
inline bool force_unsupported=false;
inline void test_features(VkPhysicalDevice gpu, VkPhysicalDeviceFeatures* features) {
    vkGetPhysicalDeviceFeatures(gpu,features);
    if(force_unsupported) features->shaderStorageImageExtendedFormats=VK_FALSE;
}
inline void test_formats(VkPhysicalDevice gpu, VkFormat format, VkFormatProperties* props) {
    vkGetPhysicalDeviceFormatProperties(gpu,format,props);
    if(std::getenv("DIS_FORCE_FALLBACK")) {
        if(format==VK_FORMAT_R16_SFLOAT) props->optimalTilingFeatures=0;
        if(format==VK_FORMAT_R32G32_SFLOAT)
            props->optimalTilingFeatures &= ~VK_FORMAT_FEATURE_SAMPLED_IMAGE_FILTER_LINEAR_BIT;
    }
}
namespace vk {
struct physical_device {
    VkPhysicalDevice handle{}; VkPhysicalDeviceFeatures features{};
    operator VkPhysicalDevice() const { return handle; }
};
struct render_device {
    VkDevice handle{}; physical_device physical;
    operator VkDevice() const { return handle; }
    const physical_device& gpu() const { return physical; }
};
}
namespace glsl { enum program_domain : unsigned char { glsl_compute_program };
enum glsl_rules : unsigned char { glsl_rules_vulkan }; }
namespace spirv {
inline bool compile_glsl_to_spv(std::vector<u32>& words, std::string& source,
                               glsl::program_domain, glsl::glsl_rules) {
    static unsigned counter=0;
    const std::string stem="shader_"+std::to_string(counter++);
    std::ofstream(stem+".comp") << source;
    std::string command=std::string(std::getenv("GLSLANG_VALIDATOR"))+
        " -V --target-env vulkan1.2 -S comp -o "+stem+".spv "+stem+".comp > shader.log 2>&1";
    if(std::system(command.c_str())!=0) {
        std::fprintf(stderr,"GLSL compilation failed: %s\n",stem.c_str());
        return false;
    }
    command=std::string(std::getenv("SPIRV_VAL"))+" --target-env vulkan1.2 "+stem+".spv";
    if(std::system(command.c_str())!=0) return false;
    std::ifstream input(stem+".spv",std::ios::binary|std::ios::ate);
    const auto bytes=input.tellg();
    if(bytes<=0 || bytes%4!=0) return false;
    words.resize(static_cast<size_t>(bytes)/4);
    input.seekg(0); input.read(reinterpret_cast<char*>(words.data()),bytes);
    return bool(input);
}
}
'''
MAIN = r'''
#include "interface.hpp"
#include "dis_flow.h"
#include "dis_shaders.hpp"
#include <cassert>
#include <cstring>
#include <iostream>
#include <cmath>

static unsigned errors=0, sync_errors=0;
VKAPI_ATTR VkBool32 VKAPI_CALL debug(VkDebugUtilsMessageSeverityFlagBitsEXT severity,
    VkDebugUtilsMessageTypeFlagsEXT, const VkDebugUtilsMessengerCallbackDataEXT* data, void*) {
    if(severity & VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT) {
        ++errors; std::fprintf(stderr,"VALIDATION: %s\n",data->pMessage);
        if(std::strstr(data->pMessage,"SYNC-")) ++sync_errors;
    }
    return VK_FALSE;
}
void check(VkResult value) { if(value!=VK_SUCCESS) throw std::runtime_error("Vulkan call failed"); }
void barrier(VkCommandBuffer cmd, VkImage image, VkImageLayout oldLayout, VkImageLayout next,
             VkAccessFlags src, VkAccessFlags dst) {
    VkImageMemoryBarrier b{}; b.sType=VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
    b.srcAccessMask=src; b.dstAccessMask=dst; b.oldLayout=oldLayout; b.newLayout=next;
    b.srcQueueFamilyIndex=b.dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED; b.image=image;
    b.subresourceRange={VK_IMAGE_ASPECT_COLOR_BIT,0,1,0,1};
    vkCmdPipelineBarrier(cmd,VK_PIPELINE_STAGE_ALL_COMMANDS_BIT,VK_PIPELINE_STAGE_ALL_COMMANDS_BIT,
                         0,0,nullptr,0,nullptr,1,&b);
}
int main() {
    std::cout << std::unitbuf;
    VkApplicationInfo app{}; app.sType=VK_STRUCTURE_TYPE_APPLICATION_INFO; app.apiVersion=VK_API_VERSION_1_2;
    const char* layer="VK_LAYER_KHRONOS_validation";
    const char* extensions[]={VK_EXT_DEBUG_UTILS_EXTENSION_NAME};
    VkValidationFeatureEnableEXT sync=VK_VALIDATION_FEATURE_ENABLE_SYNCHRONIZATION_VALIDATION_EXT;
    VkValidationFeaturesEXT validation{}; validation.sType=VK_STRUCTURE_TYPE_VALIDATION_FEATURES_EXT;
    validation.enabledValidationFeatureCount=1; validation.pEnabledValidationFeatures=&sync;
    VkInstanceCreateInfo ici{}; ici.sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
    ici.pApplicationInfo=&app; ici.enabledLayerCount=1; ici.ppEnabledLayerNames=&layer;
    ici.enabledExtensionCount=1; ici.ppEnabledExtensionNames=extensions; ici.pNext=&validation;
    VkInstance instance{}; check(vkCreateInstance(&ici,nullptr,&instance));
    VkDebugUtilsMessengerCreateInfoEXT dbg{}; dbg.sType=VK_STRUCTURE_TYPE_DEBUG_UTILS_MESSENGER_CREATE_INFO_EXT;
    dbg.messageSeverity=VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT;
    dbg.messageType=VK_DEBUG_UTILS_MESSAGE_TYPE_VALIDATION_BIT_EXT|VK_DEBUG_UTILS_MESSAGE_TYPE_PERFORMANCE_BIT_EXT;
    dbg.pfnUserCallback=debug;
    VkDebugUtilsMessengerEXT messenger{};
    auto createDebug=reinterpret_cast<PFN_vkCreateDebugUtilsMessengerEXT>(vkGetInstanceProcAddr(instance,"vkCreateDebugUtilsMessengerEXT"));
    check(createDebug(instance,&dbg,nullptr,&messenger));
    u32 count=0; check(vkEnumeratePhysicalDevices(instance,&count,nullptr)); assert(count>0);
    std::vector<VkPhysicalDevice> gpus(count); check(vkEnumeratePhysicalDevices(instance,&count,gpus.data()));
    vk::render_device dev; dev.physical.handle=gpus[0];
    vkGetPhysicalDeviceFeatures(gpus[0],&dev.physical.features);
    VkPhysicalDeviceProperties props{}; vkGetPhysicalDeviceProperties(gpus[0],&props);
    std::cout << "Vulkan device: " << props.deviceName << "\n";
    count=0; vkGetPhysicalDeviceQueueFamilyProperties(gpus[0],&count,nullptr);
    std::vector<VkQueueFamilyProperties> queues(count); vkGetPhysicalDeviceQueueFamilyProperties(gpus[0],&count,queues.data());
    u32 family=0; while(!(queues[family].queueFlags&VK_QUEUE_COMPUTE_BIT)) ++family;
    float priority=1;
    VkDeviceQueueCreateInfo qci{}; qci.sType=VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
    qci.queueFamilyIndex=family; qci.queueCount=1; qci.pQueuePriorities=&priority;
    VkPhysicalDeviceFeatures features{};
    features.shaderStorageImageExtendedFormats=dev.physical.features.shaderStorageImageExtendedFormats;
    VkDeviceCreateInfo dci{}; dci.sType=VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
    dci.queueCreateInfoCount=1; dci.pQueueCreateInfos=&qci; dci.pEnabledFeatures=&features;
    check(vkCreateDevice(gpus[0],&dci,nullptr,&dev.handle));
    VkQueue queue{}; vkGetDeviceQueue(dev, family,0,&queue);
    VkCommandPoolCreateInfo poolci{}; poolci.sType=VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
    poolci.queueFamilyIndex=family; poolci.flags=VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
    VkCommandPool pool{}; check(vkCreateCommandPool(dev,&poolci,nullptr,&pool));
    VkCommandBufferAllocateInfo cai{}; cai.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
    cai.commandPool=pool; cai.level=VK_COMMAND_BUFFER_LEVEL_PRIMARY; cai.commandBufferCount=1;
    VkCommandBuffer cmd{}; check(vkAllocateCommandBuffers(dev,&cai,&cmd));
    dis::Device allocator(dev,dev.gpu());
    auto submit=[&] {
        check(vkEndCommandBuffer(cmd));
        VkSubmitInfo si{}; si.sType=VK_STRUCTURE_TYPE_SUBMIT_INFO;
        si.commandBufferCount=1; si.pCommandBuffers=&cmd;
        check(vkQueueSubmit(queue,1,&si,VK_NULL_HANDLE)); check(vkQueueWaitIdle(queue));
    };
    auto begin=[&] {
        check(vkResetCommandBuffer(cmd,0));
        VkCommandBufferBeginInfo bi{}; bi.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
        check(vkBeginCommandBuffer(cmd,&bi));
    };
    {
        force_unsupported=true;
        dis::DisFlow rejected(dev); assert(!rejected.Valid());
        force_unsupported=false;
        dis::DisFlow flow(dev); assert(flow.Valid());
        assert(flow.Configure(64)); assert(flow.Prepare(128,72,VK_FORMAT_R8G8B8A8_UNORM));
        assert(flow.FlowExtent().height==64);
        assert(!flow.NeedsRebuild(128,72,VK_FORMAT_R8G8B8A8_UNORM));
        assert(!flow.Prepare(0,72,VK_FORMAT_R8G8B8A8_UNORM));
        dis::DisImage source(allocator,128,72,VK_FORMAT_R8G8B8A8_UNORM,1,
            VK_IMAGE_USAGE_TRANSFER_DST_BIT|VK_IMAGE_USAGE_TRANSFER_SRC_BIT);
        std::array<dis::DisImage,3> targets;
        for(auto& image:targets) image=dis::DisImage(allocator,128,72,VK_FORMAT_R8G8B8A8_UNORM,1,
            VK_IMAGE_USAGE_TRANSFER_DST_BIT|VK_IMAGE_USAGE_TRANSFER_SRC_BIT);
        auto& target=targets[0];
        assert(source.Valid() && target.Valid());
        VkBufferCreateInfo bci{}; bci.sType=VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
        bci.size=128*72*4; bci.usage=VK_BUFFER_USAGE_TRANSFER_DST_BIT;
        VkBuffer buffer{}; check(vkCreateBuffer(dev,&bci,nullptr,&buffer));
        VkMemoryRequirements req{}; vkGetBufferMemoryRequirements(dev,buffer,&req);
        VkMemoryAllocateInfo mai{}; mai.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
        mai.allocationSize=req.size; mai.memoryTypeIndex=allocator.FindMemoryType(req.memoryTypeBits,
            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT|VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
        VkDeviceMemory memory{}; check(vkAllocateMemory(dev,&mai,nullptr,&memory));
        check(vkBindBufferMemory(dev,buffer,memory,0));
        VkImageSubresourceRange range={VK_IMAGE_ASPECT_COLOR_BIT,0,1,0,1};
        for(unsigned frame=0;frame<10;++frame) {
            begin();
            barrier(cmd,source.Handle(),frame ? VK_IMAGE_LAYOUT_GENERAL : VK_IMAGE_LAYOUT_UNDEFINED,
                    VK_IMAGE_LAYOUT_GENERAL,VK_ACCESS_TRANSFER_READ_BIT,VK_ACCESS_TRANSFER_WRITE_BIT);
            VkClearColorValue color{};
            color.float32[0]=color.float32[2]=0.40f;
            color.float32[frame%2 ? 2 : 0]=0.44f; color.float32[3]=1;
            vkCmdClearColorImage(cmd,source.Handle(),VK_IMAGE_LAYOUT_GENERAL,&color,1,&range);
            barrier(cmd,source.Handle(),VK_IMAGE_LAYOUT_GENERAL,VK_IMAGE_LAYOUT_GENERAL,
                    VK_ACCESS_TRANSFER_WRITE_BIT,VK_ACCESS_TRANSFER_READ_BIT);
            const unsigned generations=frame<2 ? 0 : 1+(frame%3);
            flow.Process(cmd,source.Handle(),128,72,generations);
            if(frame>=2) {
                for(unsigned g=0;g<generations;++g) flow.GenerateInto(cmd,g,targets[g].Handle(),128,72);
                auto& generatedTarget=targets[generations-1];
                barrier(cmd,generatedTarget.Handle(),VK_IMAGE_LAYOUT_GENERAL,VK_IMAGE_LAYOUT_GENERAL,
                        VK_ACCESS_TRANSFER_WRITE_BIT,VK_ACCESS_TRANSFER_READ_BIT);
                VkBufferImageCopy copy{}; copy.imageSubresource={VK_IMAGE_ASPECT_COLOR_BIT,0,0,1};
                copy.imageExtent={128,72,1};
                vkCmdCopyImageToBuffer(cmd,generatedTarget.Handle(),VK_IMAGE_LAYOUT_GENERAL,buffer,1,&copy);
                VkMemoryBarrier host{}; host.sType=VK_STRUCTURE_TYPE_MEMORY_BARRIER;
                host.srcAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT; host.dstAccessMask=VK_ACCESS_HOST_READ_BIT;
                vkCmdPipelineBarrier(cmd,VK_PIPELINE_STAGE_TRANSFER_BIT,VK_PIPELINE_STAGE_HOST_BIT,
                                     0,1,&host,0,nullptr,0,nullptr);
            }
            submit();
            if(frame>=2) {
                void* pixels{}; check(vkMapMemory(dev,memory,0,VK_WHOLE_SIZE,0,&pixels));
                auto bytes=static_cast<unsigned char*>(pixels);
                for(unsigned i=0;i<128*72;++i) {
                    const float t=float(generations)/float(generations+1);
                    const float red=255*(frame%2 ? .44f*(1-t)+.4f*t : .4f*(1-t)+.44f*t);
                    const float blue=255*(frame%2 ? .4f*(1-t)+.44f*t : .44f*(1-t)+.4f*t);
                    assert(std::abs(float(bytes[4*i])-red)<3);
                    assert(bytes[4*i+1]<=2);
                    assert(std::abs(float(bytes[4*i+2])-blue)<3);
                    assert(bytes[4*i+3]>=253);
                }
                vkUnmapMemory(dev,memory);
            }
        }

        VkBuffer upload{}; bci.usage=VK_BUFFER_USAGE_TRANSFER_SRC_BIT;
        check(vkCreateBuffer(dev,&bci,nullptr,&upload));
        vkGetBufferMemoryRequirements(dev,upload,&req);
        mai.allocationSize=req.size;
        mai.memoryTypeIndex=allocator.FindMemoryType(req.memoryTypeBits,
            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT|VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
        VkDeviceMemory uploadMemory{}; check(vkAllocateMemory(dev,&mai,nullptr,&uploadMemory));
        check(vkBindBufferMemory(dev,upload,uploadMemory,0));
        void* mapped{}; check(vkMapMemory(dev,uploadMemory,0,VK_WHOLE_SIZE,0,&mapped));
        std::vector<unsigned char> pattern(128*72*4);
        for(unsigned y=0;y<72;++y) for(unsigned x=0;x<128;++x) {
            const unsigned k=4*(y*128+x);
            pattern[k]=static_cast<unsigned char>((x*13+y*7)%256);
            pattern[k+1]=static_cast<unsigned char>((x/4+y/4)%2 ? 190 : 40);
            pattern[k+2]=static_cast<unsigned char>((x*5+y*17)%256);
            pattern[k+3]=255;
        }
        std::memcpy(mapped,pattern.data(),pattern.size()); vkUnmapMemory(dev,uploadMemory);
        for(unsigned frame=0;frame<8;++frame) {
            begin();
            barrier(cmd,source.Handle(),VK_IMAGE_LAYOUT_GENERAL,VK_IMAGE_LAYOUT_GENERAL,
                    VK_ACCESS_TRANSFER_READ_BIT,VK_ACCESS_TRANSFER_WRITE_BIT);
            VkBufferImageCopy copy{}; copy.imageSubresource={VK_IMAGE_ASPECT_COLOR_BIT,0,0,1};
            copy.imageExtent={128,72,1};
            vkCmdCopyBufferToImage(cmd,upload,source.Handle(),VK_IMAGE_LAYOUT_GENERAL,1,&copy);
            barrier(cmd,source.Handle(),VK_IMAGE_LAYOUT_GENERAL,VK_IMAGE_LAYOUT_GENERAL,
                    VK_ACCESS_TRANSFER_WRITE_BIT,VK_ACCESS_TRANSFER_READ_BIT);
            flow.Process(cmd,source.Handle(),128,72,frame<2 ? 0 : 1);
            if(frame>=2) {
                flow.GenerateInto(cmd,0,target.Handle(),128,72);
                barrier(cmd,target.Handle(),VK_IMAGE_LAYOUT_GENERAL,VK_IMAGE_LAYOUT_GENERAL,
                        VK_ACCESS_TRANSFER_WRITE_BIT,VK_ACCESS_TRANSFER_READ_BIT);
                vkCmdCopyImageToBuffer(cmd,target.Handle(),VK_IMAGE_LAYOUT_GENERAL,buffer,1,&copy);
                VkMemoryBarrier host{}; host.sType=VK_STRUCTURE_TYPE_MEMORY_BARRIER;
                host.srcAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT; host.dstAccessMask=VK_ACCESS_HOST_READ_BIT;
                vkCmdPipelineBarrier(cmd,VK_PIPELINE_STAGE_TRANSFER_BIT,VK_PIPELINE_STAGE_HOST_BIT,
                                     0,1,&host,0,nullptr,0,nullptr);
            }
            submit();
            if(frame>=2) {
                check(vkMapMemory(dev,memory,0,VK_WHOLE_SIZE,0,&mapped));
                const auto pixels=static_cast<unsigned char*>(mapped);
                for(unsigned i=0;i<pattern.size();++i)
                    assert(std::abs(int(pixels[i])-int(pattern[i]))<=2);
                vkUnmapMemory(dev,memory);
            }
        }
        vkDestroyBuffer(dev,upload,nullptr); vkFreeMemory(dev,uploadMemory,nullptr);

        vkDestroyBuffer(dev,buffer,nullptr); vkFreeMemory(dev,memory,nullptr);
        assert(flow.Configure(180)); assert(flow.NeedsRebuild(128,72,VK_FORMAT_R8G8B8A8_UNORM));
        assert(flow.Prepare(128,72,VK_FORMAT_R8G8B8A8_UNORM));
        assert(flow.FlowExtent().width==128 && flow.FlowExtent().height==72);
        assert(flow.Prepare(320,180,VK_FORMAT_R8G8B8A8_UNORM));
        flow.Reset();
        assert(flow.Prepare(320,180,VK_FORMAT_R8G8B8A8_UNORM));
        for(int id=0;id<14;++id) assert(dis::GetDisShader(static_cast<dis::DisShader>(id)));
        std::cout << "14 shaders compiled and SPIR-V validated; 2x/3x/4x pixels, static texture, slot wrap and rebuilds passed\n";
    }
    check(vkDeviceWaitIdle(dev));
    vkDestroyCommandPool(dev,pool,nullptr); vkDestroyDevice(dev,nullptr);
    auto destroyDebug=reinterpret_cast<PFN_vkDestroyDebugUtilsMessengerEXT>(vkGetInstanceProcAddr(instance,"vkDestroyDebugUtilsMessengerEXT"));
    destroyDebug(instance,messenger,nullptr); vkDestroyInstance(instance,nullptr);
    std::cout << "Validation errors: " << errors << "; synchronization errors: " << sync_errors << "\n";
    assert(errors==0);
}
'''

validator = os.environ.get('GLSLANG_VALIDATOR') or shutil.which('glslangValidator')
spirv_val = os.environ.get('SPIRV_VAL') or shutil.which('spirv-val')
if not validator or not spirv_val:
    raise SystemExit('Set GLSLANG_VALIDATOR and SPIRV_VAL, or install glslang-tools and spirv-tools.')
with tempfile.TemporaryDirectory() as directory:
    temp=Path(directory)
    (temp/'interface.hpp').write_text(INTERFACE)
    for name in ('dis_flow.h','dis_shaders.hpp'):
        source=(DIS/name).read_text().replace('#include "../VulkanAPI.h"','#include "interface.hpp"')
        source=source.replace('#include "util/types.hpp"','#include "interface.hpp"')
        (temp/name).write_text(source)
    for name in ('dis_flow.cpp','dis_shaders.cpp'):
        source=(DIS/name).read_text()
        source=source.replace('#include "stdafx.h"','#include "interface.hpp"')
        for include in ('../vkutils/device.h','Emu/RSX/Program/GLSLTypes.h','Emu/RSX/Program/SPIRVCommon.h'):
            source=source.replace(f'#include "{include}"','')
        source=source.replace('VK_GET_SYMBOL(vkGetPhysicalDeviceFeatures)','test_features')
        source=source.replace('VK_GET_SYMBOL(vkGetPhysicalDeviceFormatProperties)','test_formats')
        (temp/name).write_text(source)
    (temp/'main.cpp').write_text(MAIN)
    command=[os.environ.get('CXX','c++'),'-std=c++20','-O1','-Wall','-Wextra','-Werror',
             '-Wno-missing-field-initializers','-pedantic']
    if os.environ.get('VULKAN_INCLUDE'): command+=['-I',os.environ['VULKAN_INCLUDE']]
    command += [str(temp/'dis_flow.cpp'),str(temp/'dis_shaders.cpp'),str(temp/'main.cpp')]
    command += [os.environ.get('VULKAN_LIBRARY','-lvulkan'),'-o',str(temp/'test')]
    subprocess.run(command,check=True)
    env=os.environ.copy(); env['GLSLANG_VALIDATOR']=validator; env['SPIRV_VAL']=spirv_val
    subprocess.run([str(temp/'test')],cwd=temp,env=env,check=True)
