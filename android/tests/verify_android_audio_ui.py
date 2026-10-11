#!/usr/bin/env python3
"""Isolated production audio dropdown test; requires kotlinc and Java, not Compose rendering."""
from pathlib import Path
import os,shutil,subprocess,tempfile,xml.etree.ElementTree as ET,re
root=Path(__file__).resolve().parents[2]
source=root/'android/app/src/main/java/net/rpcs3/ui/settings/AndroidAudioSettings.kt'
strings={n.attrib['name']:n.text for n in ET.parse(root/'android/app/src/main/res/values/android_audio_strings.xml').getroot()}
es={n.attrib['name']:n.text for n in ET.parse(root/'android/app/src/main/res/values-es/android_audio_strings.xml').getroot()}
assert strings.keys()==es.keys()
for name in strings:
    assert re.findall(r'%\d+\$[a-z]',strings[name])==re.findall(r'%\d+\$[a-z]',es[name])
for path in (root/'android/app/src/main/res/values').glob('*.xml'):
    if path.name=='android_audio_strings.xml':continue
    assert not strings.keys() & {n.attrib.get('name') for n in ET.parse(path).getroot()}
stubs={
'runtime.kt':'''package androidx.compose.runtime
import kotlin.reflect.KProperty
@Target(AnnotationTarget.FUNCTION,AnnotationTarget.TYPE)
annotation class Composable
class MutableState<T>(var value:T)
fun <T> mutableStateOf(value:T)=MutableState(value)
fun mutableFloatStateOf(value:Float)=MutableState(value)
fun <T> remember(vararg keys:Any?, block:()->T)=block()
operator fun <T> MutableState<T>.getValue(thisRef:Any?, property:KProperty<*>):T=value
operator fun <T> MutableState<T>.setValue(thisRef:Any?, property:KProperty<*>, next:T){value=next}
''',
'layout.kt':'''package androidx.compose.foundation.layout
import androidx.compose.ui.Modifier
fun Column(modifier:Modifier=Modifier,content:()->Unit){content()}
''',
'modifier.kt':'''package androidx.compose.ui
interface Modifier { companion object : Modifier }
''',
'json.kt':'''package org.json
class JSONArray(val list:List<String>) { fun length()=list.size; fun optString(i:Int)=list.getOrElse(i){""} }
class JSONObject(vararg pairs:Pair<String,Any>) {
 val values=mutableMapOf(*pairs)
 fun optLong(key:String,fallback:Long=0)=values[key]?.toString()?.toLongOrNull()?:fallback
 fun optString(key:String)=values[key]?.toString()?:""
 fun optJSONArray(key:String)=values[key] as? JSONArray
 fun put(key:String,value:Any){values[key]=value}
 companion object { fun quote(s:String)="\\\""+s+"\\\"" }
}
''',
'widgets.kt':'''package net.rpcs3.ui.components
import androidx.compose.ui.Modifier
object FakeUI {
 var label=""; var entries=listOf<String>(); var selected=-1
 var select:(Int)->Unit={}; var slider:(Float)->Unit={}; var finish:()->Unit={}
 var hints=mutableListOf<String>()
 fun reset(){hints.clear()}
}
fun SettingInlineDropdown(label:String,entries:List<String>,selectedIndex:Int,onSelected:(Int)->Unit){
 FakeUI.label=label;FakeUI.entries=entries;FakeUI.selected=selectedIndex;FakeUI.select=onSelected
}
fun SettingSlider(label:String,value:Float,valueRange:ClosedFloatingPointRange<Float>,valueText:String,enabled:Boolean,onValueChange:(Float)->Unit,onValueChangeFinished:()->Unit){
 FakeUI.slider=onValueChange;FakeUI.finish=onValueChangeFinished
}
fun SettingsHint(text:String){FakeUI.hints.add(text)}
''',
'R.kt':'package net.rpcs3\nobject R { object string {\n'+''.join('const val %s=%d\n'%(name,index) for index,name in enumerate(strings))+'} }\n',
'res.kt':'''package androidx.compose.ui.res
fun stringResource(id:Int,vararg args:Any):String { val values=listOf(
'''+','.join('"'+s.replace('\\','\\\\').replace('"','\\"').replace('$','\\$')+'"' for s in strings.values())+'''
); val text=values[id]; return if(args.isEmpty()) text else text.replace("%1\\$d",args[0].toString()).replace("%%","%") }
''',
'main.kt':'''package net.rpcs3.ui.settings
import androidx.compose.ui.Modifier
import net.rpcs3.ui.components.FakeUI
import org.json.JSONObject
fun main(){
 check(isAndroidAudioBackendSetting("Audio@@Android Audio Backend"))
 check(isAndroidAudioBackendSetting("@@Audio@@Android Audio Backend"))
 check(!isAndroidAudioBackendSetting("Audio@@Audio Device"))
 val item=JSONObject("value" to "auto", "default" to "auto")
 val commits=mutableListOf<String>()
 fun render(){FakeUI.reset();AndroidAudioBackendSetting(item,"Audio@@Android Audio Backend","TEST",Modifier){commits.add(it);true}}
 render();check(commits.isEmpty());check(item.optString("value")=="auto");check(FakeUI.selected==0)
 check(FakeUI.entries.size==3 && FakeUI.entries[1]=="AAudio" && FakeUI.entries[2]=="OpenSL ES")
 check(FakeUI.hints.size==1)
 FakeUI.select(2);check(commits.last()=="\\\"opensl\\\"");check(item.optString("value")=="opensl")
 render();check(FakeUI.selected==2)
 FakeUI.select(1);check(commits.last()=="\\\"aaudio\\\"");check(item.optString("value")=="aaudio")
 render();FakeUI.select(0);check(commits.last()=="\\\"auto\\\"");check(item.optString("value")=="auto")
 AndroidAudioBackendSetting(item,"Audio@@Android Audio Backend","TEST",Modifier){false}
 FakeUI.select(1);check(item.optString("value")=="auto")
 val before=commits.size;FakeUI.select(-1);FakeUI.select(3);check(commits.size==before)
 item.put("value","unknown");render();check(commits.size==before && item.optString("value")=="unknown")
 println("PASS: production audio UI Kotlin with widget fixtures; default preserved, exact JSON preference values, failed writes and invalid selections")
}
'''
}
with tempfile.TemporaryDirectory() as directory:
    temp=Path(directory)
    for name,text in stubs.items(): (temp/name).write_text(text)
    subprocess.run([os.environ.get('KOTLINC',shutil.which('kotlinc') or 'kotlinc'),str(source),*map(str,temp.glob('*.kt')),'-include-runtime','-d',str(temp/'test.jar')],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    subprocess.run(['java','-jar',str(temp/'test.jar')],check=True)
print('PASS: resource uniqueness, EN/ES placeholders')
