package com.example.phoneagent

import android.accessibilityservice.AccessibilityService
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.Rect
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

class AgentAccessibilityService : AccessibilityService() {

    companion object {
        const val TAG = "PHONEAGENT"
        const val ACTION_DUMP = "com.example.phoneagent.DUMP"
        const val ACTION_CLICK = "com.example.phoneagent.CLICK"

        const val ACTION_CLICK_ID = "com.example.phoneagent.CLICKID"

        const val ACTION_DO = "com.example.phoneagent.DO"
        const val ACTION_FIELD = "com.example.phoneagent.FIELD"
        const val ACT_SCROLL_FORWARD = "SCROLL_FORWARD"
        const val ACT_SCROLL_BACKWARD = "SCROLL_BACKWARD"
        const val ACT_LONG_CLICK = "LONG_CLICK"
        const val ACT_FOCUS = "FOCUS"
        const val ACT_ACCESSIBILITY_FOCUS = "ACCESSIBILITY_FOCUS"
        const val ACT_EXPAND = "EXPAND"
        const val ACT_COLLAPSE = "COLLAPSE"
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
                    Log.i(TAG, "DO received display=${intent.getIntExtra("display", -999)} vid=${intent.getStringExtra("vid")} text=${intent.getStringExtra("text")} act=${intent.getStringExtra("act")}")
                    doAction(
                        intent.getIntExtra("display", 0),
                        intent.getStringExtra("vid"),
                        intent.getStringExtra("text"),
                        intent.getStringExtra("act") ?: return
                    )
                }
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

    private fun doAction(displayId: Int, viewId: String?, text: String?, act: String) {
        val action: Int = when (act) {
            ACT_SCROLL_FORWARD -> AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
            ACT_SCROLL_BACKWARD -> AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
            ACT_LONG_CLICK -> AccessibilityNodeInfo.ACTION_LONG_CLICK
            ACT_FOCUS -> AccessibilityNodeInfo.ACTION_FOCUS
            ACT_ACCESSIBILITY_FOCUS -> AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS
            ACT_EXPAND -> AccessibilityNodeInfo.ACTION_EXPAND
            ACT_COLLAPSE -> AccessibilityNodeInfo.ACTION_COLLAPSE
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
                val ok = target?.performAction(action)
                Log.i(TAG, "DO display=$displayId vid='$viewId' act=$act result=$ok node=${target?.className}")
                return
            }
        }
        Log.i(TAG, "DO display=$displayId vid='$viewId' act=$act NOT FOUND")
    }

    private fun dumpField(displayId: Int) {
        val all = windowsOnAllDisplays
        for (i in 0 until all.size()) {
            if (all.keyAt(i) != displayId) continue
            for (w in all.valueAt(i)) {
                val root = w.root ?: continue
                var best: AccessibilityNodeInfo? = null
                var bestLen = -1
                val queue = ArrayDeque<AccessibilityNodeInfo>()
                queue.add(root)
                while (queue.isNotEmpty()) {
                    val n = queue.removeFirst()
                    val t = n.text?.toString()
                    if (n.className?.toString()?.contains("EditText") == true) {
                        val len = t?.length ?: 0
                        if (len > bestLen) { bestLen = len; best = n }
                    }
                    for (c in 0 until n.childCount) n.getChild(c)?.let { queue.add(it) }
                }
                if (best != null) {
                    Log.i(TAG, "FIELD display=$displayId id=${best.viewIdResourceName} len=$bestLen tail='${best.text?.toString()?.takeLast(20)}' focused=${best.isFocused}")
                    return
                }
            }
        }
        Log.i(TAG, "FIELD display=$displayId NO EDITTEXT")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {}
    override fun onInterrupt() {}
}