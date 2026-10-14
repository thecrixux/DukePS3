"""Validate resource coverage, formatting and display/config separation."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / 'android/app/src/main/res'
JAVA = ROOT / 'android/app/src/main/java/net/rpcs3'

def resources(folder):
    result = {}
    for path in (RES / folder).glob('*.xml'):
        for element in ET.parse(path).getroot():
            if element.tag not in ('string', 'plurals', 'string-array'):
                continue
            name = element.attrib['name']
            assert name not in result, f'Duplicate {folder}/{name}'
            result[name] = element
    return result

en, es = resources('values'), resources('values-es')
assert en.keys() == es.keys(), f'Missing Spanish: {en.keys() - es.keys()}; missing English: {es.keys() - en.keys()}'
pattern = re.compile(r'%(\d+)\$[0-9.]*([a-zA-Z])')
for name, source in en.items():
    target = es[name]
    assert source.tag == target.tag, name
    source_items = [source] if source.tag == 'string' else list(source)
    target_items = [target] if target.tag == 'string' else list(target)
    if source.tag == 'plurals':
        assert {e.attrib['quantity'] for e in target_items} >= {'one', 'other'}, name
    assert len(source_items) == len(target_items), name
    for a, b in zip(source_items, target_items):
        assert sorted(pattern.findall(a.text or '')) == sorted(pattern.findall(b.text or '')), name
    assert source.attrib.get('formatted', 'true') == target.attrib.get('formatted', 'true'), name

# All native settings in this revision must have a presentation label.
canonical = set(re.findall(r'(?:this|_this)\s*,\s*"([^"]+)"', (ROOT / 'rpcs3/Emu/system_config.h').read_text()))
mapping = (JAVA / 'ui/settings/ConfigText.kt').read_text()
labels = set(re.findall(r'"([^"]+)" to R.string.config_text_', mapping))
assert canonical <= labels, canonical - labels
settings = (JAVA / 'ui/settings/SettingItem.kt').read_text()
assert 'entries = variants.map { ConfigText.label(context, it) }' in settings
assert 'val chosen = variants.getOrNull(next)' in settings
assert 'JSONObject.quote(chosen)' in settings  # Translated values never go into config.
advanced = (JAVA / 'ui/settings/AdvancedSettingsScreen.kt').read_text()
assert 'valueToText = { ConfigText.label(context, it) }' in advanced
assert 'values = variants,' in advanced
assert 'ConfigText.label(context, it).contains(searchQuery' in advanced

for path in ('MainActivity.kt', 'RPCS3Activity.kt', 'overlay/OverlayEditActivity.kt'):
    assert 'AppCompatActivity()' in (JAVA / path).read_text(), path
manifest = (ROOT / 'android/app/src/main/AndroidManifest.xml').read_text()
assert 'android:localeConfig="@xml/locales_config"' in manifest
assert 'androidx.appcompat.app.AppLocalesMetadataHolderService' in manifest
assert 'android:name="autoStoreLocales" android:value="true"' in manifest
assert 'com.crixux.dukeps3' in (ROOT / 'android/app/build.gradle.kts').read_text()
locales = ET.parse(RES / 'xml/locales_config.xml').getroot()
assert {e.attrib['{http://schemas.android.com/apk/res/android}name'] for e in locales} == {'en', 'es'}

for path in JAVA.rglob('*.kt'):
    for key in re.findall(r'(?<!android\.)R\.string\.(\w+)', path.read_text()):
        assert key in en, f'{path}: unknown string {key}'

print(f'EN/ES: {len(en)} resources, all settings labels, plurals, format arguments and locale wiring verified')
