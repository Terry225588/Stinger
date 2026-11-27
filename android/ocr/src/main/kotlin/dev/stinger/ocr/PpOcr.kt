package dev.stinger.ocr

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.nio.FloatBuffer
import java.util.Collections
import kotlin.math.ceil
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * 离线中文 OCR。检测、方向和识别模型是 RapidOCR 1.4.4 随附的 PP-OCRv4 ONNX，
 * 预处理按同一套参数重写：最短边放到 736、32 对齐、均值和方差 0.5，通道顺序是 BGR。
 * 不下载模型，也不访问网络。
 */
class PpOcr(
    detection: ByteArray,
    recognition: ByteArray,
    classification: ByteArray,
) : AutoCloseable {
    private val environment = OrtEnvironment.getEnvironment()
    private val options = OrtSession.SessionOptions().apply {
        setIntraOpNumThreads(2)
        setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
    }
    private val detector = environment.createSession(detection, options)
    private val recognizer = environment.createSession(recognition, options)
    private val classifier = environment.createSession(classification, options)
    private val characters: List<String> = buildCharacters()

    fun recognize(argb: IntArray, width: Int, height: Int): String {
        if (width < 8 || height < 8 || argb.size < width * height) return ""
        val source = BgrImage.fromArgb(argb, width, height)
        val lines = detectLines(source)
        if (lines.isEmpty()) return ""
        val texts = ArrayList<String>()
        for (line in lines) {
            var crop = source.crop(line.left, line.top, line.right, line.bottom)
            crop = rotateIfVertical(crop)
            crop = correctOrientation(crop)
            val (text, confidence) = readLine(crop)
            if (text.isBlank() || confidence < 0.5f) continue
            if (text.length <= 1 && confidence < 0.9f) continue
            texts.add(text)
        }
        return texts.joinToString("\n")
    }

    override fun close() {
        detector.close()
        recognizer.close()
        classifier.close()
        options.close()
    }

    private fun detectLines(source: BgrImage): List<Line> {
        val resized = source.resizeMinSide(736)
        val input = resized.toNormalizedTensor()
        val probability = detector.runMap(input, resized.height, resized.width)
        val mask = dilate(probability)
        val components = components(probability, mask)
        val scaleX = source.width.toFloat() / resized.width
        val scaleY = source.height.toFloat() / resized.height
        val lines = ArrayList<Line>()
        for (component in components) {
            val span = max(component.width, component.height)
            val pad = max(2, (span * 0.15f).roundToInt())
            val left = ((component.left - pad) * scaleX).roundToInt().coerceIn(0, source.width - 1)
            val top = ((component.top - pad) * scaleY).roundToInt().coerceIn(0, source.height - 1)
            val right = ((component.right + pad) * scaleX).roundToInt().coerceIn(left + 1, source.width)
            val bottom = ((component.bottom + pad) * scaleY).roundToInt().coerceIn(top + 1, source.height)
            if (right - left < 8 || bottom - top < 8) continue
            lines.add(Line(left, top, right, bottom))
        }
        lines.sortWith(compareBy({ it.top }, { it.left }))
        return lines
    }

    private fun OrtSession.runMap(input: FloatArray, height: Int, width: Int): Array<FloatArray> {
        val value = runFloats(input, longArrayOf(1, 3, height.toLong(), width.toLong()))
        val tensor = value as Array<*>
        val first = tensor[0]
        if (first is Array<*> && first.isNotEmpty() && first[0] is FloatArray) {
            @Suppress("UNCHECKED_CAST")
            val channels = first as Array<FloatArray>
            return channels
        }
        @Suppress("UNCHECKED_CAST")
        val nested = first as Array<Array<FloatArray>>
        return nested[0]
    }

    private fun dilate(probability: Array<FloatArray>): Array<BooleanArray> {
        val height = probability.size
        val width = probability[0].size
        val binary = Array(height) { y -> BooleanArray(width) { x -> probability[y][x] > 0.3f } }
        val dilated = Array(height) { BooleanArray(width) }
        for (y in 0 until height) {
            for (x in 0 until width) {
                var on = false
                for (dy in 0..1) {
                    for (dx in 0..1) {
                        val yy = y - dy
                        val xx = x - dx
                        if (yy >= 0 && xx >= 0 && binary[yy][xx]) on = true
                    }
                }
                dilated[y][x] = on
            }
        }
        return dilated
    }

    private fun components(probability: Array<FloatArray>, mask: Array<BooleanArray>): List<Component> {
        val height = mask.size
        val width = mask[0].size
        val seen = Array(height) { BooleanArray(width) }
        val found = ArrayList<Component>()
        val stackX = IntArray(height * width)
        val stackY = IntArray(height * width)
        for (y in 0 until height) {
            for (x in 0 until width) {
                if (!mask[y][x] || seen[y][x]) continue
                var top = 0
                stackX[top] = x
                stackY[top] = y
                top++
                seen[y][x] = true
                var minX = x
                var maxX = x
                var minY = y
                var maxY = y
                var count = 0
                var score = 0f
                while (top > 0) {
                    top--
                    val cx = stackX[top]
                    val cy = stackY[top]
                    count++
                    score += probability[cy][cx]
                    if (cx < minX) minX = cx
                    if (cx > maxX) maxX = cx
                    if (cy < minY) minY = cy
                    if (cy > maxY) maxY = cy
                    top = push(cx - 1, cy, width, height, mask, seen, stackX, stackY, top)
                    top = push(cx + 1, cy, width, height, mask, seen, stackX, stackY, top)
                    top = push(cx, cy - 1, width, height, mask, seen, stackX, stackY, top)
                    top = push(cx, cy + 1, width, height, mask, seen, stackX, stackY, top)
                }
                if (maxX - minX < 3 || maxY - minY < 3) continue
                if (score / count < 0.5f) continue
                found.add(Component(minX, minY, maxX, maxY))
            }
        }
        return found
    }

    private fun push(
        nx: Int,
        ny: Int,
        width: Int,
        height: Int,
        mask: Array<BooleanArray>,
        seen: Array<BooleanArray>,
        stackX: IntArray,
        stackY: IntArray,
        top: Int,
    ): Int {
        if (nx < 0 || ny < 0 || nx >= width || ny >= height) return top
        if (!mask[ny][nx] || seen[ny][nx]) return top
        seen[ny][nx] = true
        stackX[top] = nx
        stackY[top] = ny
        return top + 1
    }

    private fun rotateIfVertical(image: BgrImage): BgrImage {
        if (image.height * 1.0 / image.width >= 1.5) return image.rotate90()
        return image
    }

    private fun correctOrientation(image: BgrImage): BgrImage {
        val targetHeight = 48
        val maxWidth = 192
        val ratio = image.width.toFloat() / image.height.coerceAtLeast(1)
        val resizedWidth = min(maxWidth, max(1, ceil(targetHeight * ratio).toInt()))
        val resized = image.resizeExact(resizedWidth, targetHeight)
        val plane = resized.toNormalizedTensor()
        val padded = FloatArray(3 * targetHeight * maxWidth)
        for (channel in 0 until 3) {
            val sourceBase = channel * targetHeight * resizedWidth
            val destBase = channel * targetHeight * maxWidth
            for (y in 0 until targetHeight) {
                plane.copyInto(
                    padded,
                    destBase + y * maxWidth,
                    sourceBase + y * resizedWidth,
                    sourceBase + (y + 1) * resizedWidth,
                )
            }
        }
        val output = classifier.runFloats(padded, longArrayOf(1, 3, targetHeight.toLong(), maxWidth.toLong()))
        val scores = flattenScores(output)
        if (scores.size >= 2 && scores[1] > scores[0] && scores[1] > 0.9f) return image.rotate180()
        return image
    }

    private fun readLine(image: BgrImage): Pair<String, Float> {
        if (image.width < 2 || image.height < 2) return "" to 0f
        val targetHeight = 48
        val ratio = image.width.toFloat() / image.height
        val maxWidth = max(320, ceil(targetHeight * ratio).toInt()).coerceAtMost(960)
        val resizedWidth = min(maxWidth, max(1, ceil(targetHeight * ratio).toInt()))
        val resized = image.resizeExact(resizedWidth, targetHeight)
        val plane = resized.toNormalizedTensor()
        val padded = FloatArray(3 * targetHeight * maxWidth)
        for (channel in 0 until 3) {
            val source = channel * targetHeight * resizedWidth
            val dest = channel * targetHeight * maxWidth
            for (y in 0 until targetHeight) {
                plane.copyInto(
                    padded,
                    dest + y * maxWidth,
                    source + y * resizedWidth,
                    source + y * resizedWidth + resizedWidth,
                )
            }
        }
        val output = recognizer.runFloats(padded, longArrayOf(1, 3, targetHeight.toLong(), maxWidth.toLong()))
        return decode(output)
    }

    private fun decode(output: Any): Pair<String, Float> {
        val steps = sequenceScores(output)
        if (steps.isEmpty()) return "" to 0f
        val chosen = ArrayList<Int>()
        val confidence = ArrayList<Float>()
        var previous = -1
        for ((index, score) in steps) {
            if (index != 0 && index != previous) {
                chosen.add(index)
                confidence.add(score)
            }
            previous = index
        }
        if (chosen.isEmpty()) return "" to 0f
        val text = buildString {
            for (index in chosen) {
                if (index in characters.indices) append(characters[index])
            }
        }
        return text to confidence.average().toFloat()
    }

    private fun sequenceScores(output: Any): List<Pair<Int, Float>> {
        val matrix: Array<FloatArray> = when (output) {
            is Array<*> -> {
                val first = output.firstOrNull()
                when (first) {
                    is FloatArray -> {
                        @Suppress("UNCHECKED_CAST")
                        output as Array<FloatArray>
                    }
                    is Array<*> -> {
                        @Suppress("UNCHECKED_CAST")
                        (first as Array<FloatArray>)
                    }
                    else -> return emptyList()
                }
            }
            else -> return emptyList()
        }
        return matrix.map { row ->
            var best = 0
            var score = Float.NEGATIVE_INFINITY
            for (index in row.indices) {
                if (row[index] > score) {
                    score = row[index]
                    best = index
                }
            }
            best to score
        }
    }

    private fun flattenScores(output: Any): FloatArray {
        return when (output) {
            is FloatArray -> output
            is Array<*> -> {
                val first = output.firstOrNull()
                if (first is FloatArray) first else FloatArray(0)
            }
            else -> FloatArray(0)
        }
    }

    private fun OrtSession.runFloats(data: FloatArray, shape: LongArray): Any {
        val tensor = OnnxTensor.createTensor(environment, FloatBuffer.wrap(data), shape)
        tensor.use {
            val input = Collections.singletonMap(inputNames.first(), tensor)
            run(input).use { result ->
                return result.get(0).value
            }
        }
    }

    private fun buildCharacters(): List<String> {
        val raw = recognizer.metadata.customMetadata["character"] ?: error("识别模型里没有字符表")
        val listed = raw.split('\n').map { it.trimEnd('\r') }.filter { it.isNotEmpty() }
        return listOf("blank") + listed + listOf(" ")
    }

    private class Component(val left: Int, val top: Int, val right: Int, val bottom: Int) {
        val width: Int get() = right - left + 1
        val height: Int get() = bottom - top + 1
    }

    private class Line(val left: Int, val top: Int, val right: Int, val bottom: Int)
}

