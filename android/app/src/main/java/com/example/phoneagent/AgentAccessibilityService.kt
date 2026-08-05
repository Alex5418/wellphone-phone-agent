package com.example.phoneagent

import android.accessibilityservice.AccessibilityService
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

class AgentAccessibilityService : AccessibilityService() {

    companion object {
        const val TAG = "PHONEAGENT"
        const val ACTION_DUMP = "com.example.phoneagent.DUMP"
        const val ACTION_CLICK = "com.example.phoneagent.CLICK"
    }

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(ctx: Context?, intent: Intent?) {
            when (intent?.action) {
                ACTION_DUMP -> dumpAllWindows()
                ACTION_CLICK -> clickByText(
                    intent.getIntExtra("display", 0),
                    intent.getStringExtra("text") ?: return
                )
            }
        }
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        Log.i(TAG, "=== service connected ===")
        val filter = IntentFilter().apply {
            addAction(ACTION_DUMP)
            addAction(ACTION_CLICK)
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
        if (label.isNotEmpty() || node.isClickable) {
            Log.i(TAG, "$pad[${node.className}] '$label' click=${node.isClickable} id=${node.viewIdResourceName}")
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

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {}
    override fun onInterrupt() {}
}