// Compile with: c++ -std=c++20 -pthread -O2 -Wall -Wextra -Werror
// android/tests/verify_ppu_compile_policy.cpp -o verify_ppu && ./verify_ppu
#include "../../rpcs3/Emu/Cell/PPUCompilePolicy.h"
#include <atomic>
#include <future>
#include <iostream>
#include <latch>
#include <stdexcept>
#include <thread>
#include <vector>

using namespace std::chrono_literals;
using namespace duke::ppu;

int main()
{
    // Actual production policy, not a second implementation of its formula.
    static_assert(worker_limit(4096 * mib, 8192 * mib, 8, 0) == 1);
    static_assert(worker_limit(4096 * mib, 8192 * mib, 8, 1) == 2);
    static_assert(worker_limit(5120 * mib, 8192 * mib, 8, 0) == 2);
    static_assert(worker_limit(5120 * mib, 8192 * mib, 8, 1) == 3);
    static_assert(worker_limit(5120 * mib, 8192 * mib, 8, 2) == 4);
    static_assert(worker_limit(8192 * mib, 16384 * mib, 8, 0) == 4);
    static_assert(worker_limit(8192 * mib, 16384 * mib, 8, 1) == 3);
    static_assert(worker_limit(8192 * mib, 16384 * mib, 8, 2) == 4);
    static_assert(worker_limit(1024 * mib, 8192 * mib, 8, 2) == 1);
    static_assert(worker_limit(2048 * mib, 8192 * mib, 8, 2) == 1);
    static_assert(worker_limit(0, 8192 * mib, 8, 2) == 2);
    static_assert(worker_limit(0, 8192 * mib, 8, 1) == 2);
    static_assert(worker_limit(0, 0, 8, 0) == 8);
    static_assert(worker_limit(0, 0, 8, 2) == 4);
    static_assert(worker_limit(0, 0, 8, 1) == 3);
    static_assert(worker_limit(5120 * mib, 8192 * mib, 8, 99) == 2);
    static_assert(worker_limit(5120 * mib, 8192 * mib, 0, 2) == 1);
    static_assert(worker_limit(5120 * mib, 8192 * mib, 2, 2) == 2);
    static_assert(worker_limit(UINT64_MAX, UINT64_MAX, UINT32_MAX, 2) == 4);
    for (unsigned profile = 0; profile < 3; ++profile)
        for (unsigned cores = 0; cores < 33; ++cores)
            for (std::uint64_t ram = 0; ram < 20000; ram += 97)
            {
                const auto limit = worker_limit(ram * mib, 16000 * mib, cores, profile);
                assert(limit >= 1 && limit <= std::max(1u, cores));
                assert(limit <= profile_cap(profile));
            }

    std::string cache = "/cache/game/ppu-object/";
    select_test_cache(cache, 0);
    assert(cache == "/cache/game/ppu-object/");
    select_test_cache(cache, 2);
    assert(cache == "/cache/game/ppu-object/duke-ppu-test-2/");
    std::string custom = "/custom/objects";
    select_test_cache(custom, 9);
    assert(custom == "/custom/objects/duke-ppu-test-9/");
    std::string invalid = "/normal";
    select_test_cache(invalid, 10);
    assert(invalid == "/normal");

    assert(!startup_preparation.load());
    try
    {
        startup_scope outer;
        assert(startup_preparation.load());
        { startup_scope inner; assert(startup_preparation.load()); }
        assert(startup_preparation.load());
        throw std::runtime_error("unwind");
    }
    catch (const std::runtime_error&) {}
    assert(!startup_preparation.load());

    // Clear the phase before releasing Android's emulator lock, not at the
    // end of subsequent progress-notification work. Destructor is idempotent.
    {
        startup_scope explicit_finish;
        assert(startup_preparation.load());
        explicit_finish.finish();
        assert(!startup_preparation.load());
        explicit_finish.finish();
        assert(!startup_preparation.load());
    }
    assert(!startup_preparation.load());

    // Many independent module queues share a single gate.
    admission_gate shared;
    std::atomic<unsigned> active = 0, completed = 0;
    std::vector<std::jthread> workers;
    for (unsigned i = 0; i < 12; ++i)
        workers.emplace_back([&]
        {
            for (unsigned job = 0; job < 30; ++job)
            {
                admission_gate::lease token(shared, [] { return 4u; }, [] { return false; });
                assert(token);
                const auto now = ++active;
                assert(now <= 4);
                std::this_thread::sleep_for(100us);
                --active;
                ++completed;
            }
        });
    workers.clear();
    assert(completed == 360 && active == 0 && shared.peak() <= 4);

    // Shrinking the budget preserves running work and blocks new admissions.
    admission_gate shrinking;
    std::atomic<unsigned> limit = 3;
    std::latch ready(3);
    std::promise<void> release[3];
    auto f0 = release[0].get_future(), f1 = release[1].get_future(), f2 = release[2].get_future();
    auto holder = [&](std::future<void>& future)
    {
        admission_gate::lease token(shrinking, [&] { return limit.load(); }, [] { return false; });
        assert(token);
        ready.count_down();
        future.wait();
    };
    std::jthread first(holder, std::ref(f0)), second(holder, std::ref(f1)), third(holder, std::ref(f2));
    ready.wait();
    limit = 1;
    std::promise<void> admitted;
    auto next = admitted.get_future();
    std::jthread waiting([&]
    {
        admission_gate::lease token(shrinking, [&] { return limit.load(); }, [] { return false; });
        assert(token);
        admitted.set_value();
    });
    assert(next.wait_for(20ms) == std::future_status::timeout);
    release[0].set_value(); release[1].set_value();
    first.join(); second.join();
    assert(next.wait_for(20ms) == std::future_status::timeout);
    release[2].set_value(); third.join();
    assert(next.wait_for(1s) == std::future_status::ready);
    waiting.join();
    assert(shrinking.peak() == 3);

    // Cancellation while waiting cannot acquire or leak a permit.
    admission_gate cancelling;
    std::atomic<bool> cancel = false;
    std::promise<bool> result;
    auto cancelled = result.get_future();
    {
        admission_gate::lease occupied(cancelling, [] { return 1u; }, [] { return false; });
        std::jthread waiter([&]
        {
            admission_gate::lease token(cancelling, [] { return 1u; }, [&] { return cancel.load(); });
            result.set_value(static_cast<bool>(token));
        });
        assert(cancelled.wait_for(20ms) == std::future_status::timeout);
        cancel = true;
        assert(cancelled.wait_for(1s) == std::future_status::ready && !cancelled.get());
    }
    admission_gate::lease recovered(cancelling, [] { return 1u; }, [] { return false; });
    assert(recovered);

    // Exception unwinding returns a permit.
    admission_gate unwinding;
    try
    {
        admission_gate::lease token(unwinding, [] { return 1u; }, [] { return false; });
        throw std::runtime_error("JIT constructor failure");
    }
    catch (const std::runtime_error&) {}
    admission_gate::lease retry(unwinding, [] { return 1u; }, [] { return false; });
    assert(retry);
    std::cout << "PASS: production PPU profiles, cache isolation, startup scope, shared admission, shrinking RAM, cancellation and RAII.\n";
}
