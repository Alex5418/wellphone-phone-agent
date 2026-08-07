package com.example.phoneagent

import android.view.accessibility.AccessibilityNodeInfo
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test
import org.mockito.Mockito.mock
import org.mockito.Mockito.`when`

class TreeHashTest {

    private fun node(
        cls: String? = null,
        viewId: String? = null,
        text: String? = null,
        contentDesc: String? = null,
        clickable: Boolean = false,
        checked: Boolean = false,
    ): AccessibilityNodeInfo {
        val n = mock(AccessibilityNodeInfo::class.java)
        if (cls != null) `when`(n.className).thenReturn(cls)
        if (viewId != null) `when`(n.viewIdResourceName).thenReturn(viewId)
        if (text != null) `when`(n.text).thenReturn(text)
        if (contentDesc != null) `when`(n.contentDescription).thenReturn(contentDesc)
        `when`(n.isClickable).thenReturn(clickable)
        `when`(n.isChecked).thenReturn(checked)
        return n
    }

    private fun flat(
        node: AccessibilityNodeInfo,
        idx: Int = 0,
        parent: Int = -1,
        depth: Int = 0,
        rootOrdinal: Int = 0,
        childIndex: Int = 0,
    ) = Snapshot.Flat(idx, parent, depth, node, rootOrdinal, childIndex)

    private fun flatTree(nodes: List<Snapshot.Flat>) =
        Snapshot.FlatTree(nodes, false, emptyList())

    @Test
    fun a1_sameTreeTwice_sameHash() {
        val n = node(cls = "android.widget.Button", text = "Send")
        val tree = flatTree(listOf(flat(n)))
        assertEquals(Snapshot.treeHash(tree), Snapshot.treeHash(tree))
    }

    @Test
    fun a2_changeText_hashChanges() {
        val n1 = node(cls = "android.widget.Button", text = "Send")
        val n2 = node(cls = "android.widget.Button", text = "Cancel")
        val h1 = Snapshot.treeHash(flatTree(listOf(flat(n1))))
        val h2 = Snapshot.treeHash(flatTree(listOf(flat(n2))))
        assertNotEquals(h1, h2)
    }

    @Test
    fun a3_changeClickable_hashChanges() {
        val n1 = node(cls = "android.widget.Button", clickable = false)
        val n2 = node(cls = "android.widget.Button", clickable = true)
        val h1 = Snapshot.treeHash(flatTree(listOf(flat(n1))))
        val h2 = Snapshot.treeHash(flatTree(listOf(flat(n2))))
        assertNotEquals(h1, h2)
    }

    @Test
    fun a4_orderMatters_hashChanges() {
        val na = node(cls = "android.widget.Button", text = "A")
        val nb = node(cls = "android.widget.Button", text = "B")
        val t1 = flatTree(listOf(flat(na, 0), flat(nb, 1)))
        val t2 = flatTree(listOf(flat(nb, 0), flat(na, 1)))
        assertNotEquals(Snapshot.treeHash(t1), Snapshot.treeHash(t2))
    }

    @Test
    fun a5_separatorPreventsConcatenationCollision() {
        val n1 = node(cls = "X", text = "a", contentDesc = "b")
        val n2 = node(cls = "X", text = "ab", contentDesc = null)
        val h1 = Snapshot.treeHash(flatTree(listOf(flat(n1))))
        val h2 = Snapshot.treeHash(flatTree(listOf(flat(n2))))
        assertNotEquals("SEP should prevent text+desc concatenation collision", h1, h2)
    }
}
