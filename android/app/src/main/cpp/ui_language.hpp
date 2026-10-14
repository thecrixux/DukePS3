#pragma once

#include "Emu/localized_string_id.h"
#include <array>
#include <atomic>
#include <string>
#include <string_view>
#include <utility>

namespace duke::ui
{
    inline std::atomic<bool> spanish{false};
    struct localized_entry
    {
        localized_string_id id;
        std::string_view text;
        std::u32string_view text32;
    };

#define MAKE_STRING(id, x) {localized_string_id::id, x, U##x}
    inline constexpr localized_entry english_entries[] = {
#include "localized_strings.inl"
    };
    inline constexpr localized_entry spanish_entries[] = {
#include "localized_strings_es.inl"
    };
#undef MAKE_STRING
    static_assert(std::size(english_entries) == std::size(spanish_entries));

    // UTF-8 arguments (game names and filenames) also need a Unicode conversion.
    inline std::u32string utf32(std::string_view input)
    {
        std::u32string result;
        for (std::size_t i = 0; i < input.size();)
        {
            const unsigned char first = input[i];
            unsigned length = first < 0x80 ? 1 : first >= 0xc2 && first <= 0xdf ? 2
                : first >= 0xe0 && first <= 0xef ? 3 : first >= 0xf0 && first <= 0xf4 ? 4 : 0;
            char32_t code = length == 1 ? first : length ? first & ((1u << (7 - length)) - 1) : 0;
            bool valid = length && input.size() - i >= length;
            for (unsigned n = 1; valid && n < length; ++n)
            {
                const unsigned char next = input[i + n];
                valid = (next & 0xc0) == 0x80;
                code = (code << 6) | (next & 0x3f);
            }
            valid = valid && (length != 2 || code >= 0x80) && (length != 3 || code >= 0x800)
                && (length != 4 || code >= 0x10000) && code <= 0x10ffff
                && !(code >= 0xd800 && code <= 0xdfff);
            result += valid ? code : 0xfffd;
            i += valid ? length : 1;
        }
        return result;
    }

    template <typename String, typename View>
    inline void replace_argument(String& text, View token, const String& replacement)
    {
        std::size_t pos = 0;
        while ((pos = text.find(token, pos)) != String::npos)
        {
            text.replace(pos, token.size(), replacement);
            pos += replacement.size();
        }
    }

    inline const localized_entry* entry(localized_string_id id)
    {
        const auto* values = spanish.load(std::memory_order_relaxed) ? spanish_entries : english_entries;
        for (std::size_t i = 0; i < std::size(english_entries); ++i)
            if (values[i].id == id) return values + i;
        return nullptr;
    }

    inline std::string localized(localized_string_id id, const char* arg)
    {
        const auto* value = entry(id);
        if (!value) return {};
        std::string text(value->text);
        replace_argument(text, std::string_view("%0"), std::string(arg ? arg : ""));
        return text;
    }

    inline std::u32string localized32(localized_string_id id, const char* arg)
    {
        const auto* value = entry(id);
        if (!value) return {};
        std::u32string text(value->text32);
        replace_argument(text, std::u32string_view(U"%0"), utf32(arg ? arg : ""));
        return text;
    }

    inline std::string text(std::string_view canonical)
    {
        if (spanish.load(std::memory_order_relaxed))
        {
            static constexpr std::pair<std::string_view, std::string_view> labels[] = {
#include "native_text_es.inl"
            };
            for (const auto& [key, value] : labels)
                if (key == canonical) return std::string(value);
        }
        return std::string(canonical);
    }
}
