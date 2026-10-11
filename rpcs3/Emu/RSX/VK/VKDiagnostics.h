#pragma once

#include <cstdint>
#include <mutex>
#include <string>
#include <utility>

namespace vk
{
	// Copies only: Android readers must not retain a pointer to a Vulkan device
	// while another thread tears it down. Independent of frame generation.
	struct renderer_diagnostics
	{
		bool available = false;
		std::string gpu_name;
		std::string driver_name;
		std::string driver_version;
		std::string vulkan_version;
		std::uint32_t driver_vendor_id = 0;
		std::uint32_t guest_width = 0, guest_height = 0, guest_pitch_bytes = 0;
		std::uint32_t source_width = 0, source_height = 0;
		std::uint32_t output_width = 0, output_height = 0;
		bool source_found = false;
	};

	class renderer_diagnostics_cache
	{
		std::mutex m_mutex;
		renderer_diagnostics m_snapshot;

	public:
		void set_device(renderer_diagnostics identity)
		{
			std::lock_guard lock(m_mutex);
			m_snapshot = std::move(identity);
		}

		void set_present(std::uint32_t guest_width, std::uint32_t guest_height,
			std::uint32_t pitch_bytes, std::uint32_t source_width, std::uint32_t source_height,
			std::uint32_t output_width, std::uint32_t output_height, bool source_found)
		{
			std::lock_guard lock(m_mutex);
			if (!m_snapshot.available) return;
			m_snapshot.guest_width = guest_width;
			m_snapshot.guest_height = guest_height;
			m_snapshot.guest_pitch_bytes = pitch_bytes;
			m_snapshot.source_width = source_width;
			m_snapshot.source_height = source_height;
			m_snapshot.output_width = output_width;
			m_snapshot.output_height = output_height;
			m_snapshot.source_found = source_found;
		}

		void reset()
		{
			std::lock_guard lock(m_mutex);
			m_snapshot = {};
		}

		renderer_diagnostics get()
		{
			std::lock_guard lock(m_mutex);
			return m_snapshot;
		}
	};

	inline renderer_diagnostics_cache g_renderer_diagnostics;
}
