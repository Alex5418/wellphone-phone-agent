package com.example.phoneagent

import android.accessibilityservice.AccessibilityService
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

class CommandError(val code: String, override val message: String) : Exception(message)

interface CommandHandler {
    /** @return 响应的 data 对象；失败抛 [CommandError] */
    fun handle(cmd: String, args: JSONObject): JSONObject
}

/**
 * HARNESS-SPEC §2 的命令实现。
 *
 * 全部在**主线程**上执行（socket 线程通过 [onMain] 编组过来）：
 * a11y 的节点操作跨线程虽然多数时候能跑，但 performAction 的分发与窗口回调都在主线程，
 * 混线程会让"归还是否在动作之后发生"这种时序问题变得无法归因。
 * 单次操作超过 [OP_TIMEOUT_MS] 主动返回 TIMEOUT，不阻塞整条通道。
 */
class AgentCommands(private val svc: AgentAccessibilityService) : CommandHandler {

    companion object {
        const val TAG = AgentAccessibilityService.TAG
        const val OP_TIMEOUT_MS = 5000L
        const val MAX_RESPONSE_BYTES = 512 * 1024
        const val PRIMARY_DISPLAY = 0

        /**
         * 归还时重扫主屏树的节点预算。超过就退回 findFocus 兜底。
         * 这段代码在打扰窗口之内，宁可少查一点也不能把用户的打字断出感知。
         */
        const val PRIMARY_SCAN_NODE_LIMIT = 200
    }

    private val main = Handler(Looper.getMainLooper())

    override fun handle(cmd: String, args: JSONObject): JSONObject = onMain {
        when (cmd) {
            "ping" -> JSONObject().put("pong", true).put("uptime_ms", SystemClock.elapsedRealtime())
            "state" -> cmdState()
            "observe" -> cmdObserve(args.reqInt("display"))
            "probe" -> cmdProbe(args.reqInt("display"), args.reqObj("locator"))
            "act" -> cmdAct(args)
            else -> throw CommandError("UNKNOWN_CMD", "unknown cmd '$cmd'")
        }
    }

    // ---------------------------------------------------------------- 线程编组

    private fun <T> onMain(block: () -> T): T {
        if (Looper.myLooper() == Looper.getMainLooper()) return block()
        val latch = CountDownLatch(1)
        var result: T? = null
        var thrown: Throwable? = null
        main.post {
            try {
                result = block()
            } catch (t: Throwable) {
                thrown = t
            } finally {
                latch.countDown()
            }
        }
        if (!latch.await(OP_TIMEOUT_MS, TimeUnit.MILLISECONDS)) {
            throw CommandError("TIMEOUT", "operation exceeded ${OP_TIMEOUT_MS}ms on main thread")
        }
        thrown?.let { throw it }
        @Suppress("UNCHECKED_CAST")
        return result as T
    }

    // ---------------------------------------------------------------- state

    private fun cmdState(): JSONObject {
        val displays = JSONArray()
        // 三值：true 有 IME / false 没有 / null 连 display 0 的窗口都读不到，无从判断。
        // 读不到就报 false 等于告诉 PC 侧"用户没在打字"—— 那是把仪表的失败
        // 说成了被测对象的状态，是这套 harness 里反复出现的同一类错。
        var imePresent: Boolean? = null
        var imePkg: String? = null

        for (id in Snapshot.displayIds(svc)) {
            val wins = JSONArray()
            val windows = Snapshot.windowsOf(svc, id, includeIme = true)
            // 能枚举到窗口 = 有资格判断有没有 IME；枚举不到才是 null
            if (id == PRIMARY_DISPLAY && windows.isNotEmpty() && imePresent == null) {
                imePresent = false
            }
            for (w in windows) {
                val pkg = w.root?.packageName?.toString()
                if (w.type == AccessibilityWindowInfo.TYPE_INPUT_METHOD) {
                    if (id == PRIMARY_DISPLAY) {
                        imePresent = true
                        imePkg = pkg
                    }
                }
                wins.put(JSONObject()
                    .put("pkg", pkg ?: JSONObject.NULL)
                    // ⚠ isFocused 是 per-display 语义，两块屏可同时为 true。
                    // 这里原样上报，判断留给 PC 侧，不在这里做"全局焦点"的错误推断。
                    .put("focused", w.isFocused)
                    .put("active", w.isActive)
                    .put("type", w.type)
                    .put("layer", w.layer)
                    .put("id", w.id))
            }
            displays.put(JSONObject()
                .put("id", id)
                .put("windows", wins)
                .put("activity", svc.activityOf(id) ?: JSONObject.NULL))
        }

        val pf = findPrimaryInputFocus()
        val primary = if (pf == null) JSONObject.NULL else JSONObject()
            .put("display", PRIMARY_DISPLAY)
            .put("pkg", pf.packageName?.toString() ?: JSONObject.NULL)
            .put("node_class", Snapshot.cls(pf))
            .put("resource_id", Snapshot.viewId(pf) ?: JSONObject.NULL)
            .put("editable", pf.isEditable)
            .put("text_len", pf.text?.length ?: 0)

        return JSONObject()
            .put("displays", displays)
            .put("primary_focus", primary)
            .put("ime_present", imePresent ?: JSONObject.NULL)
            .put("ime_pkg", imePkg ?: JSONObject.NULL)
    }

