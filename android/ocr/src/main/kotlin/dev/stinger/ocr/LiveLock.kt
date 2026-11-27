package dev.stinger.ocr

import dev.stinger.match.recognitionKey
import kotlin.math.abs
import kotlin.math.max

/**
 * 连续几帧文字接近才锁定题干。轻微晃动造成的单字跳动、短暂空白或画面还在动时，保持上一次结果。
 */
class LiveLock(
    private val stableFrames: Int = 3,
    private val emptyFrames: Int = 4,
) {
    private var locked: String? = null
    private var pending: String? = null
    private var pendingCount = 0
    private var emptyCount = 0

    fun onMotion(): LockDecision = hold()

    fun onBlur(): LockDecision = hold()

    fun onText(raw: String): LockDecision {
        val shown = raw.trim()
        if (shown.isEmpty()) {
            pending = null
            pendingCount = 0
            emptyCount += 1
            if (locked != null && emptyCount < emptyFrames) return LockDecision.Hold
            if (emptyCount >= emptyFrames) {
                val hadLock = locked != null
                locked = null
                return if (hadLock || emptyCount == emptyFrames) LockDecision.Clear else LockDecision.Hold
            }
            return LockDecision.Hold
        }
        emptyCount = 0
        val lockedText = locked
        if (lockedText != null && similar(shown, lockedText)) {
            pending = null
            pendingCount = 0
            return LockDecision.Hold
        }
        val pendingText = pending
        if (pendingText != null && similar(shown, pendingText)) {
            pendingCount += 1
            pending = shown
        } else {
            pending = shown
            pendingCount = 1
        }
        if (pendingCount >= stableFrames) {
            locked = pending
            pending = null
            pendingCount = 0
            return LockDecision.Replace(locked!!)
        }
        return LockDecision.Hold
    }

    private fun hold(): LockDecision {
        pending = null
        pendingCount = 0
        return LockDecision.Hold
    }
}

sealed class LockDecision {
    data object Hold : LockDecision()
    data class Replace(val text: String) : LockDecision()
    data object Clear : LockDecision()
}

fun similarOcrText(left: String, right: String): Boolean {
    val a = recognitionKey(left)
    val b = recognitionKey(right)
    if (a.isEmpty() || b.isEmpty()) return false
    if (a == b) return true
    val limit = max(1, max(a.length, b.length) / 12)
    return levenshtein(a, b, limit) <= limit
}

private fun similar(left: String, right: String): Boolean = similarOcrText(left, right)

fun levenshtein(left: String, right: String, limit: Int): Int {
    if (abs(left.length - right.length) > limit) return limit + 1
    if (left == right) return 0
    var previous = IntArray(right.length + 1) { it }
    var current = IntArray(right.length + 1)
    for (i in 1..left.length) {
        current[0] = i
        var rowBest = current[0]
        val ca = left[i - 1]
        for (j in 1..right.length) {
            val cost = if (ca == right[j - 1]) 0 else 1
            current[j] = minOf(
                current[j - 1] + 1,
                previous[j] + 1,
                previous[j - 1] + cost,
            )
            if (current[j] < rowBest) rowBest = current[j]
        }
        if (rowBest > limit) return limit + 1
        val swap = previous
        previous = current
        current = swap
    }
    return previous[right.length]
}

/**
 * 取景框缩小后的灰度差。超过阈值视为还在移动，先不采用新的识别结果。
 */
class FrameMotion(private val threshold: Double = 14.0) {
    private var last: IntArray? = null

    fun observe(pixels: IntArray, width: Int, height: Int): Boolean {
        val sample = downsampleGray(pixels, width, height, 32, 32)
        val previous = last
        last = sample
        if (previous == null || previous.size != sample.size) return false
        return meanAbs(previous, sample) >= threshold
    }

    companion object {
        fun downsampleGray(pixels: IntArray, width: Int, height: Int, sampleWidth: Int, sampleHeight: Int): IntArray {
            val out = IntArray(sampleWidth * sampleHeight)
            var index = 0
            for (y in 0 until sampleHeight) {
                val sourceY = y * height / sampleHeight
                for (x in 0 until sampleWidth) {
                    val sourceX = x * width / sampleWidth
                    val pixel = pixels[sourceY * width + sourceX]
                    val red = (pixel shr 16) and 0xFF
                    val green = (pixel shr 8) and 0xFF
                    val blue = pixel and 0xFF
                    out[index++] = (red * 30 + green * 59 + blue * 11) / 100
                }
            }
            return out
        }

        fun meanAbs(left: IntArray, right: IntArray): Double {
            var sum = 0.0
            for (index in left.indices) sum += abs(left[index] - right[index])
            return sum / left.size
        }
    }
}
