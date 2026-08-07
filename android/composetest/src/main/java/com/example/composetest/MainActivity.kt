package com.example.composetest

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

/**
 * C2 替代样本：极简 Compose 写信界面（3 个输入框 + 1 个发送按钮），
 * 用于验证「无 resource-id 的 Compose 语义节点能否被分层定位器唯一指认」。
 * 控件故意不使用 Modifier.testTag —— 不注入任何额外语义，保持与真实
 * Compose app（如 K-9 21.x）一致的默认语义树形态。
 */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                ComposeMailScreen()
            }
        }
    }
}

@Composable
private fun ComposeMailScreen() {
    var to by rememberSaveable { mutableStateOf("") }
    var subject by rememberSaveable { mutableStateOf("") }
    var body by rememberSaveable { mutableStateOf("") }
    var sent by rememberSaveable { mutableStateOf(false) }

    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text("Compose Mail", style = MaterialTheme.typography.headlineSmall)
        OutlinedTextField(
            value = to,
            onValueChange = { to = it },
            label = { Text("To") },
            modifier = Modifier.fillMaxWidth()
        )
        OutlinedTextField(
            value = subject,
            onValueChange = { subject = it },
            label = { Text("Subject") },
            modifier = Modifier.fillMaxWidth()
        )
        OutlinedTextField(
            value = body,
            onValueChange = { body = it },
            label = { Text("Body") },
            modifier = Modifier.fillMaxWidth().weight(1f)
        )
        Button(
            onClick = { sent = true },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Send")
        }
        if (sent) {
            Text("Message sent")
        }
    }
}