    // ---------------------------------------------------------------- observe

    private fun cmdObserve(displayId: Int): JSONObject {
        val wins = Snapshot.windowsOf(svc, displayId)
        if (wins.isEmpty()) throw CommandError("NO_DISPLAY", "display $displayId has no window")
        val tree = Snapshot.flattenDisplay(svc, displayId)
        if (tree.nodes.isEmpty()) throw CommandError("NO_DISPLAY", "display $displayId has no node")

        val full = renderObserve(displayId, tree, withBounds = true, interactiveOnly = false)
        val bytes = full.toString().toByteArray(Charsets.UTF_8).size
        if (bytes <= MAX_RESPONSE_BYTES) return full

        // 超限降级一次：丢 bounds 与不可交互的纯布局节点（无文字、无 id、不可交互）
        Log.w(TAG, "observe display=$displayId ${bytes}B over limit, retrying reduced")
        return renderObserve(displayId, tree, withBounds = false, interactiveOnly = true)
            .put("reduced", true)
    }

    private fun renderObserve(
        displayId: Int,
        tree: Snapshot.FlatTree,
        withBounds: Boolean,
        interactiveOnly: Boolean,
    ): JSONObject {
        val arr = JSONArray()
        // 降级模式下会丢节点，idx 必须重编号并同步 parent，否则 Python 侧重建的树是错的
        val remap = HashMap<Int, Int>()
        for (f in tree.nodes) {
            val n = f.node
            if (interactiveOnly && !keepWhenReduced(n)) continue
            val newIdx = arr.length()
            remap[f.idx] = newIdx
            var p: Int? = null
            var cur = f.parent
            while (cur >= 0) {
                val mapped = remap[cur]
                if (mapped != null) { p = mapped; break }
                cur = tree.byIdx(cur)?.parent ?: -1
            }
            arr.put(nodeJson(f, newIdx, p, withBounds))
        }
        return JSONObject()
            .put("display", displayId)
            .put("pkg", tree.roots.firstOrNull()?.packageName?.toString() ?: JSONObject.NULL)
            .put("activity", svc.activityOf(displayId) ?: JSONObject.NULL)
            .put("window_count", tree.roots.size)
            .put("tree_hash", Snapshot.treeHash(tree))
            .put("truncated", tree.truncated)
            .put("nodes", arr)
    }

    private fun keepWhenReduced(n: AccessibilityNodeInfo): Boolean =
        Snapshot.isInteractive(n) || Snapshot.text(n) != null ||
            Snapshot.contentDesc(n) != null || n.isCheckable

    private fun nodeJson(f: Snapshot.Flat, idx: Int, parent: Int?, withBounds: Boolean): JSONObject {
        val n = f.node
        val o = JSONObject()
            .put("idx", idx)
            .put("parent", parent ?: JSONObject.NULL)
            .put("depth", f.depth)
            .put("class", Snapshot.cls(n))
            .put("resource_id", Snapshot.viewId(n) ?: JSONObject.NULL)
            .put("text", Snapshot.text(n) ?: JSONObject.NULL)
            .put("content_desc", Snapshot.contentDesc(n) ?: JSONObject.NULL)
            .put("clickable", n.isClickable)
            .put("long_clickable", n.isLongClickable)
            .put("scrollable", n.isScrollable)
            .put("editable", n.isEditable)
            .put("checkable", n.isCheckable)
            .put("checked", Snapshot.isChecked(n))
            .put("focused", n.isFocused)
            .put("enabled", n.isEnabled)
            .put("visible", n.isVisibleToUser)
            // 空 EditText 的 text 是 hint（已知坑），显式带出来供 Python 侧判"是否真的填了字"
            .put("hint_text", n.isShowingHintText)
            .put("actions", JSONArray(Snapshot.actionNames(n)))
        if (withBounds) {
            val r = Snapshot.boundsOf(n)
            o.put("bounds", JSONArray(listOf(r.left, r.top, r.right, r.bottom)))
        }
        return o
    }

