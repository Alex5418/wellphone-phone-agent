package com.example.phoneagent

import android.view.accessibility.AccessibilityNodeInfo
import org.junit.Assert.assertEquals
import org.junit.Test
import org.mockito.Mockito.mock
import org.mockito.Mockito.`when`

/** 探路：JVM 单测里能不能 mock AccessibilityNodeInfo 并喂给 Snapshot 的纯函数。 */
class ProbeMockTest {
    @Test
    fun canMockNodeAndReadThroughSnapshot() {
        val n = mock(AccessibilityNodeInfo::class.java)
        `when`(n.className).thenReturn("android.widget.Button")
        `when`(n.text).thenReturn("Send")
        assertEquals("android.widget.Button", Snapshot.cls(n))
        assertEquals("Send", Snapshot.text(n))
    }
}
