#!/usr/bin/env python3
"""Compile the production directory enqueue and worker-limit decisions.

Exercises overlapping game/update roots and Android's preparation queue without
LLVM, then verifies requested workers stay within existing CPU/RAM permits.
This does not measure first-boot compilation time or run an Android APK.
"""
from pathlib import Path
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
source = (root / 'rpcs3/Emu/Cell/PPUThread.cpp').read_text()
native = (root / 'android/app/src/main/cpp/native-lib.cpp').read_text()

def brace_block(text, signature):
    start = text.index(signature)
    opening = text.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]

start = source.index("\t// Make sure we only have one '/' at the end")
normalize = source[start:source.index('\tconst std::string firmware_sprx_path', start)]
directory = brace_block(source[source.index('extern void ppu_precompile'):], 'if (entry.is_directory)')
start = native.index('    std::vector<std::string> dir_queue;', native.index('auto rootPath ='))
native_roots = native[start:native.index('    std::vector<ppu_module<lv2_obj> *> mod_list;', start)]
start = source.index('\t\tconst u32 worker_limit =')
workers = source[start:source.index('\n\t\tppu_log.notice("PPU compile workers:', start)]

prefix = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <map>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>
using u32=std::uint32_t; using u64=std::uint64_t;
using usz=std::size_t; using s16=std::int16_t;
template<class T> u32 size32(const T& value) { return static_cast<u32>(value.size()); }
struct Entry { std::string name; bool is_directory; };
using Tree=std::map<std::string,std::vector<Entry>>;
struct Result { std::vector<std::string> dirs, files; u32 roots; u64 avoided; };
Result scan(const Tree& tree, std::vector<std::string> dir_queue) {
'''

walk = r'''
    std::vector<std::string> files;
    for(usz i=0;i<dir_queue.size();++i) {
        for(const auto& entry : tree.at(dir_queue[i])) {
'''

middle = r'''
            files.push_back(dir_queue[i]+entry.name);
        }
    }
    return {dir_queue,files,scan_roots,duplicate_directories};
}
std::vector<std::string> preparation_roots(const std::filesystem::path& rootPath) {
'''

worker_fixture = r'''
    return dir_queue;
}
struct jit_core_allocator { s16 thread_count=1; } allocator;
struct Registry { template<class T> T& get() { return allocator; } } registry;
auto* g_fxo=&registry;
u32 cpu_limit=8;
namespace rpcs3::utils { u32 get_max_threads() { return cpu_limit; } }
u32 worker_count(u32 jobs, u32 requested, s16 permits) {
    std::vector<int> workload(jobs);
    cpu_limit=requested;
    allocator.thread_count=permits;
'''

tests = r'''
    return thread_count+1; // Includes the current thread, as production does.
}
int main() {
    Tree tree{
        {"/game/", {{".",true},{"..",true},{"USRDIR",true},{"PARAM.SFO",false}}},
        {"/game/USRDIR/", {{"EBOOT.BIN",false},{"levels",true}}},
        {"/game/USRDIR/levels/", {{"chapter.sprx",false},{"overlays",true}}},
        {"/game/USRDIR/levels/overlays/", {{"part.self",false}}},
        {"/update/", {{"patch.sprx",false},{"USRDIR",true}}},
        {"/update/USRDIR/", {{"extra.sprx",false}}}
    };
    auto result=scan(tree,{"/game/", "/game/USRDIR/", "/game/USRDIR/levels/",
                         "/game/USRDIR/levels/overlays/", "/update/", "/update/USRDIR/"});
    assert(result.dirs.size()==6 && result.files.size()==6);
    assert(result.avoided==4);
    std::unordered_set<std::string> dirs(result.dirs.begin(),result.dirs.end());
    std::unordered_set<std::string> files(result.files.begin(),result.files.end());
    assert(dirs.size()==result.dirs.size() && files.size()==result.files.size());
    assert(files.contains("/game/USRDIR/levels/overlays/part.self"));
    assert(files.contains("/update/USRDIR/extra.sprx"));

    // Supplying only parents discovers exactly the same files once.
    auto parents=scan(tree,{"/game/", "/update/"});
    assert(std::unordered_set<std::string>(parents.files.begin(),parents.files.end())==files);
    assert(parents.dirs.size()==6 && parents.avoided==0);

    // Trailing separators and repeated roots must not duplicate descendants.
    auto repeated=scan(tree,{"", "/game///", "/game/", "/game/USRDIR/",
                            "/game/USRDIR/", "/update\\"});
    assert(repeated.dirs.size()==6 && repeated.files.size()==6);
    assert(repeated.roots==3);
    assert(scan(tree,{}).dirs.empty());
    auto only_update=scan(tree,{"/update/USRDIR/"});
    assert(only_update.files==std::vector<std::string>{"/update/USRDIR/extra.sprx"});

    // A filesystem root remains valid; dot entries are not enqueued.
    Tree rooted{{"/", {{".",true},{"..",true},{"file.sprx",false}}}};
    auto root_result=scan(rooted,{"/", "///"});
    assert(root_result.dirs==std::vector<std::string>{"/"});
    assert(root_result.files==std::vector<std::string>{"/file.sprx"});

    // Execute Android's actual root preparation; ppu_precompile owns recursion.
    assert(preparation_roots("/game")==std::vector<std::string>{"/game"});

    // A 1-permit Android allocator previously requested seven extra workers
    // for 44 jobs. Now only the current thread is needed. No permit is raised.
    assert(worker_count(44,8,1)==1);
    assert(worker_count(44,8,2)==2);
    assert(worker_count(44,2,4)==2); // Explicit user maximum still respected.
    assert(worker_count(1,8,4)==1);
    assert(worker_count(3,8,4)==3);
    assert(worker_count(44,8,0)==1);
    assert(worker_count(44,0,8)==1); // Defensive zero CPU report.
    std::cout << "PASS: production traversal considers each directory/file once, "
        "retains nested/update roots, avoids redundant Android enumeration, "
        "and respects existing compile permits.\n";
}
'''

with tempfile.TemporaryDirectory() as directory_path:
    path = Path(directory_path)
    cpp = path / 'ppu_precompile.cpp'
    cpp.write_text(prefix + normalize + walk + directory + middle + native_roots +
                   worker_fixture + workers + tests)
    subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++20', '-Wall', '-Wextra',
                    '-Werror', '-O2', str(cpp), '-o', str(path / 'verify')], check=True)
    subprocess.run([str(path / 'verify')], check=True)
