#pragma once

#include <algorithm>
#include <cassert>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <mutex>
#include <string>

namespace duke::ppu
{
	// Scheduling only: these profiles do not change LLVM IR, ISA or codegen.
	inline constexpr std::uint64_t mib = 1024ull * 1024;
	inline constexpr std::uint64_t reserve_bytes = 2048 * mib;
	inline std::atomic<bool> startup_preparation{false};

	// The Android preparation queue temporarily uses Emu's Running state.
	// Its owner holds the emulator mutex, so no gameplay overlaps this scope.
	class startup_scope
	{
		const bool m_previous = startup_preparation.exchange(true);
		bool m_active = true;
	public:
		startup_scope() = default;
		startup_scope(const startup_scope&) = delete;
		startup_scope& operator=(const startup_scope&) = delete;
		void finish()
		{
			if (m_active)
			{
				startup_preparation.store(m_previous);
				m_active = false;
			}
		}
		~startup_scope() { finish(); }
	};

	inline void select_test_cache(std::string& path, unsigned slot)
	{
		if (slot == 0 || slot > 9) return;
		if (!path.ends_with('/')) path += '/';
		path += "duke-ppu-test-" + std::to_string(slot) + '/';
	}

	constexpr unsigned valid_profile(unsigned profile)
	{
		return profile <= 2 ? profile : 0;
	}

	constexpr unsigned profile_cap(unsigned profile)
	{
		return profile == 1 ? 3 : profile == 2 ? 4 : 0x7fff;
	}

	constexpr std::uint64_t worker_budget(unsigned profile)
	{
		return (profile == 1 ? 1024 : profile == 2 ? 768 : 1536) * mib;
	}

	constexpr unsigned worker_limit(std::uint64_t available, std::uint64_t total,
		unsigned cores, unsigned profile)
	{
		profile = valid_profile(profile);
		const unsigned by_cores = std::clamp(cores, 1u, 0x7fffu);
		std::uint64_t by_memory = by_cores;
		if (available)
		{
			const auto spare = available > reserve_bytes ? available - reserve_bytes : 0;
			by_memory = spare / worker_budget(profile);
		}
		else if (total)
		{
			// Unknown available RAM must not opt into a more optimistic estimate.
			by_memory = total / (3072 * mib);
		}
		return static_cast<unsigned>(std::max<std::uint64_t>(1,
			std::min<std::uint64_t>({by_memory, by_cores, profile_cap(profile)})));
	}

	// Shared by all PPU modules. The existing semaphore still caps workers;
	// this gate rechecks free RAM between jobs. Shrinking a limit never aborts
	// an in-flight JIT or destroys its context. It only delays new jobs.
	class admission_gate
	{
		std::mutex m_mutex;
		std::condition_variable m_cv;
		unsigned m_active = 0;
		unsigned m_peak = 0;

	public:
		class lease
		{
			admission_gate* m_owner = nullptr;

		public:
			template <typename Limit, typename Cancelled>
			lease(admission_gate& owner, Limit&& limit, Cancelled&& cancelled)
			{
				std::unique_lock lock(owner.m_mutex);
				while (!cancelled())
				{
					if (owner.m_active < std::max(1u, static_cast<unsigned>(limit())))
					{
						++owner.m_active;
						owner.m_peak = std::max(owner.m_peak, owner.m_active);
						m_owner = &owner;
						return;
					}
					owner.m_cv.wait_for(lock, std::chrono::milliseconds(100));
				}
			}

			lease(const lease&) = delete;
			lease& operator=(const lease&) = delete;

			~lease()
			{
				if (m_owner)
				{
					{
						std::lock_guard lock(m_owner->m_mutex);
						assert(m_owner->m_active != 0);
						--m_owner->m_active;
					}
					m_owner->m_cv.notify_all();
				}
			}

			explicit operator bool() const { return m_owner != nullptr; }
		};

		unsigned peak()
		{
			std::lock_guard lock(m_mutex);
			return m_peak;
		}
	};
}
