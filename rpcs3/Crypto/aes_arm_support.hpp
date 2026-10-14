#pragma once

#if defined(__aarch64__) && defined(__linux__) && !defined(__AARCH64EB__)
#include <asm/hwcap.h>
#include <sys/auxv.h>
#endif

namespace duke::crypto
{
    inline bool arm_aes_available()
    {
#if defined(__aarch64__) && defined(__linux__) && !defined(__AARCH64EB__)
        static const bool available = (getauxval(AT_HWCAP) & HWCAP_AES) != 0;
        return available;
#else
        return false;
#endif
    }
}
