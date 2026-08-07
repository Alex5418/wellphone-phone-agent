package com.example.phoneagent

import android.view.accessibility.AccessibilityNodeInfo
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.mockito.Mockito.mock
import org.mockito.Mockito.`when`

class LocatorResolverTest {

    private fun node(
        cls: String? = null,
        viewId: String? = null,
        text: String? = null,
        contentDesc: String? = null,
        clickable: Boolean = false,
        longClickable: Boolean = false,
        scrollable: Boolean = false,
        editable: Boolean = false,
    ): AccessibilityNodeInfo {
        val n = mock(AccessibilityNodeInfo::class.java)
        if (cls != null) `when`(n.className).thenReturn(cls)
        if (viewId != null) `when`(n.viewIdResourceName).thenReturn(viewId)
        if (text != null) `when`(n.text).thenReturn(text)
        if (contentDesc != null) `when`(n.contentDescription).thenReturn(contentDesc)
        `when`(n.isClickable).thenReturn(clickable)
        `when`(n.isLongClickable).thenReturn(longClickable)
        `when`(n.isScrollable).thenReturn(scrollable)
        `when`(n.isEditable).thenReturn(editable)
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

    private fun spec(
        strategy: String = "L1",
        resourceId: String? = null,
        text: String? = null,
        contentDesc: String? = null,
        cls: String? = null,
        index: Int = 0,
        target: String = "self",
        path: List<Int>? = null,
    ) = LocatorResolver.Spec(strategy, resourceId, text, contentDesc, cls, index, target, path)

    @Test
    fun b1_l1_uniqueResourceId_found() {
        val n = node(viewId = "com.example:id/target")
        val tree = flatTree(listOf(flat(n)))
        val result = LocatorResolver.resolve(tree, spec(resourceId = "com.example:id/target"))
        assertNotNull(result.target)
        assertEquals(n, result.target)
        assertEquals(1, result.candidates)
    }

    @Test
    fun b2_l1_multipleMatches_returnsFirstCandidate() {
        val n1 = node(viewId = "com.example:id/item")
        val n2 = node(viewId = "com.example:id/item")
        val tree = flatTree(listOf(flat(n1, 0), flat(n2, 1)))
        val result = LocatorResolver.resolve(tree, spec(resourceId = "com.example:id/item"))
        assertNotNull(result.target)
        assertEquals(n1, result.target)
        assertEquals(2, result.candidates)
    }

    @Test
    fun b3_l4_textMatch_found() {
        val n = node(text = "Hello")
        val tree = flatTree(listOf(flat(n)))
        val result = LocatorResolver.resolve(tree, spec(strategy = "L4", text = "Hello"))
        assertNotNull(result.target)
        assertEquals(n, result.target)
    }

    @Test
    fun b4_l4_contentDescriptionMatch_found() {
        val n = node(contentDesc = "Hello")
        val tree = flatTree(listOf(flat(n)))
        val result = LocatorResolver.resolve(tree, spec(strategy = "L4", text = "Hello"))
        assertNotNull(result.target)
        assertEquals(n, result.target)
    }

    @Test
    fun b5_l6_path_found() {
        val root = node()
        val child = node()
        val grandchild = node()
        val tree = flatTree(
            listOf(
                flat(root, 0, -1, 0, 0, 0),
                flat(child, 1, 0, 1, 0, 1),
                flat(grandchild, 2, 1, 2, 0, 0),
            )
        )
        val result = LocatorResolver.resolve(tree, spec(strategy = "L6", path = listOf(0, 1, 0)))
        assertNotNull(result.target)
        assertEquals(grandchild, result.target)
    }

    @Test
    fun b6_l6_outOfBounds_notFound() {
        val root = node()
        val tree = flatTree(listOf(flat(root, 0, -1, 0, 0, 0)))
        val result = LocatorResolver.resolve(tree, spec(strategy = "L6", path = listOf(0, 999)))
        assertNull(result.target)
        assertTrue(result.note.isNotEmpty())
    }

    @Test
    fun b7_anyStrategy_noMatch_notFound() {
        val n = node()
        val tree = flatTree(listOf(flat(n)))
        val result = LocatorResolver.resolve(tree, spec(resourceId = "nonexistent.id"))
        assertNull(result.target)
        assertEquals(0, result.candidates)
        assertTrue(result.note.isNotEmpty())
    }

    @Test
    fun b8_climbToExecutable_climbsToInteractiveAncestor() {
        val parent = node(clickable = true)
        val child = node(text = "label", clickable = false)
        val tree = flatTree(
            listOf(
                flat(parent, 0, -1, 0, 0, 0),
                flat(child, 1, 0, 1, 0, 0),
            )
        )
        val result = LocatorResolver.resolve(
            tree,
            spec(strategy = "L4", text = "label", target = "ancestor_clickable")
        )
        assertNotNull(result.target)
        assertEquals(parent, result.target)
        assertEquals(child, result.anchor)
    }
}