    // ---------------------------------------------------------------- probe

    private fun cmdProbe(displayId: Int, locator: JSONObject): JSONObject {
        val tree = Snapshot.flattenDisplay(svc, displayId)
        val r = LocatorResolver.resolve(tree, LocatorResolver.Spec.from(locator))
        return nodeState(r)
    }

    private fun nodeState(r: LocatorResolver.Resolved): JSONObject {
        val n = r.target
            ?: return JSONObject().put("found", false).put("candidates", r.candidates)
                .put("note", r.note)
        return JSONObject()
            .put("found", true)
            .put("candidates", r.candidates)
            .put("note", r.note)
            .put("class", Snapshot.cls(n))
            .put("resource_id", Snapshot.viewId(n) ?: JSONObject.NULL)
            .put("text", Snapshot.effectiveText(n) ?: JSONObject.NULL)
            .put("raw_text", Snapshot.text(n) ?: JSONObject.NULL)
            .put("content_desc", Snapshot.contentDesc(n) ?: JSONObject.NULL)
            .put("checkable", n.isCheckable)
            .put("checked", Snapshot.isChecked(n))
            .put("enabled", n.isEnabled)
            .put("focused", n.isFocused)
            .put("selected", n.isSelected)
    }

    // ---------------------------------------------------------------- act

    /** 主屏焦点节点的**定位信息**（不是节点对象）—— 动作后据此重新解析 */
    private class FocusDescriptor(
        val pkg: String?,
        val resourceId: String?,
        val cls: String,
        val editable: Boolean,
        val windowId: Int,
    ) {
        fun toJson(): JSONObject = JSONObject()
            .put("pkg", pkg ?: JSONObject.NULL)
            .put("resource_id", resourceId ?: JSONObject.NULL)
            .put("class", cls)
            .put("editable", editable)
            .put("window_id", windowId)
    }

