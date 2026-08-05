package com.example.phoneagent

import android.accessibilityservice.AccessibilityService
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.Rect
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo

class AgentAccessibilityService : AccessibilityService() {

    companion object {
        const val TAG = "PHONEAGENT"
        const val ACTION_DUMP = "com.example.phoneagent.DUMP"
        const val ACTION_CLICK = "com.example.phoneagent.CLICK"

        const val ACTION_CLICK_ID = "com.example.phoneagent.CLICKID"

        const val ACTION_DO = "com.example.phoneagent.DO"
        const val ACTION_DO_RESTORE = "com.example.phoneagent.DORESTORE"
        const val ACTION_FIELD = "com.example.phoneagent.FIELD"
        const val ACT_SCROLL_FORWARD = "SCROLL_FORWARD"
        const val ACT_SCROLL_BACKWARD = "SCROLL_BACKWARD"
        const val ACT_LONG_CLICK = "LONG_CLICK"
        const val ACT_FOCUS = "FOCUS"
        const val ACT_ACCESSIBILITY_FOCUS = "ACCESSIBILITY_FOCUS"
        const val ACT_EXPAND = "EXPAND"
        const val ACT_COLLAPSE = "COLLAPSE"
        const val ACT_SET_TEXT = "SET_TEXT"
    }

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(ctx: Context?, intent: Intent?) {
            when (intent?.action) {
                ACTION_DUMP -> dumpAllWindows()
                ACTION_CLICK -> clickByText(
                    intent.getIntExtra("display", 0),
                    intent.getStringExtra("text") ?: return
                )
                ACTION_CLICK_ID -> clickById(
                    intent.getIntExtra("display", 0),
                    intent.getStringExtra("vid") ?: return
                )
                ACTION_DO -> {
                    Log.i(TAG, "DO received display=${intent.getIntExtra("display", -999)} vid=${intent.getStringExtra("vid")} text=${intent.getStringExtra("text")} act=${intent.getStringExtra("act")} val=${intent.getStringExtra("val")}")
                    doAction(
                        intent.getIntExtra("display", 0),
                        intent.getStringExtra("vid"),
                        intent.getStringExtra("text"),
                        intent.getStringExtra("act") ?: return,
                        intent.getStringExtra("val")
                    )
                }
                ACTION_DO_RESTORE -> doWithRestore(
                    intent.getIntExtra("display", 0),
                    intent.getStringExtra("vid"),
                    intent.getStringExtra("act") ?: "CLICK",
                    intent.getStringExtra("val"),
                    intent.getBooleanExtra("restore", true),
                    intent.getStringExtra("restoreAct") ?: "FOCUS",
                    intent.getIntExtra("delay", 0)
                )
                ACTION_FIELD -> dumpField(intent.getIntExtra("display", 0))
            }
        }
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        Log.i(TAG, "=== service connected ===")
        val filter = IntentFilter().apply {
            addAction(ACTION_DUMP)
            addAction(ACTION_CLICK)
            addAction(ACTION_CLICK_ID)
            addAction(ACTION_DO)
            addAction(ACTION_DO_RESTORE)
            addAction(ACTION_FIELD)
        }
        registerReceiver(receiver, filter, Context.RECEIVER_EXPORTED)
        dumpAllWindows()
    }

    private fun dumpAllWindows() {
        val all = windowsOnAllDisplays
        Log.i(TAG, "########## displays found: ${all.size()} ##########")
        for (i in 0 until all.size()) {
            val displayId = all.keyAt(i)
            val windows = all.valueAt(i)
            Log.i(TAG, ">>> display=$displayId  windows=${windows.size}")
            for (w in windows) {
                val root = w.root
                Log.i(TAG, "    win pkg=${root?.packageName} focused=${w.isFocused} active=${w.isActive}")
                root?.let {
                    val n = countNodes(it)
                    Log.i(TAG, "    nodes=$n")
                    printTree(it, 0, 12)
                }
            }
        }
    }

    private fun countNodes(node: AccessibilityNodeInfo): Int {
        var c = 1
        for (i in 0 until node.childCount) {
            node.getChild(i)?.let { c += countNodes(it) }
        }
        return c
    }

    private fun printTree(node: AccessibilityNodeInfo, depth: Int, maxDepth: Int) {
        if (depth > maxDepth) return
        val pad = "  ".repeat(depth)
        val label = node.text ?: node.contentDescription ?: ""
        val expandable = node.actionList.any { it.id == AccessibilityNodeInfo.ACTION_EXPAND || it.id == AccessibilityNodeInfo.ACTION_COLLAPSE }
        val r = Rect()
        node.getBoundsInScreen(r)
        if (label.isNotEmpty() || node.isClickable || node.isScrollable || node.isLongClickable || node.isFocusable || expandable) {
            Log.i(
                TAG,
                "$pad[${node.className}] '$label' click=${node.isClickable} scroll=${node.isScrollable} " +
                    "long=${node.isLongClickable} focus=${node.isFocusable} focused=${node.isFocused} " +
                    "a11yFocus=${node.isAccessibilityFocused} expand=$expandable " +
                    "id=${node.viewIdResourceName} bounds=$r"
            )
        }
        for (i in 0 until node.childCount) {
            node.getChild(i)?.let { printTree(it, depth + 1, maxDepth) }
        }
    }

    private fun clickByText(displayId: Int, text: String) {
        val all = windowsOnAllDisplays
        for (i in 0 until all.size()) {
            if (all.keyAt(i) != displayId) continue
            for (w in all.valueAt(i)) {
                val root = w.root ?: continue
                val hits = root.findAccessibilityNodeInfosByText(text)
                if (hits.isNullOrEmpty()) continue
                var target: AccessibilityNodeInfo? = hits[0]
                while (target != null && !target.isClickable) target = target.parent
                val ok = target?.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                Log.i(TAG, "CLICK display=$displayId text='$text' result=$ok node=${target?.className}")
                return
            }
        }
        Log.i(TAG, "CLICK display=$displayId text='$text' NOT FOUND")
    }

    private fun clickById(displayId: Int, viewId: String) {
        val all = windowsOnAllDisplays
        for (i in 0 until all.size()) {
            if (all.keyAt(i) != displayId) continue
            for (w in all.valueAt(i)) {
                val root = w.root ?: continue
                val hits = root.findAccessibilityNodeInfosByViewId(viewId)
                if (hits.isNullOrEmpty()) continue
                var target: AccessibilityNodeInfo? = hits[0]
                while (target != null && !target.isClickable) target = target.parent
                val ok = target?.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                Log.i(TAG, "CLICK_ID display=$displayId id='$viewId' result=$ok node=${target?.className}")
                return
            }
        }
        Log.i(TAG, "CLICK_ID display=$displayId id='$viewId' NOT FOUND")
    }

    private fun doAction(displayId: Int, viewId: String?, text: String?, act: String, value: String?) {
        val action: Int = when (act) {
            ACT_SCROLL_FORWARD -> AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
            ACT_SCROLL_BACKWARD -> AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
            ACT_LONG_CLICK -> AccessibilityNodeInfo.ACTION_LONG_CLICK
            ACT_FOCUS -> AccessibilityNodeInfo.ACTION_FOCUS
            ACT_ACCESSIBILITY_FOCUS -> AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS
            ACT_EXPAND -> AccessibilityNodeInfo.ACTION_EXPAND
            ACT_COLLAPSE -> AccessibilityNodeInfo.ACTION_COLLAPSE
            ACT_SET_TEXT -> AccessibilityNodeInfo.ACTION_SET_TEXT
            else -> {
                Log.i(TAG, "DO display=$displayId vid='$viewId' act=$act UNKNOWN ACTION")
                return
            }
        }
        val all = windowsOnAllDisplays
        for (i in 0 until all.size()) {
            if (all.keyAt(i) != displayId) continue
            for (w in all.valueAt(i)) {
                val root = w.root ?: continue
                val hits = if (viewId != null) {
                    root.findAccessibilityNodeInfosByViewId(viewId)
                } else {
                    root.findAccessibilityNodeInfosByText(text ?: return)
                }
                if (hits.isNullOrEmpty()) continue
                var target: AccessibilityNodeInfo? = hits[0]
                while (target != null && !target.actionList.any { it.id == action }) target = target.parent
                val ok = if (action == AccessibilityNodeInfo.ACTION_SET_TEXT) {
                    val args = Bundle().apply {
                        putCharSequence(
                            AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,
                            value ?: "hello"
                        )
                    }
                    target?.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
                } else {
                    target?.performAction(action)
                }
                Log.i(TAG, "DO display=$displayId vid='$viewId' act=$act result=$ok node=${target?.className}")
                return
            }
        }
        Log.i(TAG, "DO display=$displayId vid='$viewId' act=$act NOT FOUND")
    }

    // ---- EXP-FOCUS-RESTORE ----------------------------------------------

    /**
     * 主屏(display 0)当前持有输入焦点的节点。FOCUS_INPUT 是输入焦点，不是 a11y 焦点。
     *
     * 必须跳过 IME 窗口：软键盘弹起后 Gboard 自身也是 display 0 上的一个窗口，
     * 且 findFocus 会在它里面命中按键节点，先到先得会拿到键盘按键而不是用户的输入框。
     * 可编辑节点优先，其余作为兜底。
     */
    private fun findPrimaryInputFocus(): AccessibilityNodeInfo? {
        val all = windowsOnAllDisplays
        var fallback: AccessibilityNodeInfo? = null
        for (i in 0 until all.size()) {
            if (all.keyAt(i) != 0) continue
            for (w in all.valueAt(i)) {
                if (w.type == AccessibilityWindowInfo.TYPE_INPUT_METHOD) continue
                val root = w.root ?: continue
                val f = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT) ?: continue
                Log.i(TAG, "  candidate winType=${w.type} pkg=${root.packageName} " +
                    "node=${f.className} id=${f.viewIdResourceName} editable=${f.isEditable}")
                if (f.isEditable) return f
                if (fallback == null) fallback = f
            }
        }
        return fallback
    }

    /** 按 viewId 找副屏目标，并向上爬到真正支持该动作的节点（沿用 doAction 的做法）。 */
    private fun nodeByVid(displayId: Int, vid: String, action: Int): AccessibilityNodeInfo? {
        val all = windowsOnAllDisplays
        for (i in 0 until all.size()) {
            if (all.keyAt(i) != displayId) continue
            for (w in all.valueAt(i)) {
                val root = w.root ?: continue
                val hits = root.findAccessibilityNodeInfosByViewId(vid)
                if (hits.isNullOrEmpty()) continue
                var target: AccessibilityNodeInfo? = hits[0]
                while (target != null && !target.actionList.any { it.id == action }) target = target.parent
                return target ?: hits[0]
            }
        }
        return null
    }

    /** 把焦点还给 node。restoreAct: FOCUS / CLICK / BOTH。 */
    private fun restoreFocus(node: AccessibilityNodeInfo, restoreAct: String): String {
        val refreshed = node.refresh()   // 快照可能已 stale
        val f = if (restoreAct == "FOCUS" || restoreAct == "BOTH")
            node.performAction(AccessibilityNodeInfo.ACTION_FOCUS) else null
        val c = if (restoreAct == "CLICK" || restoreAct == "BOTH")
            node.performAction(AccessibilityNodeInfo.ACTION_CLICK) else null
        return "refresh=$refreshed focusOk=$f clickOk=$c isFocused=${node.isFocused} " +
            "sel=${node.textSelectionStart}..${node.textSelectionEnd}"
    }

    private fun doWithRestore(
        displayId: Int,
        vid: String?,
        act: String,
        value: String?,
        restore: Boolean,
        restoreAct: String,
        delayMs: Int
    ) {
        // ① 动作前先抓住主屏焦点节点 —— 必须在这里抓，动作后窗口已变，快照会 stale
        val primary = findPrimaryInputFocus()
        Log.i(TAG, "RESTORE primary=${primary?.className} id=${primary?.viewIdResourceName} " +
            "len=${primary?.text?.length} sel=${primary?.textSelectionStart}..${primary?.textSelectionEnd}")

        val action: Int = when (act) {
            "CLICK" -> AccessibilityNodeInfo.ACTION_CLICK
            ACT_SCROLL_FORWARD -> AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
            ACT_SCROLL_BACKWARD -> AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
            ACT_LONG_CLICK -> AccessibilityNodeInfo.ACTION_LONG_CLICK
            ACT_SET_TEXT -> AccessibilityNodeInfo.ACTION_SET_TEXT
            else -> {
                Log.i(TAG, "RESTORE act=$act UNKNOWN ACTION")
                return
            }
        }

        val target = vid?.let { nodeByVid(displayId, it, action) }
        if (target == null) {
            Log.i(TAG, "RESTORE target NOT FOUND display=$displayId vid=$vid")
            return
        }

        // ② 执行副屏动作
        val t0 = SystemClock.elapsedRealtime()
        val ok = if (action == AccessibilityNodeInfo.ACTION_SET_TEXT) {
            val args = Bundle().apply {
                putCharSequence(
                    AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,
                    value ?: "hello"
                )
            }
            target.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
        } else {
            target.performAction(action)
        }
        val t1 = SystemClock.elapsedRealtime()

        if (!restore || primary == null) {
            Log.i(TAG, "RESTORE act=$act ok=$ok restored=SKIPPED(restore=$restore primary=${primary != null}) " +
                "action=${t1 - t0}ms")
            return
        }

        // ③ 归还焦点。delay=0 走同步路径（EXP 原始逻辑）；delay>0 用于排除异步时序干扰
        if (delayMs <= 0) {
            val detail = restoreFocus(primary, restoreAct)
            val t2 = SystemClock.elapsedRealtime()
            Log.i(TAG, "RESTORE act=$act ok=$ok via=$restoreAct delay=0 $detail " +
                "action=${t1 - t0}ms restore=${t2 - t1}ms total=${t2 - t0}ms")
        } else {
            Log.i(TAG, "RESTORE act=$act ok=$ok via=$restoreAct delay=${delayMs}ms action=${t1 - t0}ms (restore pending)")
            Handler(Looper.getMainLooper()).postDelayed({
                val detail = restoreFocus(primary, restoreAct)
                val t2 = SystemClock.elapsedRealtime()
                Log.i(TAG, "RESTORE-DELAYED act=$act via=$restoreAct delay=${delayMs}ms $detail " +
                    "total=${t2 - t0}ms")
            }, delayMs.toLong())
        }
    }

    // ---------------------------------------------------------------------

    /**
     * 主判据计数器。两个必须的选择规则：
     *  - 跳过 IME 窗口，否则会数到软键盘里的节点
     *  - 聚焦节点优先于「文本最长」。Contacts 的 open_search_bar 文本是提示语
     *    "Search contacts"(15 字符)，比用户真正输入的内容还长，纯比长度会选错节点，
     *    而提示语是常量 → Δ 恒为 0 → 得出「一个字没丢」的假结论。
     */
    private fun dumpField(displayId: Int) {
        val all = windowsOnAllDisplays
        var focused: AccessibilityNodeInfo? = null
        var longest: AccessibilityNodeInfo? = null
        var longestLen = -1
        var count = 0
        for (i in 0 until all.size()) {
            if (all.keyAt(i) != displayId) continue
            for (w in all.valueAt(i)) {
                if (w.type == AccessibilityWindowInfo.TYPE_INPUT_METHOD) continue
                val root = w.root ?: continue
                val queue = ArrayDeque<AccessibilityNodeInfo>()
                queue.add(root)
                while (queue.isNotEmpty()) {
                    val n = queue.removeFirst()
                    if (n.isEditable || n.className?.toString()?.contains("EditText") == true) {
                        count++
                        val len = n.text?.length ?: 0
                        Log.i(TAG, "  field cand id=${n.viewIdResourceName} len=$len " +
                            "focused=${n.isFocused} editable=${n.isEditable} text='${n.text}'")
                        if (n.isFocused && focused == null) focused = n
                        if (len > longestLen) { longestLen = len; longest = n }
                    }
                    for (c in 0 until n.childCount) n.getChild(c)?.let { queue.add(it) }
                }
            }
        }
        val best = focused ?: longest
        if (best == null) {
            Log.i(TAG, "FIELD display=$displayId NO EDITTEXT")
            return
        }
        Log.i(TAG, "FIELD display=$displayId id=${best.viewIdResourceName} " +
            "len=${best.text?.length ?: 0} tail='${best.text?.toString()?.takeLast(20)}' " +
            "focused=${best.isFocused} sel=${best.textSelectionStart}..${best.textSelectionEnd} " +
            "pickedBy=${if (focused != null) "FOCUSED" else "LONGEST"} cands=$count")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {}
    override fun onInterrupt() {}
}