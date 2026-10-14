#include "ui_language.hpp"
#include <cassert>
#include <iostream>
#include <thread>
#include <vector>

int main()
{
    using namespace duke::ui;
    spanish.store(false);
    assert(localized(localized_string_id::PROGRESS_DIALOG_COMPILING_PPU_MODULES, "") == "Compiling PPU Modules...");
    assert(text("Enable Time Stretching") == "Enable Time Stretching");
    spanish.store(true);
    assert(localized(localized_string_id::PROGRESS_DIALOG_COMPILING_PPU_MODULES, "") == "Compilando módulos PPU…");
    assert(text("Enable Time Stretching") == "Ajustar velocidad del audio");
    assert(text("User filename.bin") == "User filename.bin");
    assert(localized32(localized_string_id::CELL_SAVEDATA_DELETE, "Muñeco 🦆") == U"¿Eliminar estos datos?\n\nMuñeco 🦆");
    assert(localized32(localized_string_id::CELL_CROSS_CONTROLLER_MSG, "á%0") ==
        U"Inicia [á%0] en el sistema PS Vita.\nSi [á%0] no está instalado, abre [Uso a distancia] en PS Vita e inicia [Cross-Controller] desde la pantalla LiveArea™.");
    assert(utf32("\xf0\x9f\xa6\x86") == U"🦆");
    assert(utf32("\xc0\xaf") == U"\ufffd\ufffd");
    assert(utf32("\xed\xa0\x80") == U"\ufffd\ufffd\ufffd");
    assert(utf32("\xf4\x90\x80\x80") == U"\ufffd\ufffd\ufffd\ufffd");
    assert(utf32("\xe2") == U"\ufffd");
    for (std::size_t i = 0; i < std::size(english_entries); ++i)
    {
        assert(english_entries[i].id == spanish_entries[i].id);
        for (bool es : {false, true})
        {
            spanish.store(es);
            const auto& e = es ? spanish_entries[i] : english_entries[i];
            assert(utf32(e.text) == e.text32);
            assert(utf32(localized(e.id, "árbol")) == localized32(e.id, "árbol"));
        }
    }
    // Locale selection may change while native progress messages are produced.
    std::vector<std::thread> readers;
    for (unsigned i = 0; i < 6; ++i) readers.emplace_back([] {
        for (unsigned n = 0; n < 10000; ++n)
        {
            const auto text = localized(localized_string_id::PROGRESS_DIALOG_COMPILING_PPU_MODULES, "");
            assert(text == "Compiling PPU Modules..." || text == "Compilando módulos PPU…");
        }
    });
    for (unsigned i = 0; i < 10000; ++i) spanish.store(i % 2);
    for (auto& reader : readers) reader.join();
    std::cout << "Native EN/ES strings, Unicode arguments and concurrent locale reads passed\n";
}