    /**
     * 执行顺序严格按 HARNESS-SPEC §2.3，**不可调换**。
     * 第 2 步记描述符、第 6 步重解析是整个护栏的核心：动作可能触发 Activity 重建，
     * 动作前抓的 AccessibilityNodeInfo 快照会 stale（refresh 返回 false），
     * 拿死快照去 performAction 等于没归还。
     */
    private fun cmdAct(args: JSONObject): JSONObject {
        val displayId = args.reqInt("display")
        val actionName = args.optString("action", "CLICK").uppercase()
        val value = args.optStringOrNull("value")
        val restore = args.optBoolean("restore", true)
        val verifyRead = args.optBoolean("verify_read", true)

        val actionId = actionIdOf(actionName)
        // BACK 走 performGlobalAction，没有目标节点 —— locator 可以缺席。
        // 不特判的话它会卡在下面的"解析失败就不执行"上，表现为"BACK 永远不生效"。
        val isGlobal = actionName == "BACK"
        val locator = if (isGlobal) args.optJSONObject("locator") else args.reqObj("locator")

        // ① 解析目标。失败直接返回 found=false，不执行任何动作
        var spec: LocatorResolver.Spec? = null
        var target: AccessibilityNodeInfo? = null
        val resolvedJson = JSONObject()
        if (locator != null) {
            val tree = Snapshot.flattenDisplay(svc, displayId)
            spec = LocatorResolver.Spec.from(locator)
            val resolved = LocatorResolver.resolve(tree, spec)
            target = resolved.target
            resolvedJson.put("found", target != null)
                .put("candidates", resolved.candidates)
                .put("note", resolved.note)
                .put("strategy", spec.strategy)
            if (target != null) {
                resolvedJson.put("class", Snapshot.cls(target))
                    .put("resource_id", Snapshot.viewId(target) ?: JSONObject.NULL)
                    .put("anchor_class",
                        resolved.anchor?.let { Snapshot.cls(it) } ?: JSONObject.NULL)
            }
        } else {
            resolvedJson.put("found", true).put("candidates", 0)
                .put("note", "global action, no locator").put("strategy", "-")
        }
        if (target == null && !isGlobal) {
            return JSONObject()
                .put("resolved", resolvedJson)
                .put("action_ok", false)
                .put("restore", JSONObject().put("attempted", false).put("reason", "target_not_found"))
                .put("post_state", JSONObject().put("found", false))
                .put("window_after", windowInfo(displayId))
                .put("timing", JSONObject().put("action_ms", 0).put("restore_ms", 0).put("total_ms", 0))
        }

        // ② 记录主屏焦点的定位信息（不是节点对象）
        val pre = findPrimaryInputFocus()
        val desc = pre?.let {
            FocusDescriptor(
                pkg = it.packageName?.toString(),
                resourceId = Snapshot.viewId(it),
                cls = Snapshot.cls(it),
                editable = it.isEditable,
                windowId = it.windowId,
            )
        }
        val holderBefore = focusedPkgOnPrimary()

        // ③④⑤ 执行动作
        val t0 = SystemClock.elapsedRealtime()
        val actionOk = perform(target, actionId, actionName, value)
        val t1 = SystemClock.elapsedRealtime()

        // ⑥⑦⑧ 归还 + 校验 + 至多重试一次
        //
        // ⚠ 计时必须把「打扰窗口」和「校验开销」分开。
        // 焦点真正不在主屏的时间只到 doRestore 返回为止；之后的 focusedPkgOnPrimary()
        // 是遍历窗口做校验，用户早已能继续打字。把校验算进 restore_ms 会让头条数字
        // 被自己的仪表拖大，还没法和 E6 的纯 ACTION_FOCUS 耗时对比。
        val restoreJson = JSONObject()
        var t2 = t1
        if (!restore) {
            restoreJson.put("attempted", false).put("reason", "restore=false")
        } else if (desc == null) {
            // 主屏本来就没有输入焦点持有者 —— 没有东西可还，不是失败
            restoreJson.put("attempted", false).put("reason", "no_primary_focus")
        } else {
            var focusMs = 0L                       // 累加纯归还耗时，不含中间的校验读取
            val fs0 = SystemClock.elapsedRealtime()
            var focusResult = doRestore(desc)
            focusMs += SystemClock.elapsedRealtime() - fs0

            var holderAfter = focusedPkgOnPrimary()
            var retried = false
            // 只在**确实读到了持有者、且确实不对**时才重试。
            // 读不到就重试等于凭空把打扰窗口翻倍 —— 首次真机跑就是这样：display 0 上
            // 没有窗口自报 focused/active，holder 恒为 null，于是每一步都白retry 一次。
            if (holderAfter != null && holderAfter != desc.pkg) {
                retried = true
                val fs1 = SystemClock.elapsedRealtime()
                focusResult = doRestore(desc)
                focusMs += SystemClock.elapsedRealtime() - fs1
                holderAfter = focusedPkgOnPrimary()
            }
            t2 = SystemClock.elapsedRealtime()
            restoreJson.put("attempted", true)
                // ⚠ 归还成功与否以 holder_after 为准，不以 performAction 的返回值为准：
                // 对已聚焦节点发 ACTION_FOCUS 返回 false 是正常的（E6）。
                // 读不到持有者时报 null（UNKNOWN）而不是 false —— 没有证据说明失败，
                // 报 false 是在制造假警报。真正的判定交给 PC 侧的 dumpsys 交叉校验。
                .put("ok", if (holderAfter == null) JSONObject.NULL
                           else (holderAfter == desc.pkg))
                .put("ok_unknown_reason",
                    if (holderAfter != null) JSONObject.NULL
                    else "display 0 上没有窗口自报 focused/active，a11y 侧无法判定持有者")
                .put("retried", retried)
                // focus_ms: 真正的打扰窗口（重解析 + ACTION_FOCUS），与 E6 的 10–15ms 可比
                // verify_ms: 校验窗口持有者的开销，发生在打扰窗口之外
                .put("focus_ms", focusMs.toInt())
                .put("verify_ms", (t2 - t1 - focusMs).toInt())
                .put("total_ms", (t2 - t1).toInt())
                .put("holder_before", holderBefore ?: JSONObject.NULL)
                .put("holder_after", holderAfter ?: JSONObject.NULL)
                .put("expect_pkg", desc.pkg ?: JSONObject.NULL)
                .put("focus_action_result", focusResult.first)
                .put("node_refound", focusResult.second)
                // 最后一次归还的耗时拆分（重试时是第二次那一趟）
                .put("last_resolve_ms", lastResolveMs.toInt())
                .put("last_focus_call_ms", lastFocusCallMs.toInt())
                .put("descriptor", desc.toJson())
        }

        // ⑩ 独立重读目标节点（不复用动作前的快照）
        val postState = if (!verifyRead || spec == null) {
            JSONObject().put("found", false).put("skipped", true)
        } else {
            val tree2 = Snapshot.flattenDisplay(svc, displayId)
            nodeState(LocatorResolver.resolve(tree2, spec))
        }
        val t3 = SystemClock.elapsedRealtime()

        return JSONObject()
            .put("resolved", resolvedJson)
            .put("action_ok", actionOk)
            .put("restore", restoreJson)
            .put("post_state", postState)
            .put("window_after", windowInfo(displayId))
            .put("timing", JSONObject()
                .put("action_ms", (t1 - t0).toInt())
                // 打扰窗口 = 动作 + 归还，不含任何校验读取。这才是要上报的那个数字。
                .put("disturb_ms", (t1 - t0).toInt() + restoreJson.optInt("focus_ms", 0))
                .put("restore_focus_ms", restoreJson.optInt("focus_ms", 0))
                .put("restore_total_ms", (t2 - t1).toInt())
                .put("total_ms", (t3 - t0).toInt()))
    }