private class BgrImage(val width: Int, val height: Int, val data: ByteArray) {
    fun crop(left: Int, top: Int, right: Int, bottom: Int): BgrImage {
        val w = (right - left).coerceAtLeast(1)
        val h = (bottom - top).coerceAtLeast(1)
        val out = ByteArray(w * h * 3)
        for (y in 0 until h) {
            val source = ((top + y) * width + left) * 3
            val dest = y * w * 3
            data.copyInto(out, dest, source, source + w * 3)
        }
        return BgrImage(w, h, out)
    }

    fun resizeMinSide(limit: Int): BgrImage {
        val ratio = if (min(width, height) < limit) limit.toFloat() / min(width, height) else 1f
        val resizedW = max(32, (roundToMultiple(width * ratio))).coerceAtLeast(32)
        val resizedH = max(32, (roundToMultiple(height * ratio))).coerceAtLeast(32)
        return resizeExact(resizedW, resizedH)
    }

    fun resizeHeight(targetHeight: Int, maxWidth: Int): BgrImage {
        val ratio = width.toFloat() / height
        val resizedW = min(maxWidth, max(1, ceil(targetHeight * ratio).toInt()))
        val image = resizeExact(resizedW, targetHeight)
        if (resizedW == maxWidth) return image
        val padded = ByteArray(maxWidth * targetHeight * 3)
        for (y in 0 until targetHeight) {
            image.data.copyInto(padded, y * maxWidth * 3, y * resizedW * 3, (y + 1) * resizedW * 3)
        }
        return BgrImage(maxWidth, targetHeight, padded)
    }

