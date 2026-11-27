package dev.stinger.ocr

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

class LiveLockTest {
    @Test
    fun locksOnlyAfterRepeatedSimilarText() {
        val lock = LiveLock(stableFrames = 3)
        assertIs<LockDecision.Hold>(lock.onText("传输层负责端到端传输"))
        assertIs<LockDecision.Hold>(lock.onText("传输层负责端到端传输"))
        val locked = lock.onText("传输层负责端到端传输。")
        assertEquals("传输层负责端到端传输。", (locked as LockDecision.Replace).text)
        assertIs<LockDecision.Hold>(lock.onText("传输层负责端到端传输"))
    }

    @Test
    fun singleCharacterFlipDoesNotReplaceTheLock() {
        val lock = LiveLock(stableFrames = 2)
        lock.onText("传输层负责端到端传输")
        lock.onText("传输层负责端到端传输")
        assertIs<LockDecision.Hold>(lock.onText("传输层负责端到端传翰"))
        assertIs<LockDecision.Hold>(lock.onText("传输层负责端到端传翰"))
    }

    @Test
    fun motionAndBlurHoldTheLockedResult() {
        val lock = LiveLock(stableFrames = 2)
        lock.onText("操作系统属于系统软件")
        val locked = lock.onText("操作系统属于系统软件")
        assertIs<LockDecision.Replace>(locked)
        assertIs<LockDecision.Hold>(lock.onMotion())
        assertIs<LockDecision.Hold>(lock.onBlur())
        assertIs<LockDecision.Hold>(lock.onText("完全不同的另一道园林题目"))
    }

    @Test
    fun briefEmptyReadsDoNotClearUntilTheyPersist() {
        val lock = LiveLock(stableFrames = 2, emptyFrames = 3)
        lock.onText("路由选择负责转发分组")
        lock.onText("路由选择负责转发分组")
        assertIs<LockDecision.Hold>(lock.onText(""))
        assertIs<LockDecision.Hold>(lock.onText("   "))
        assertIs<LockDecision.Clear>(lock.onText(""))
        assertIs<LockDecision.Hold>(lock.onText(""))
    }

    @Test
    fun aDifferentQuestionUpdatesOnlyAfterItStabilizes() {
        val lock = LiveLock(stableFrames = 3)
        repeat(3) { lock.onText("第一题传输层提供可靠传输") }
        assertIs<LockDecision.Hold>(lock.onText("第二题应用层负责邮件传输"))
        assertIs<LockDecision.Hold>(lock.onText("第二题应用层负责邮件传输"))
        val replaced = lock.onText("第二题应用层负责邮件传输")
        assertEquals("第二题应用层负责邮件传输", (replaced as LockDecision.Replace).text)
    }

    @Test
    fun alternatingTextNeverLocks() {
        val lock = LiveLock(stableFrames = 3)
        repeat(6) { index ->
            val text = if (index % 2 == 0) "甲题干内容完全不同啊" else "乙题干内容也完全不同"
            assertIs<LockDecision.Hold>(lock.onText(text))
        }
    }

    @Test
    fun frameMotionIgnoresTheFirstSampleAndFlagsALargeShift() {
        val motion = FrameMotion(threshold = 10.0)
        val still = IntArray(64 * 64) { 40 }
        assertFalse(motion.observe(still, 64, 64))
        assertFalse(motion.observe(still.copyOf(), 64, 64))
        val moved = IntArray(64 * 64) { 220 }
        assertTrue(motion.observe(moved, 64, 64))
    }
}
