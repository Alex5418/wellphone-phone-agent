package com.example.phoneagent

import android.view.accessibility.AccessibilityNodeInfo
import org.json.JSONObject

/**
 * locator 解析（HARNESS-SPEC §4.3 的 Android 侧对应实现）。
 *
 * 设计上有一条与旧 LOCATE 广播指令不同的地方：**不用 framework 的 find* API**。
 * 原因是 findAccessibilityNodeInfosByText 的匹配语义（子串、同时匹配 contentDescription）
 * 和返回顺序都不受我们控制，而 Python 侧的唯一性判定与 L5 序号是按 observe 的遍历顺序
 * 算出来的。这里改为在 [Snapshot.flatten] 的同一份扁平列表上做**精确匹配 + 同序筛选**，
 * 两侧语义按定义一致，不靠"实测碰巧对上"。
 *
 * 命中的是 **anchor**（文字/id 所在节点），再按 target 规则换算成真正的**执行节点**。
 */
object LocatorResolver {

    class Resolved(
        val target: AccessibilityNodeInfo?,
        val anchor: AccessibilityNodeInfo?,
        val candidates: Int,
        val note: String,
    )

    class Spec(
        val strategy: String,
        val resourceId: String?,
        val text: String?,
        val contentDesc: String?,
        val cls: String?,
        val index: Int,
        val target: String,
        val path: List<Int>?,
    ) {
        companion object {
            fun from(o: JSONObject): Spec = Spec(
                strategy = o.optString("strategy", "L1"),
                resourceId = o.optStringOrNull("resource_id"),
                text = o.optStringOrNull("text"),
                contentDesc = o.optStringOrNull("content_desc"),
                cls = o.optStringOrNull("cls") ?: o.optStringOrNull("class"),
                index = o.optInt("index", 0),
                target = o.optString("target", "self").ifEmpty { "self" },
                path = o.optJSONArray("path")?.let { arr ->
                    (0 until arr.length()).map { arr.getInt(it) }
                },
            )
        }

        fun describe(): String =
            "$strategy(id=$resourceId text=$text cd=$contentDesc cls=$cls idx=$index target=$target path=$path)"
    }

    fun resolve(tree: Snapshot.FlatTree, spec: Spec): Resolved {
        // ① 按 strategy 收集候选 anchor（保持 flatten 的 DFS 顺序）
        val cands: List<Snapshot.Flat> = when (spec.strategy) {
            "L1" -> tree.nodes.filter { Snapshot.viewId(it.node) == spec.resourceId }
            "L2" -> tree.nodes.filter {
                Snapshot.viewId(it.node) == spec.resourceId && labelMatches(tree, it, spec.text)
            }
            "L3" -> tree.nodes.filter { Snapshot.contentDesc(it.node) == spec.contentDesc }
            "L4", "L5" -> tree.nodes.filter { textUniverseMatch(it.node, spec.text) }
            "L6" -> resolveByPath(tree, spec.path)
            else -> return Resolved(null, null, 0, "UNKNOWN_STRATEGY ${spec.strategy}")
        }
        if (cands.isEmpty()) return Resolved(null, null, 0, "no candidate for ${spec.describe()}")

        // ② L5 取第 index 个（flatten 的 DFS 序即 Python 侧的 idx 序）
        val anchorFlat = if (spec.strategy == "L5") {
            cands.getOrNull(spec.index)
                ?: return Resolved(null, null, cands.size,
                    "index ${spec.index} out of range (${cands.size} candidates)")
        } else {
            cands[0]
        }
        val anchor = anchorFlat.node

        // ③ 应用 target
        var target: AccessibilityNodeInfo? = when {
            spec.target == "self" -> anchor
            spec.target == "ancestor_clickable" -> climbToExecutable(tree, anchorFlat)?.node
            spec.target.startsWith("descendant_class:") -> {
                // 先归位到「容器」再向下找。典型场景：Preference 行里裸露的 Switch ——
                // 行的文字在 TextView 上，Switch 是 TextView 的**兄弟**而非后代，
                // 直接从文字节点向下 BFS 永远找不到它。
                // 所以：锚点不可交互时先爬到最近的可交互祖先（= 整行），再从行里找 class。
                val base = if (Snapshot.isInteractive(anchorFlat.node)) anchorFlat
                           else (climbToExecutable(tree, anchorFlat) ?: anchorFlat)
                findDescendantByClass(base, spec.target.removePrefix("descendant_class:"))
            }
            else -> anchor
        }

        // ④ 兜底：爬不到就用原候选。actionList 未登记某动作 ≠ 该动作不可用（E6 教训 4），
        //    这里返回失败会把「其实能点」的节点判死。
        var note = "ok"
        if (target == null) {
            target = anchor
            note = "target '${spec.target}' unreachable, fell back to anchor"
        }
        return Resolved(target, anchor, cands.size, note)
    }

