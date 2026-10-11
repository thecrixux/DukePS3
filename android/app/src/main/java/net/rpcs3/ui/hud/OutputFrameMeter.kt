package net.rpcs3.ui.hud

/** Successful Vulkan present requests per second, including original frames.
 * This is not a measurement of physical scanout or the emulator's speed.
 */
class OutputFrameMeter {
    private data class Point(val at: Long, val count: Long)
    private val points = java.util.ArrayDeque<Point>()

    fun sample(now: Long, presented: Long, enabled: Boolean): Float {
        if (!enabled) {
            points.clear()
            return Float.NaN
        }
        val previous = points.peekLast()
        if (previous != null && (now <= previous.at || presented < previous.count ||
                    now - previous.at > 2000L)) {
            points.clear()
        }
        points.addLast(Point(now, presented))
        // Keep one anchor at or just before the last second, including stalled output.
        while (points.size > 2 && points.elementAt(1).at <= now - 1000L) {
            points.removeFirst()
        }
        val first = points.peekFirst() ?: return Float.NaN
        val elapsed = now - first.at
        return if (elapsed > 0L) (presented - first.count) * 1000f / elapsed else Float.NaN
    }
}
