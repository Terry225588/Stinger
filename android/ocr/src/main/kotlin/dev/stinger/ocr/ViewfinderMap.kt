package dev.stinger.ocr

import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * 把屏幕上的取景框换算到已经转正的分析图坐标。
 * 预览是 FILL_CENTER 时会裁掉传感器两边或上下，不能按整幅画面的百分比去裁。
 */
object ViewfinderMap {
    enum class Scale {
        FILL_START,
        FILL_CENTER,
        FILL_END,
        FIT_START,
        FIT_CENTER,
        FIT_END,
    }

    data class Crop(val left: Int, val top: Int, val right: Int, val bottom: Int) {
        val width: Int get() = right - left
        val height: Int get() = bottom - top

        fun coversEntire(imageWidth: Int, imageHeight: Int): Boolean {
            return left <= 0 && top <= 0 && right >= imageWidth && bottom >= imageHeight
        }
    }

    fun uprightSize(bufferWidth: Int, bufferHeight: Int, rotationDegrees: Int): Pair<Int, Int> {
        val quarter = Math.floorMod(rotationDegrees, 360)
        return if (quarter == 90 || quarter == 270) {
            bufferHeight to bufferWidth
        } else {
            bufferWidth to bufferHeight
        }
    }

    fun map(
        viewWidth: Int,
        viewHeight: Int,
        uprightWidth: Int,
        uprightHeight: Int,
        viewLeft: Float,
        viewTop: Float,
        viewRight: Float,
        viewBottom: Float,
        scale: Scale,
        mirrored: Boolean,
    ): Crop {
        require(viewWidth > 0 && viewHeight > 0 && uprightWidth > 0 && uprightHeight > 0)
        val fills = scale == Scale.FILL_START || scale == Scale.FILL_CENTER || scale == Scale.FILL_END
        val scaleFactor = if (fills) {
            max(viewWidth / uprightWidth.toFloat(), viewHeight / uprightHeight.toFloat())
        } else {
            min(viewWidth / uprightWidth.toFloat(), viewHeight / uprightHeight.toFloat())
        }
        val displayedWidth = uprightWidth * scaleFactor
        val displayedHeight = uprightHeight * scaleFactor
        val alignEnd = scale == Scale.FILL_END || scale == Scale.FIT_END
        val alignCenter = scale == Scale.FILL_CENTER || scale == Scale.FIT_CENTER
        val offsetX = when {
            alignCenter -> (viewWidth - displayedWidth) / 2f
            alignEnd -> viewWidth - displayedWidth
            else -> 0f
        }
        val offsetY = when {
            alignCenter -> (viewHeight - displayedHeight) / 2f
            alignEnd -> viewHeight - displayedHeight
            else -> 0f
        }
        fun alongX(viewX: Float): Float {
            val x = (viewX - offsetX) / scaleFactor
            return if (mirrored) uprightWidth - x else x
        }
        fun alongY(viewY: Float) = (viewY - offsetY) / scaleFactor
        var left = alongX(viewLeft)
        var right = alongX(viewRight)
        if (left > right) {
            val swap = left
            left = right
            right = swap
        }
        val top = alongY(viewTop)
        val bottom = alongY(viewBottom)
        val cropLeft = left.roundToInt().coerceIn(0, uprightWidth - 1)
        val cropTop = top.roundToInt().coerceIn(0, uprightHeight - 1)
        val cropRight = right.roundToInt().coerceIn(cropLeft + 1, uprightWidth)
        val cropBottom = bottom.roundToInt().coerceIn(cropTop + 1, uprightHeight)
        return Crop(cropLeft, cropTop, cropRight, cropBottom)
    }
}
