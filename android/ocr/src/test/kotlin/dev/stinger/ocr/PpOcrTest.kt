package dev.stinger.ocr

import java.io.File
import javax.imageio.ImageIO
import kotlin.test.Test
import kotlin.test.assertTrue

class PpOcrTest {
    @Test
    fun readsPrintedChineseWithoutANetwork() {
        val models = File("../app/src/main/assets/ocr")
        val engine = PpOcr(
            File(models, "ch_PP-OCRv4_det_infer.onnx").readBytes(),
            File(models, "ch_PP-OCRv4_rec_infer.onnx").readBytes(),
            File(models, "ch_ppocr_mobile_v2.0_cls_infer.onnx").readBytes(),
        )
        engine.use {
            val image = ImageIO.read(javaClass.classLoader.getResource("sample_cn.png"))
            val pixels = IntArray(image.width * image.height)
            image.getRGB(0, 0, image.width, image.height, pixels, 0, image.width)
            val text = engine.recognize(pixels, image.width, image.height)
            assertTrue(text.contains("传输层负责端到端传输"), text)
            assertTrue(text.contains("端到端可靠传输"), text)
            assertTrue(text.contains("路由选择"), text)
            assertTrue(text.contains("调制解调"), text)
        }
    }
}
