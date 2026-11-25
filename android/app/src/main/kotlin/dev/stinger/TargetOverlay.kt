package dev.stinger

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View

/** 取景框。OCR 只使用同一比例的画面，不把底部答案再送去识别。 */
class TargetOverlay @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {
    private val shade = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0x66000000 }
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        style = Paint.Style.STROKE
        strokeWidth = resources.displayMetrics.density * 2f
    }
    private val label = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        textSize = resources.displayMetrics.density * 14f
    }
    private val hole = RectF()

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (width == 0 || height == 0) return
        hole.set(
            width * LEFT,
            height * TOP,
            width * RIGHT,
            height * BOTTOM,
        )
        canvas.drawRect(0f, 0f, width.toFloat(), hole.top, shade)
        canvas.drawRect(0f, hole.bottom, width.toFloat(), height.toFloat(), shade)
        canvas.drawRect(0f, hole.top, hole.left, hole.bottom, shade)
        canvas.drawRect(hole.right, hole.top, width.toFloat(), hole.bottom, shade)
        canvas.drawRect(hole, stroke)
        canvas.drawText("对准题目", hole.left + 12f, hole.top + label.textSize + 8f, label)
    }

    companion object {
        const val LEFT = 0.06f
        const val TOP = 0.06f
        const val RIGHT = 0.94f
        const val BOTTOM = 0.58f
    }
}
