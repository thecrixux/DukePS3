#pragma once

#include <atomic>
#include <cstdint>
#include <mutex>
#include <string>

// Android's output backend is distinct from the emulated GPU. These counters
// describe the application's supply to Cubeb, not hardware/AAudio xrun counts.
namespace android_audio
{
static_assert(std::atomic<std::uint64_t>::is_always_lock_free, "Audio diagnostics require lock-free counters");
struct snapshot
{
	std::string preference = "auto";
	std::string backend;
	bool stream_open = false;
	bool playing = false;
	std::uint64_t stream_generation = 0;
	std::uint32_t rate = 0, channels = 0, bytes_per_sample = 0;
	std::uint32_t requested_latency_frames = 0;
	std::uint64_t delivered_callbacks = 0, requested_frames = 0;
	std::uint64_t short_read_callbacks = 0, missing_frames = 0;
	std::uint64_t mutex_timeout_callbacks = 0, reset_silence_callbacks = 0;
	std::uint64_t missing_callback_silence_callbacks = 0;
};

class diagnostics
{
	mutable std::mutex m_mutex;
	snapshot m_stream;
	std::atomic<bool> m_playing{false};
	std::atomic<std::uint64_t> m_delivered{0}, m_requested{0};
	std::atomic<std::uint64_t> m_short_reads{0}, m_missing{0};
	std::atomic<std::uint64_t> m_mutex_timeouts{0}, m_reset_silence{0}, m_no_callback{0};

public:
	void set_backend(const std::string& preference, const char* backend)
	{
		std::lock_guard lock(m_mutex);
		m_stream.preference = preference;
		m_stream.backend = backend ? backend : "";
	}

	// Called only after the old stream has been destroyed, before playback.
	void opened(std::uint32_t rate, std::uint32_t channels,
		std::uint32_t bytes_per_sample, std::uint32_t requested_latency_frames)
	{
		std::lock_guard lock(m_mutex);
		m_playing.store(false, std::memory_order_relaxed);
		m_delivered = 0; m_requested = 0; m_short_reads = 0; m_missing = 0;
		m_mutex_timeouts = 0; m_reset_silence = 0; m_no_callback = 0;
		m_stream.stream_open = true;
		++m_stream.stream_generation;
		m_stream.rate = rate;
		m_stream.channels = channels;
		m_stream.bytes_per_sample = bytes_per_sample;
		m_stream.requested_latency_frames = requested_latency_frames;
	}

	void set_playing(bool playing) { m_playing.store(playing, std::memory_order_relaxed); }

	void closed()
	{
		set_playing(false);
		std::lock_guard lock(m_mutex);
		m_stream.stream_open = false;
		// Retain the last stream's counters for an export after stopping.
	}

	// Real-time callback path: relaxed atomic increments, no logging, allocation
	// or extra mutex. Intentional silence while paused is excluded.
	void delivered(std::uint64_t requested, std::uint64_t written)
	{
		if (!m_playing.load(std::memory_order_relaxed)) return;
		m_delivered.fetch_add(1, std::memory_order_relaxed);
		m_requested.fetch_add(requested, std::memory_order_relaxed);
		if (written < requested)
		{
			m_short_reads.fetch_add(1, std::memory_order_relaxed);
			m_missing.fetch_add(requested - written, std::memory_order_relaxed);
		}
	}

	void silence(bool resetting, bool lock_acquired)
	{
		if (!m_playing.load(std::memory_order_relaxed)) return;
		auto& counter = resetting ? m_reset_silence :
			!lock_acquired ? m_mutex_timeouts : m_no_callback;
		counter.fetch_add(1, std::memory_order_relaxed);
	}

	snapshot get() const
	{
		std::lock_guard lock(m_mutex);
		auto result = m_stream;
		result.playing = m_playing.load(std::memory_order_relaxed);
		// Counters are independently sampled; a callback may overlap a read.
		result.delivered_callbacks = m_delivered.load(std::memory_order_relaxed);
		result.requested_frames = m_requested.load(std::memory_order_relaxed);
		result.short_read_callbacks = m_short_reads.load(std::memory_order_relaxed);
		result.missing_frames = m_missing.load(std::memory_order_relaxed);
		result.mutex_timeout_callbacks = m_mutex_timeouts.load(std::memory_order_relaxed);
		result.reset_silence_callbacks = m_reset_silence.load(std::memory_order_relaxed);
		result.missing_callback_silence_callbacks = m_no_callback.load(std::memory_order_relaxed);
		return result;
	}
};

inline diagnostics g_diagnostics;
}
