#!/usr/bin/env python3
"""scout_dump.py — 对 uiautomator dump XML 做 B3 体检统计（离线，无依赖）

用法: python scout_dump.py <dump.xml>
输出: 总节点数 / class 分布 top10 / 规范 resource-id 数+样例 / clickable / EditText / WebView·Flutter·RN 特征
"""
import re
import sys
import xml.etree.ElementTree as ET

CANONICAL_ID = re.compile(r"^[a-z][a-z0-9_.]*:[a-z][a-z0-9_.]*:/[a-zA-Z0-9_.]+$|^[a-z][a-z0-9_.]*:id/[a-zA-Z0-9_.]+$")


def main():
    path = sys.argv[1]
    root = ET.parse(path).getroot()
    nodes = list(root.iter("node"))
    total = len(nodes)

    classes = {}
    ids = []
    clickable = 0
    edittext = 0
    webview = 0
    flutter = 0
    rn = 0
    for n in nodes:
        a = n.attrib
        cls = a.get("class", "")
        classes[cls] = classes.get(cls, 0) + 1
        rid = a.get("resource-id") or ""
        if rid:
            ids.append(rid)
        if a.get("clickable") == "true":
            clickable += 1
        if "EditText" in cls or a.get("editable") == "true":
            edittext += 1
        if "WebView" in cls or "webview" in cls.lower():
            webview += 1
        if "FlutterView" in cls or "flutter" in cls.lower():
            flutter += 1
        if "React" in cls or "com.facebook.react" in cls:
            rn += 1

    print(f"## {path}")
    print(f"total nodes: {total}")
    print("class distribution top10:")
    for cls, cnt in sorted(classes.items(), key=lambda kv: -kv[1])[:10]:
        pct = 100.0 * cnt / total if total else 0
        print(f"  {cnt:4d} ({pct:5.1f}%)  {cls}")
    canonical = [i for i in ids if CANONICAL_ID.match(i)]
    print(f"resource-id total: {len(ids)}  canonical(包名:id/xxx): {len(canonical)}")
    if canonical:
        print("  sample canonical ids:")
        for i in list(dict.fromkeys(canonical))[:5]:
            print(f"    {i}")
    print(f"clickable=true: {clickable}")
    print(f"EditText/editable: {edittext}")
    print(f"WebView: {webview}  Flutter: {flutter}  ReactNative: {rn}")


if __name__ == "__main__":
    main()
