package dev.stinger.ocr

import kotlin.math.roundToInt
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ViewfinderMapTest {
    @Test
    fun rotationTurnsSensorBufferUpright() {
        assertEquals(1080 to 1920, ViewfinderMap.uprightSize(1920, 1080, 90))
        assertEquals(1080 to 1920, ViewfinderMap.uprightSize(1920, 1080, 270))
        assertEquals(1920 to 1080, ViewfinderMap.uprightSize(1920, 1080, 0))
        assertEquals(1920 to 1080, ViewfinderMap.uprightSize(1920, 1080, 180))
        assertEquals(1080 to 1920, ViewfinderMap.uprightSize(1920, 1080, -90))
    }

    @Test
    fun fillCenterCropsOffscreenSensorEdgesInsteadOfTheWholeFrame() {
        val uprightWidth = 1080
        val uprightHeight = 1920
        val viewWidth = 1080
        val viewHeight = 2400
        val crop = ViewfinderMap.map(
            viewWidth = viewWidth,
            viewHeight = viewHeight,
            uprightWidth = uprightWidth,
            uprightHeight = uprightHeight,
            viewLeft = viewWidth * 0.06f,
            viewTop = viewHeight * 0.06f,
            viewRight = viewWidth * 0.94f,
            viewBottom = viewHeight * 0.58f,
            scale = ViewfinderMap.Scale.FILL_CENTER,
            mirrored = false,
        )
        assertFalse(crop.coversEntire(uprightWidth, uprightHeight))
        assertTrue(crop.left > uprightWidth * 0.10f)
        assertTrue(crop.right < uprightWidth * 0.90f)
        assertTrue(crop.bottom < uprightHeight * 0.70f)
        val rawPercent = ViewfinderMap.Crop(
            left = (1920 * 0.06f).toInt(),
            top = (1080 * 0.06f).toInt(),
            right = (1920 * 0.94f).toInt(),
            bottom = (1080 * 0.58f).toInt(),
        )
        assertTrue(rawPercent.width > crop.width)
        assertTrue(rawPercent.bottom != crop.bottom || rawPercent.right != crop.right)
    }

    @Test
    fun fitCenterLetterboxMapsOnlyTheVisiblePicture() {
        val crop = ViewfinderMap.map(
            viewWidth = 1000,
            viewHeight = 1000,
            uprightWidth = 1000,
            uprightHeight = 500,
            viewLeft = 0f,
            viewTop = 400f,
            viewRight = 1000f,
            viewBottom = 600f,
            scale = ViewfinderMap.Scale.FIT_CENTER,
            mirrored = false,
        )
        assertEquals(0, crop.left)
        assertEquals(1000, crop.right)
        assertEquals(150, crop.top)
        assertEquals(350, crop.bottom)
        assertFalse(crop.coversEntire(1000, 500))
    }

    @Test
    fun frontCameraMirrorsTheViewfinderHorizontally() {
        val crop = ViewfinderMap.map(
            viewWidth = 200,
            viewHeight = 200,
            uprightWidth = 200,
            uprightHeight = 200,
            viewLeft = 10f,
            viewTop = 20f,
            viewRight = 50f,
            viewBottom = 80f,
            scale = ViewfinderMap.Scale.FILL_CENTER,
            mirrored = true,
        )
        assertEquals(150, crop.left)
        assertEquals(190, crop.right)
        assertEquals(20, crop.top)
        assertEquals(80, crop.bottom)
    }

    @Test
    fun sameAspectFillCenterFollowsTheDrawnBoxAndNotTheFullFrame() {
        val crop = ViewfinderMap.map(
            viewWidth = 1080,
            viewHeight = 1920,
            uprightWidth = 1080,
            uprightHeight = 1920,
            viewLeft = 1080 * 0.06f,
            viewTop = 1920 * 0.06f,
            viewRight = 1080 * 0.94f,
            viewBottom = 1920 * 0.58f,
            scale = ViewfinderMap.Scale.FILL_CENTER,
            mirrored = false,
        )
        assertEquals((1080 * 0.06f).roundToInt(), crop.left)
        assertEquals((1920 * 0.06f).roundToInt(), crop.top)
        assertEquals((1080 * 0.94f).roundToInt(), crop.right)
        assertEquals((1920 * 0.58f).roundToInt(), crop.bottom)
        assertFalse(crop.coversEntire(1080, 1920))
    }
}
