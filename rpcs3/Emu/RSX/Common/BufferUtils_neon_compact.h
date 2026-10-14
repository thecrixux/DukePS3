// Adapted from RPCS3 PR #19756, merged 2026-10-10.
// https://github.com/RPCS3/rpcs3/pull/19756
// DukePS3: only the NEON primitive-restart compaction path is imported here.

#pragma once

#include <algorithm>
#include <array>
#include <bit>
#include <span>
#include <tuple>
#include <type_traits>

#if defined(ARCH_ARM64)
#include <arm_neon.h>

namespace
{
	template <usz Bytes, usz Lanes>
	constexpr auto make_compress_table()
	{
		std::array<std::array<u8, 16>, 1u << Lanes> table{};

		for (usz mask = 0; mask < table.size(); ++mask)
		{
			table[mask].fill(0xff);
			usz out = 0;

			for (usz lane = 0; lane < Lanes; ++lane)
			{
				if (mask & (1u << lane))
				{
					for (usz byte = 0; byte < Bytes; ++byte)
					{
						table[mask][out++] = static_cast<u8>(lane * Bytes + byte);
					}
				}
			}
		}

		return table;
	}

	alignas(64) constexpr auto s_compress_u16 = make_compress_table<2, 8>();
	alignas(64) constexpr auto s_compress_u32 = make_compress_table<4, 4>();

	template <typename T>
	std::tuple<T, T, u32> upload_swapped_neon_skip_restart(std::span<to_be_t<const T>> src, std::span<T> dst, T restart_index)
	{
		static_assert(std::is_same_v<T, u16> || std::is_same_v<T, u32>);
		const u32 count = ::size32(src);
		u32 i = 0;
		u32 written = 0;
		T min_index = static_cast<T>(-1);
		T max_index = 0;

		if constexpr (sizeof(T) == 2)
		{
			auto min = vdupq_n_u16(-1);
			auto max = vdupq_n_u16(0);
			const u16 weights[] = {1, 2, 4, 8, 16, 32, 64, 128};

			for (; count - i >= 8; i += 8)
			{
				const auto value = vreinterpretq_u16_u8(vrev16q_u8(vld1q_u8(reinterpret_cast<const u8*>(src.data() + i))));
				const auto removed = vceqq_u16(value, vdupq_n_u16(restart_index));
				min = vminq_u16(min, vorrq_u16(value, removed));
				max = vmaxq_u16(max, vbicq_u16(value, removed));
				const u32 mask = vaddvq_u16(vbicq_u16(vld1q_u16(weights), removed));
				const auto packed = vqtbl1q_u8(vreinterpretq_u8_u16(value), vld1q_u8(s_compress_u16[mask].data()));
				// written <= i, so the full store stays inside the input-sized destination.
				vst1q_u8(reinterpret_cast<u8*>(dst.data() + written), packed);
				written += std::popcount(mask);
			}

			min_index = vminvq_u16(min);
			max_index = vmaxvq_u16(max);
		}
		else
		{
			auto min = vdupq_n_u32(-1);
			auto max = vdupq_n_u32(0);
			const u32 weights[] = {1, 2, 4, 8};

			for (; count - i >= 4; i += 4)
			{
				const auto value = vreinterpretq_u32_u8(vrev32q_u8(vld1q_u8(reinterpret_cast<const u8*>(src.data() + i))));
				const auto removed = vceqq_u32(value, vdupq_n_u32(restart_index));
				min = vminq_u32(min, vorrq_u32(value, removed));
				max = vmaxq_u32(max, vbicq_u32(value, removed));
				const u32 mask = vaddvq_u32(vbicq_u32(vld1q_u32(weights), removed));
				const auto packed = vqtbl1q_u8(vreinterpretq_u8_u32(value), vld1q_u8(s_compress_u32[mask].data()));
				vst1q_u8(reinterpret_cast<u8*>(dst.data() + written), packed);
				written += std::popcount(mask);
			}

			min_index = vminvq_u32(min);
			max_index = vmaxvq_u32(max);
		}

		for (; i < count; ++i)
		{
			const T value = src[i];
			if (value != restart_index)
			{
				min_index = std::min(min_index, value);
				max_index = std::max(max_index, value);
				dst[written++] = value;
			}
		}

		return {min_index, max_index, written};
	}
} // namespace
#endif // ARCH_ARM64
