"""节点树重建与本地 hash 复算。

hash 在 Python 侧独立复算一遍：设备返回的 tree_hash 与本地复算不一致，说明
「返回的节点数组」和「设备用来算 hash 的那棵树」不是同一份 —— 这正是
「工具会撒谎」的第 2 种形态（参数被静默忽略）。不一致时打标记，交给 observation 报告。
"""

from __future__ import annotations

import hashlib

from .models import Node, Tree

SEP = "\x1f"
REC = "\x1e"


def local_tree_hash(nodes: list[Node]) -> str:
    """必须与 Snapshot.treeHash（Kotlin）逐字节同规则。"""
    md = hashlib.sha1()
    for n in nodes:
        rec = (
            f"{n.cls}{SEP}"
            f"{n.resource_id or ''}{SEP}"
            f"{n.text or ''}{SEP}"
            f"{n.content_desc or ''}{SEP}"
            f"{'1' if n.clickable else '0'}"
            f"{'1' if n.checked else '0'}"
            f"{REC}"
        )
        md.update(rec.encode("utf-8"))
    return md.hexdigest()[:16]


def build_tree(data: dict) -> Tree:
    nodes = [Node.from_json(d) for d in data.get("nodes", [])]
    # 降级响应会重编号，这里校验 idx 连续 —— 断掉就说明协议实现有 bug，早死早好
    for i, n in enumerate(nodes):
        if n.idx != i:
            raise ValueError(f"node idx not contiguous at {i}: got {n.idx}")
        if n.parent is not None and not (0 <= n.parent < i):
            raise ValueError(f"node {i} has forward/invalid parent {n.parent}")
    device_hash = data.get("tree_hash") or ""
    tree = Tree(
        display=data.get("display", -1),
        pkg=data.get("pkg"),
        activity=data.get("activity"),
        tree_hash=device_hash,
        nodes=nodes,
        window_count=int(data.get("window_count") or 1),
        truncated=bool(data.get("truncated")),
        reduced=bool(data.get("reduced")),
    )
    if not tree.reduced:
        # reduced 响应丢了节点，hash 是按完整树算的，跳过比对
        tree.hash_mismatch = bool(device_hash) and local_tree_hash(nodes) != device_hash
    return tree


def label_of(n: Node) -> str | None:
    """节点自身的文字来源：text 优先，content_desc 兜底。"""
    if n.text and n.text.strip() and not n.hint_text:
        return n.text
    if n.content_desc and n.content_desc.strip():
        return n.content_desc
    return None


def find_text_universe(nodes: list[Node]) -> dict[str, list[int]]:
    """findByText 的查找宇宙 = text 属性 ∪ content_desc 属性。

    C3 实测：findAccessibilityNodeInfosByText 同时匹配两者。设备侧的 LocatorResolver
    也按这个合并宇宙做精确匹配，两侧同规则，L5 的 index 才不会错位。
    命中顺序 = observe 的 idx 顺序（DFS）。
    """
    uni: dict[str, list[int]] = {}
    for n in nodes:
        for v in (n.text, n.content_desc):
            if v and v.strip():
                uni.setdefault(v, []).append(n.idx)
    return uni


def count_by_id(nodes: list[Node]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for n in nodes:
        if n.resource_id:
            out.setdefault(n.resource_id, []).append(n.idx)
    return out


def count_by_desc(nodes: list[Node]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for n in nodes:
        if n.content_desc and n.content_desc.strip():
            out.setdefault(n.content_desc, []).append(n.idx)
    return out


def path_from_root(tree: Tree, idx: int) -> list[int]:
    """L6 结构路径：[根序号, 子序号, ...]，与 Kotlin 侧 rootOrdinal/childIndex 同源。"""
    chain: list[int] = []
    cur: int | None = idx
    while cur is not None:
        parent = tree.by_idx(cur).parent
        if parent is None:
            roots = tree.roots()
            chain.insert(0, roots.index(cur))
            break
        chain.insert(0, tree.children(parent).index(cur))
        cur = parent
    return chain


def screen_rect(tree: Tree) -> tuple[int, int, int, int] | None:
    """以最大的根节点 bounds 作为可视区（用于判断条目是否在屏幕内）。"""
    best = None
    for r in tree.roots():
        b = tree.by_idx(r).bounds
        if not b:
            continue
        area = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
        if best is None or area > best[0]:
            best = (area, b)
    return best[1] if best else None


def onscreen(b: tuple[int, int, int, int] | None,
             screen: tuple[int, int, int, int] | None) -> bool:
    if b is None or screen is None:
        return True
    return b[2] > screen[0] and b[3] > screen[1] and b[0] < screen[2] and b[1] < screen[3]
