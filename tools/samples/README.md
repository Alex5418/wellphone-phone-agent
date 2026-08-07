# 节点树样本

这些是 B2 / B3 / C2 的结论所依据的**原始 uiautomator dump**，不是临时文件 ——
文档里逐个引用了它们的统计数字，删掉就没法复核结论。

| 文件 | 来源页面 | 用在哪 |
|---|---|---|
| `s.xml` | Settings 首页 | B2 压缩前后对比 |
| `d0.xml` | 主屏完整 dump（557 节点） | B2 大样本 |
| `settings-display.xml` | Settings 显示设置页 | B2 / C2 |
| `chrome-ntp.xml` | Chrome 新标签页（WebView） | C2 可指认率 |
| `compose.xml` | composetest（Compose 无 id） | C2 可指认率 |
| `contacts.xml` `clock1.xml` `clock-alarm.xml` `calendar.xml` `cal5.xml` `notes.xml` `k9.xml` | B3 的 5 个候选 app | B3 节点树体检 |

复核方式：

```bash
python tools/compress_tree.py tools/samples/s.xml            # 压缩输出
python tools/compress_tree.py tools/samples/compose.xml --assess   # 可指认率
```