    fun resizeExact(targetWidth: Int, targetHeight: Int): BgrImage {
        if (targetWidth == width && targetHeight == height) return this
        val out = ByteArray(targetWidth * targetHeight * 3)
        for (y in 0 until targetHeight) {
            val fy = (y + 0.5f) * height / targetHeight - 0.5f
            val y0 = fy.toInt().coerceIn(0, height - 1)
            val y1 = min(y0 + 1, height - 1)
            val wy = (fy - y0).coerceIn(0f, 1f)
            for (x in 0 until targetWidth) {
                val fx = (x + 0.5f) * width / targetWidth - 0.5f
                val x0 = fx.toInt().coerceIn(0, width - 1)
                val x1 = min(x0 + 1, width - 1)
                val wx = (fx - x0).coerceIn(0f, 1f)
                val dest = (y * targetWidth + x) * 3
                for (channel in 0 until 3) {
                    val p00 = data[(y0 * width + x0) * 3 + channel].toInt() and 0xFF
                    val p01 = data[(y0 * width + x1) * 3 + channel].toInt() and 0xFF
                    val p10 = data[(y1 * width + x0) * 3 + channel].toInt() and 0xFF
                    val p11 = data[(y1 * width + x1) * 3 + channel].toInt() and 0xFF
                    val top = p00 + (p01 - p00) * wx
                    val bottom = p10 + (p11 - p10) * wx
                    out[dest + channel] = (top + (bottom - top) * wy).roundToInt().coerceIn(0, 255).toByte()
                }
            }
        }
        return BgrImage(targetWidth, targetHeight, out)
    }