    /**
     * L4/L5 的查找宇宙 = text 属性 ∪ contentDescription 属性。
     * 这一条来自 C3 实测（findAccessibilityNodeInfosByText 同时匹配两者），
     * Python 侧的唯一性计数也按合并宇宙来 —— 两侧必须同规则，否则 ordinal 会错位。
     */
    private fun textUniverseMatch(n: AccessibilityNodeInfo, want: String?): Boolean {
        if (want == null) return false
        return Snapshot.text(n) == want || Snapshot.contentDesc(n) == want
    }

    /** L2：同 id 多个候选时，用「自身或近邻后代的文字」消歧 */
    private fun labelMatches(tree: Snapshot.FlatTree, f: Snapshot.Flat, want: String?): Boolean {
        if (want == null) return true
        if (textUniverseMatch(f.node, want)) return true
        // 后代 BFS（深度 ≤3，与 Python 侧 compress 的锚点搜索一致）
        for (d in descendants(tree, f, 3)) {
            if (textUniverseMatch(d.node, want)) return true
        }
        return false
    }

    private fun children(tree: Snapshot.FlatTree, f: Snapshot.Flat): List<Snapshot.Flat> =
        tree.nodes.filter { it.parent == f.idx }

    private fun descendants(tree: Snapshot.FlatTree, f: Snapshot.Flat, maxDepth: Int): List<Snapshot.Flat> {
        val out = ArrayList<Snapshot.Flat>()
        var frontier = children(tree, f)
        var d = 1
        while (frontier.isNotEmpty() && d <= maxDepth) {
            out.addAll(frontier)
            frontier = frontier.flatMap { children(tree, it) }
            d++
        }
        return out
    }

    /** 向上找第一个可执行祖先（clickable / long_clickable / scrollable / editable） */
    private fun climbToExecutable(tree: Snapshot.FlatTree, from: Snapshot.Flat): Snapshot.Flat? {
        // 严格向上：anchor 自身是不是可交互无关紧要，target=ancestor_clickable 的语义就是
        // 「文字在子节点、可点在父节点」，要的是 anchor 之上的那个执行节点
        var cur = from
        while (cur.parent >= 0) {
            val p = tree.byIdx(cur.parent) ?: return null
            if (Snapshot.isInteractive(p.node)) return p
            cur = p
        }
        return null
    }

    /** BFS 找第一个 class == X 的后代（Preference 行里的 Switch 就是这么定位的） */
    private fun findDescendantByClass(from: Snapshot.Flat, cls: String): AccessibilityNodeInfo? {
        val queue = ArrayDeque<AccessibilityNodeInfo>()
        queue.addLast(from.node)
        while (queue.isNotEmpty()) {
            val n = queue.removeFirst()
            if (n !== from.node && Snapshot.cls(n) == cls) return n
            for (i in 0 until n.childCount) n.getChild(i)?.let { queue.addLast(it) }
        }
        return null
    }

    /**
     * L6 结构路径：path[0] = 第几棵树（窗口序），其余为逐层 child index。
     * 与 [Snapshot.flatten] 记录的 rootOrdinal / childIndex 同源。
     */
    private fun resolveByPath(tree: Snapshot.FlatTree, path: List<Int>?): List<Snapshot.Flat> {
        if (path.isNullOrEmpty()) return emptyList()
        var cur = tree.nodes.firstOrNull { it.parent < 0 && it.rootOrdinal == path[0] }
            ?: return emptyList()
        for (step in path.drop(1)) {
            cur = tree.nodes.firstOrNull { it.parent == cur.idx && it.childIndex == step }
                ?: return emptyList()
        }
        return listOf(cur)
    }
}

/** org.json 把缺失的键读成字符串 "null"，这里统一收口 */
fun JSONObject.optStringOrNull(key: String): String? {
    if (!has(key) || isNull(key)) return null
    val v = optString(key, "")
    return v.ifEmpty { null }
}
