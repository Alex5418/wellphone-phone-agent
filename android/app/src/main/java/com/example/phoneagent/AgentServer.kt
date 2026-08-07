package com.example.phoneagent

import android.net.LocalServerSocket
import android.net.LocalSocket
import android.util.Log
import org.json.JSONObject
import java.io.BufferedReader
import java.io.BufferedWriter
import java.io.InputStreamReader
import java.io.OutputStreamWriter

/**
 * LocalServerSocket 通道（HARNESS-SPEC §1）。
 *
 * 为什么不继续用 am broadcast + logcat：单向、无请求-响应配对、结构化数据要解析日志文本，
 * 而且 logcat 缓冲区会截断长内容 —— 完整节点树轻易超限。这是必须换传输层的直接原因。
 *
 * PC 侧：adb forward tcp:8760 localabstract:phoneagent
 * 协议：一行 JSON 请求 → 一行 JSON 响应 → 关闭。**短连接**，服务端不持有任何会话状态。
 */
class AgentServer(
    private val commands: CommandHandler,
    private val socketName: String = SOCKET_NAME,
) {
    companion object {
        const val SOCKET_NAME = "phoneagent"
        private const val TAG = AgentAccessibilityService.TAG
        private const val MAX_REQUEST_BYTES = 1 shl 20
    }

    @Volatile private var running = false
    private var server: LocalServerSocket? = null
    private var thread: Thread? = null

    fun start() {
        if (running) return
        running = true
        thread = Thread({ acceptLoop() }, "agent-server").apply {
            isDaemon = true
            start()
        }
    }

    fun stop() {
        running = false
        try {
            server?.close()
        } catch (t: Throwable) {
            Log.w(TAG, "server close failed: ${t.message}")
        }
        server = null
        thread = null
    }

    private fun acceptLoop() {
        try {
            server = LocalServerSocket(socketName)
        } catch (t: Throwable) {
            // 已知坑：改完代码没在设置里关掉再打开无障碍服务时，旧实例还占着这个名字。
            // 这里必须响亮报错，否则表现为"PC 连得上但跑的是旧逻辑"，极难查。
            Log.e(TAG, "!!! bind localabstract:$socketName FAILED (旧服务实例还活着？" +
                "去无障碍设置里关掉再打开): ${t.message}")
            running = false
            return
        }
        Log.i(TAG, "=== agent server listening on localabstract:$socketName ===")
        while (running) {
            var client: LocalSocket? = null
            try {
                client = server?.accept() ?: break
                serve(client)
            } catch (t: Throwable) {
                if (running) Log.w(TAG, "accept/serve error: ${t.javaClass.simpleName} ${t.message}")
            } finally {
                try { client?.close() } catch (_: Throwable) {}
            }
        }
        Log.i(TAG, "=== agent server stopped ===")
    }

    private fun serve(client: LocalSocket) {
        val reader = BufferedReader(InputStreamReader(client.inputStream, Charsets.UTF_8))
        val writer = BufferedWriter(OutputStreamWriter(client.outputStream, Charsets.UTF_8))
        val line = reader.readLine() ?: return
        if (line.length > MAX_REQUEST_BYTES) {
            writer.write(errorLine("", "BAD_JSON", "request too large"))
            writer.flush()
            return
        }

        var reqId = ""
        val response: String = try {
            val req = JSONObject(line)
            reqId = req.optString("req_id", "")
            val cmd = req.optString("cmd", "")
            if (cmd.isEmpty()) throw CommandError("BAD_ARGS", "missing 'cmd'")
            val args = req.optJSONObject("args") ?: JSONObject()
            val t0 = System.currentTimeMillis()
            val data = commands.handle(cmd, args)
            val ms = System.currentTimeMillis() - t0
            Log.i(TAG, "cmd=$cmd req=$reqId ok ${ms}ms")
            JSONObject().put("req_id", reqId).put("ok", true).put("data", data).toString()
        } catch (e: CommandError) {
            Log.w(TAG, "cmd failed req=$reqId ${e.code}: ${e.message}")
            errorLine(reqId, e.code, e.message).trimEnd('\n')
        } catch (t: Throwable) {
            Log.e(TAG, "cmd crashed req=$reqId", t)
            errorLine(reqId, "INTERNAL", "${t.javaClass.simpleName}: ${t.message}").trimEnd('\n')
        }

        writer.write(response)
        writer.write("\n")
        writer.flush()
        try { client.shutdownOutput() } catch (_: Throwable) {}
    }

    private fun errorLine(reqId: String, code: String, msg: String?): String =
        JSONObject()
            .put("req_id", reqId)
            .put("ok", false)
            .put("error", JSONObject().put("code", code).put("msg", msg ?: ""))
            .toString() + "\n"
}
