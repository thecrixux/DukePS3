#pragma once
#include "aes.h"
#include "aes_arm_support.hpp"

// Arm AES uses the same little-endian key schedule as the portable AES code.
// Restrict this path to platforms with an explicit runtime capability check.
#if defined(__aarch64__) && defined(__linux__) && !defined(__AARCH64EB__)

// Older Clang versions guard the intrinsic declarations with feature macros.
// The functions below are targeted separately; the rest of the build keeps its ISA.
#if defined(__clang__) && !defined(__ARM_FEATURE_AES)
#define __ARM_FEATURE_AES 1
#define DUKE_UNDEFINE_ARM_AES
#endif
#if defined(__clang__) && !defined(__ARM_FEATURE_CRYPTO)
#define __ARM_FEATURE_CRYPTO 1
#define DUKE_UNDEFINE_ARM_CRYPTO
#endif
#include <arm_neon.h>
#ifdef DUKE_UNDEFINE_ARM_AES
#undef __ARM_FEATURE_AES
#undef DUKE_UNDEFINE_ARM_AES
#endif
#ifdef DUKE_UNDEFINE_ARM_CRYPTO
#undef __ARM_FEATURE_CRYPTO
#undef DUKE_UNDEFINE_ARM_CRYPTO
#endif

namespace duke::crypto
{
#if defined(__clang__)
    __attribute__((target("aes")))
#elif defined(__GNUC__)
    __attribute__((target("+crypto")))
#endif
    inline int arm_aes_ecb(aes_context* ctx, int mode,
        const unsigned char input[16], unsigned char output[16])
    {
        auto block = vld1q_u8(input);
        const auto* keys = reinterpret_cast<const unsigned char*>(ctx->rk);
        if (mode == AES_DECRYPT)
        {
            for (int round = 0; round < ctx->nr - 1; ++round)
                block = vaesimcq_u8(vaesdq_u8(block, vld1q_u8(keys + round * 16)));
            block = vaesdq_u8(block, vld1q_u8(keys + (ctx->nr - 1) * 16));
        }
        else
        {
            for (int round = 0; round < ctx->nr - 1; ++round)
                block = vaesmcq_u8(vaeseq_u8(block, vld1q_u8(keys + round * 16)));
            block = vaeseq_u8(block, vld1q_u8(keys + (ctx->nr - 1) * 16));
        }
        block = veorq_u8(block, vld1q_u8(keys + ctx->nr * 16));
        vst1q_u8(output, block);
        return 0;
    }
}
#endif
