#!/usr/bin/env python3
"""Compile the production Kotlin HUD meter and verify stalls/restarts/FG toggles."""
from pathlib import Path
import os
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'android/app/src/main/java/net/rpcs3/ui/hud/OutputFrameMeter.kt'
TEST='''
import net.rpcs3.ui.hud.OutputFrameMeter
import kotlin.math.abs
fun equal(actual: Float, expected: Float) { check(abs(actual-expected)<0.01f) { "$actual != $expected" } }
fun main() {
    val meter=OutputFrameMeter()
    check(meter.sample(0,100,true).isNaN())
    equal(meter.sample(500,130,true),60f)
    equal(meter.sample(1000,160,true),60f)
    equal(meter.sample(1500,160,true),30f)
    equal(meter.sample(2000,160,true),0f) // stalled output is zero, not hidden
    equal(meter.sample(2500,170,true),10f)
    check(meter.sample(3000,180,false).isNaN())
    check(meter.sample(3500,200,true).isNaN()) // toggling starts a fresh window
    equal(meter.sample(4000,230,true),60f)
    check(meter.sample(4500,1,true).isNaN()) // counter reset
    equal(meter.sample(5000,16,true),30f)
    check(meter.sample(5000,16,true).isNaN()) // duplicated timestamp
    check(meter.sample(8001,100,true).isNaN()) // pause discards stale rate
    equal(meter.sample(8501,115,true),30f)
    println("Kotlin HUD meter: normal output, stall, zero, toggles, counter reset and pause passed")
}
'''
with tempfile.TemporaryDirectory() as directory:
    temp=Path(directory); test=temp/'Test.kt'; test.write_text(TEST); binary=temp/'meter.jar'
    subprocess.run([os.environ.get('KOTLINC','kotlinc'),str(SOURCE),str(test),'-include-runtime','-d',str(binary)],check=True)
    subprocess.run(['java','-jar',str(binary)],check=True)
view=(SOURCE.parent/'HudView.kt').read_text()
assert 'if (!sample.frameGenerationEnabled)' in view
assert 'if (sample.outputFps <= 0f)' not in view
activity=(SOURCE.parents[2]/'RPCS3Activity.kt').read_text()
assert 'generated > lastGenerated' not in activity
assert 'optBoolean("frameGenEnabled", false)' in activity
print('HUD visibility depends on configured Frame Gen, not intermittent generated frames')