    fun rotate90(): BgrImage {
        val out = ByteArray(width * height * 3)
        for (y in 0 until height) {
            for (x in 0 until width) {
                val nx = y
                val ny = width - 1 - x
                val source = (y * width + x) * 3
                val dest = (ny * height + nx) * 3
                data.copyInto(out, dest, source, source + 3)
            }
        }
        return BgrImage(height, width, out)
    }

    fun rotate180(): BgrImage {
        val out = ByteArray(data.size)
        val pixels = width * height
        for (index in 0 until pixels) {
            val dest = (pixels - 1 - index) * 3
            val source = index * 3
            data.copyInto(out, dest, source, source + 3)
        }
        return BgrImage(width, height, out)
    }

    fun toNormalizedTensor(): FloatArray {
        val plane = width * height
        val tensor = FloatArray(3 * plane)
        for (index in 0 until plane) {
            val source = index * 3
            for (channel in 0 until 3) {
                val value = (data[source + channel].toInt() and 0xFF) / 255f
                tensor[channel * plane + index] = (value - 0.5f) / 0.5f
            }
        }
        return tensor
    }

    companion object {
        fun fromArgb(pixels: IntArray, width: Int, height: Int): BgrImage {
            val data = ByteArray(width * height * 3)
            var dest = 0
            val count = width * height
            for (index in 0 until count) {
                val pixel = pixels[index]
                data[dest++] = (pixel and 0xFF).toByte()
                data[dest++] = ((pixel shr 8) and 0xFF).toByte()
                data[dest++] = ((pixel shr 16) and 0xFF).toByte()
            }
            return BgrImage(width, height, data)
        }

        private fun roundToMultiple(value: Float): Int {
            return (kotlin.math.round(value / 32f) * 32f).toInt()
        }
    }
}
