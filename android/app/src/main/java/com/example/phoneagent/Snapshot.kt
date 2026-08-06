package com.example.phoneagent

import android.accessibilityservice.AccessibilityService
import android.graphics.Rect
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import java.security.MessageDigest

/**
 * 节点树遍历的唯一入口。
 *
 * **为什么 observe 与 locator 解析必须共用这里的遍历**：
 * locator 的 L5 用「同类候选中的第 index 个」消歧，这个序号是 Python 侧按 observe 返回的
 * idx 顺序算出来的。若解析时换一套遍历顺序（比如直接用 findAccessibilityNodeInfosByText
 * 的返回序），index 就指向别的节点 —— 静默点错，且难查。
 * 因此两条路径都走 [flatten]，窗口顺序都走 [windowsOf]。
 */
object Snapshot {

    /** 与 HARNESS-SPEC §2.2 的深度上限一致；解析侧也用同一个值，否则深层节点在两侧不一致 */
    const val DEPTH_LIMIT = 25

    class Flat(
        val idx: Int,
        val parent: Int,          // -1 = 根
        val depth: Int,
        val node: AccessibilityNodeInfo,
        val rootOrdinal: Int,     // 属于第几棵树（窗口序），L6 路径的第一段
        val childIndex: Int,      // 在父节点中的序号，L6 路径的后续段
    )

    class FlatTree(
        val nodes: List<Flat>,
        val truncated: Boolean,
        val roots: List<AccessibilityNodeInfo>,
    ) {
        fun byIdx(i: Int): Flat? = nodes.getOrNull(i)
    }

    /**
     * 某个 display 上的窗口，**确定性排序**（layer 降序 → id 升序）。
     * 不用 windowsOnAllDisplays 的原始顺序：它没有文档保证，两次调用之间可能变。
     *
     * IME 窗口默认排除 —— E6 教训：findFocus 会在软键盘窗口里命中按键节点，
     * 不排除会把焦点归还打到键盘按键上。
     */
    fun windowsOf(
        svc: AccessibilityService,
        displayId: Int,
        includeIme: Boolean = false,
    ): List<AccessibilityWindowInfo> {
        val all = svc.windowsOnAllDisplays
        for (i in 0 until all.size()) {
            if (all.keyAt(i) != displayId) continue
            return all.valueAt(i)
                .filter { includeIme || it.type != AccessibilityWindowInfo.TYPE_INPUT_METHOD }
                .sortedWith(compareByDescending<AccessibilityWindowInfo> { it.layer }.thenBy { it.id })
        }
        return emptyList()
    }

    fun displayIds(svc: AccessibilityService): List<Int> {
        val all = svc.windowsOnAllDisplays
        return (0 until all.size()).map { all.keyAt(it) }.sorted()
    }

    /** 前序 DFS 展开。子节点按 getChild 的下标顺序（这就是 L6 path 里的 childIndex）。 */
    fun flatten(roots: List<AccessibilityNodeInfo>, depthLimit: Int = DEPTH_LIMIT): FlatTree {
        val out = ArrayList<Flat>()
        var truncated = false
        // 显式栈，避免深树递归爆栈；压栈时反序，保证弹出顺序 = 子节点自然序
        data class Item(val node: AccessibilityNodeInfo, val parent: Int, val depth: Int,
                        val rootOrdinal: Int, val childIndex: Int)
        for ((ro, root) in roots.withIndex()) {
            val stack = ArrayDeque<Item>()
            stack.addLast(Item(root, -1, 0, ro, 0))
            while (stack.isNotEmpty()) {
                val it = stack.removeLast()
                val idx = out.size
                out.add(Flat(idx, it.parent, it.depth, it.node, it.rootOrdinal, it.childIndex))
                if (it.depth >= depthLimit) {
                    if (it.node.childCount > 0) truncated = true
                    continue
                }
                for (c in it.node.childCount - 1 downTo 0) {
                    it.node.getChild(c)?.let { child ->
                        stack.addLast(Item(child, idx, it.depth + 1, it.rootOrdinal, c))
                    }
                }
            }
        }
        return FlatTree(out, truncated, roots)
    }

    fun flattenDisplay(svc: AccessibilityService, displayId: Int): FlatTree {
        val roots = windowsOf(svc, displayId).mapNotNull { it.root }
        return flatten(roots)
    }

    // ---- 节点属性读取（统一空串 -> null，Python 侧不必再判空） ----