    private fun actionIdOf(name: String): Int = when (name) {
        "CLICK" -> AccessibilityNodeInfo.ACTION_CLICK
        "LONG_CLICK" -> AccessibilityNodeInfo.ACTION_LONG_CLICK
        "SET_TEXT" -> AccessibilityNodeInfo.ACTION_SET_TEXT
        "SCROLL_FORWARD" -> AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
        "SCROLL_BACKWARD" -> AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
        "FOCUS" -> AccessibilityNodeInfo.ACTION_FOCUS
        "BACK" -> -1   // 走 performGlobalAction
        else -> throw CommandError("BAD_ARGS", "unsupported action '$name'")
    }

    private fun perform(
        target: AccessibilityNodeInfo?,
        actionId: Int,
        name: String,
        value: String?,
    ): Boolean = when {
        // ⚠ BACK 作用于「当前有焦点的 display」，跨屏语义未验证。
        // 先实现并如实上报，不假装它落在 args.display 上。
        name == "BACK" -> svc.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK)
        target == null -> false
        actionId == AccessibilityNodeInfo.ACTION_SET_TEXT -> {
            val b = Bundle().apply {
                putCharSequence(
                    AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, value ?: "")
            }
            target.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, b)
        }
        else -> target.performAction(actionId)
    }

    /**
     * 归还：用描述符**重新解析**主屏节点，再发 ACTION_FOCUS。
     * @return (performAction 的返回值, 是否重新找到了节点)
     */
    /** 上一次 doRestore 的耗时拆分：重解析 vs ACTION_FOCUS 分发 */
    private var lastResolveMs = 0L
    private var lastFocusCallMs = 0L

    private fun doRestore(desc: FocusDescriptor): Pair<Boolean, Boolean> {
        // 拆开量：实测主题切换那一步打扰窗口是 2526ms（滚动只有 12ms），
        // 得知道这 2.5 秒是耗在"重新找到主屏节点"还是"把焦点发过去"上 ——
        // 前者也许还能优化，后者是 Activity 重建期间的平台行为，只能如实上报。
        val r0 = SystemClock.elapsedRealtime()
        val node = reResolvePrimary(desc)
        lastResolveMs = SystemClock.elapsedRealtime() - r0
        if (node == null) {
            lastFocusCallMs = 0
            return Pair(false, false)
        }
        // ACTION_FOCUS 零 UI 副作用、不移动光标；抢焦点发生在动作分发路径上，
        // 与该动作是否"生效"无关 —— 这正是它适合做归还原语的原因（E6）
        val f0 = SystemClock.elapsedRealtime()
        val ok = node.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
        lastFocusCallMs = SystemClock.elapsedRealtime() - f0
        return Pair(ok, true)
    }

    private fun reResolvePrimary(desc: FocusDescriptor): AccessibilityNodeInfo? {
        val wins = Snapshot.windowsOf(svc, PRIMARY_DISPLAY)   // 已排除 IME
        val ordered = wins.sortedByDescending { it.id == desc.windowId }
        for (w in ordered) {
            val root = w.root ?: continue
            if (desc.pkg != null && root.packageName?.toString() != desc.pkg) continue
            // ① 有 id 就按 id 找，优先仍标记 focused 的那个（view 焦点通常没丢，丢的是 window 焦点）
            if (desc.resourceId != null) {
                val hits = root.findAccessibilityNodeInfosByViewId(desc.resourceId)
                if (!hits.isNullOrEmpty()) {
                    return hits.firstOrNull { it.isFocused } ?: hits[0]
                }
            }
            // ② 无 id：按 class + editable 在树里找，同样优先 focused。
            //    ⚠ 这段跑在打扰窗口之内，必须限量：超过 PRIMARY_SCAN_NODE_LIMIT
            //    直接放弃扫描，走 ③ 的 findFocus 兜底 —— 便宜且几乎总能命中，
            //    因为 view 焦点从未丢失，丢的只是 window 焦点（E6）。
            val flat = Snapshot.flattenCapped(root, PRIMARY_SCAN_NODE_LIMIT)
            if (flat != null) {
                val byClass = flat.nodes.filter {
                    Snapshot.cls(it.node) == desc.cls && it.node.isEditable == desc.editable
                }
                if (byClass.isNotEmpty()) {
                    return (byClass.firstOrNull { it.node.isFocused } ?: byClass[0]).node
                }
            }
            // ③ 兜底：该窗口当前的输入焦点节点
            root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)?.let { return it }
        }
        return null
    }

    /**
     * display 0 上"看起来"持有焦点的窗口包名。
     *
     * ⚠ 这是 **per-display** 判据，不是全局 mCurrentFocus。a11y 侧拿不到 dumpsys，
     * 真正的全局校验由 PC 侧用 `dumpsys window` 交叉验证（harness/adbutil.py）——
     * 刻意走另一条链路，避免"用产生结果的同一条链路去验证结果"。
     */
    private fun focusedPkgOnPrimary(): String? {
        val wins = Snapshot.windowsOf(svc, PRIMARY_DISPLAY)
        val w = wins.firstOrNull { it.isFocused } ?: wins.firstOrNull { it.isActive } ?: return null
        return w.root?.packageName?.toString()
    }

    private fun windowInfo(displayId: Int): JSONObject {
        val wins = Snapshot.windowsOf(svc, displayId)
        return JSONObject()
            .put("display", displayId)
            .put("pkg", wins.firstOrNull()?.root?.packageName?.toString() ?: JSONObject.NULL)
            .put("activity", svc.activityOf(displayId) ?: JSONObject.NULL)
            .put("window_count", wins.size)
    }

    /**
     * 主屏输入焦点节点。必须排除 IME 窗口 —— 否则 findFocus 会命中软键盘里的按键，
     * 归还就打在键盘按键上，进而得出"跨屏焦点不联动"的假结论（E6）。
     * 可编辑节点优先，其余作兜底。
     */
    private fun findPrimaryInputFocus(): AccessibilityNodeInfo? {
        var fallback: AccessibilityNodeInfo? = null
        for (w in Snapshot.windowsOf(svc, PRIMARY_DISPLAY)) {
            val root = w.root ?: continue
            val f = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT) ?: continue
            if (f.isEditable) return f
            if (fallback == null) fallback = f
        }
        return fallback
    }

    // ---------------------------------------------------------------- 参数读取

    private fun JSONObject.reqInt(key: String): Int {
        if (!has(key)) throw CommandError("BAD_ARGS", "missing arg '$key'")
        return optInt(key, Int.MIN_VALUE).also {
            if (it == Int.MIN_VALUE) throw CommandError("BAD_ARGS", "arg '$key' must be int")
        }
    }

    private fun JSONObject.reqObj(key: String): JSONObject =
        optJSONObject(key) ?: throw CommandError("BAD_ARGS", "missing arg '$key'")
}