    fun text(n: AccessibilityNodeInfo): String? =
        n.text?.toString()?.takeIf { it.isNotEmpty() }

    fun contentDesc(n: AccessibilityNodeInfo): String? =
        n.contentDescription?.toString()?.takeIf { it.isNotEmpty() }

    fun viewId(n: AccessibilityNodeInfo): String? =
        n.viewIdResourceName?.takeIf { it.isNotEmpty() }

    fun cls(n: AccessibilityNodeInfo): String = n.className?.toString() ?: ""

    /**
     * 空 EditText 的 getText() 返回的是 hint 而非空串（已知坑）。
     * 判「有没有真的填了字」必须看 isShowingHintText，不能只看 text 非空。
     */
    fun effectiveText(n: AccessibilityNodeInfo): String? {
        if (n.isShowingHintText) return null
        return text(n)
    }

    fun isInteractive(n: AccessibilityNodeInfo): Boolean =
        n.isClickable || n.isLongClickable || n.isScrollable || n.isEditable

    /**
     * checked 状态。新 SDK 把 isChecked 标为废弃（改用 getChecked() 的三态），
     * 但后者是 API 36 才有的，本项目 minSdk=30 —— 在支持的最低版本上只有这一个选择。
     * 收在这一处：tree_hash 与 post_state 都依赖它，两边必须永远同一个取法。
     */
    @Suppress("DEPRECATION")
    fun isChecked(n: AccessibilityNodeInfo): Boolean = n.isChecked

    fun boundsOf(n: AccessibilityNodeInfo): Rect {
        val r = Rect()
        n.getBoundsInScreen(r)
        return r
    }

    /** actionList 的字符串化。⚠ 未登记 ≠ 不可用，Python 侧不得据此丢弃节点。 */
    fun actionNames(n: AccessibilityNodeInfo): List<String> = n.actionList.mapNotNull { a ->
        when (a.id) {
            AccessibilityNodeInfo.ACTION_CLICK -> "ACTION_CLICK"
            AccessibilityNodeInfo.ACTION_LONG_CLICK -> "ACTION_LONG_CLICK"
            AccessibilityNodeInfo.ACTION_FOCUS -> "ACTION_FOCUS"
            AccessibilityNodeInfo.ACTION_CLEAR_FOCUS -> "ACTION_CLEAR_FOCUS"
            AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS -> "ACTION_ACCESSIBILITY_FOCUS"
            AccessibilityNodeInfo.ACTION_SCROLL_FORWARD -> "ACTION_SCROLL_FORWARD"
            AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD -> "ACTION_SCROLL_BACKWARD"
            AccessibilityNodeInfo.ACTION_SET_TEXT -> "ACTION_SET_TEXT"
            AccessibilityNodeInfo.ACTION_EXPAND -> "ACTION_EXPAND"
            AccessibilityNodeInfo.ACTION_COLLAPSE -> "ACTION_COLLAPSE"
            AccessibilityNodeInfo.ACTION_SELECT -> "ACTION_SELECT"
            AccessibilityNodeInfo.ACTION_PASTE -> "ACTION_PASTE"
            else -> null
        }
    }

    private const val SEP = '\u001F'   // 字段分隔（unit separator，正文里不会出现）
    private const val REC = '\u001E'   // 记录分隔（record separator）

    /**
     * tree_hash：对 (class, resource_id, text, content_desc, clickable, checked) 按 idx 顺序
     * 拼接后取 SHA1 前 16 位。Python 侧会用同样规则复算一遍做交叉校验 ——
     * 「不信任工具返回值」同样适用于 hash 本身。
     */
    fun treeHash(tree: FlatTree): String {
        val md = MessageDigest.getInstance("SHA-1")
        val sb = StringBuilder()
        for (f in tree.nodes) {
            val n = f.node
            sb.setLength(0)
            sb.append(cls(n)).append(SEP)
                .append(viewId(n) ?: "").append(SEP)
                .append(text(n) ?: "").append(SEP)
                .append(contentDesc(n) ?: "").append(SEP)
                .append(if (n.isClickable) '1' else '0')
                .append(if (isChecked(n)) '1' else '0')
                .append(REC)
            md.update(sb.toString().toByteArray(Charsets.UTF_8))
        }
        return md.digest().joinToString("") { "%02x".format(it) }.substring(0, 16)
    }
}
