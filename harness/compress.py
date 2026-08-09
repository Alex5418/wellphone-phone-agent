"""锚点合并 + locator 生成（HARNESS-SPEC §4.2 / §4.3）。

产出 Item 列表 —— 喂给 LLM 的最小单位。LLM 只看到短 ID 与语义，
resource-id / 坐标 / 类名一概不出现在它面前（ARCHITECTURE §4）。

两条容易被压成一条、又必须分开的东西：
    [LinearLayout] clickable id=null        ← 点它 = 进子页面
        [TextView] 'Dark theme'
        [Switch]   clickable checkable      ← 点它 = 原地翻转
实测同一句文字对应两种完全不同的行为，所以这里**两条都保留**，靠 kind 区分。
"""

from __future__ import annotations

from . import config
from .models import Item, Locator, Node, Tree
from .tree import (count_by_desc, count_by_id, find_text_universe, label_of,
                   onscreen, path_from_root, screen_rect)

_SWITCH_HINTS = ("Switch", "CheckBox", "ToggleButton", "RadioButton", "CheckedTextView")


# ---------------------------------------------------------------- 锚点

def _own_label(n: Node) -> str | None:
    return label_of(n)


def _descendant_anchor(tree: Tree, target: Node, candidate_ids: set[int]) -> int | None:
    """在后代里 BFS 找第一个文字节点（深度 ≤ ANCHOR_LOOKAHEAD）。

    跳过「以另一个候选为根的子树」：否则一个 RecyclerView 会把第一行的文字认领成
    自己的名字，而那行本身也是候选 —— 两条条目同名，LLM 无从区分。
    先找 text，再找 content_desc（顺序来自 SPEC §4.2 第 2 步）。
    """
    for want_text in (True, False):
        frontier, depth = tree.children(target.idx), 1
        while frontier and depth <= config.ANCHOR_LOOKAHEAD:
            nxt = []
            for i in frontier:
                n = tree.by_idx(i)
                if i in candidate_ids:
                    continue          # 别人的地盘，连同其子树一起跳过
                v = (n.text if not n.hint_text else None) if want_text else n.content_desc
                if v and v.strip():
                    return i
                nxt.extend(tree.children(i))
            frontier, depth = nxt, depth + 1
    return None


def _inherited_anchor(tree: Tree, target: Node, labels: dict[int, int]) -> int | None:
    """没有自己的文字、也没有文字后代时，借最近的**有标签的候选祖先**的锚点。

    这就是裸 Switch 的处理方式：它自己什么文字都没有，但用户看到的是整行的标题。
    借来之后 target 规则记为 descendant_class，执行侧从容器往下找回这个 Switch。
    """
    for a in tree.ancestors(target.idx):
        if a in labels:
            return labels[a]
    return None


# ---------------------------------------------------------------- state / kind

def _kind_of(n: Node) -> str:
    cls = n.cls or ""
    if any(h in cls for h in _SWITCH_HINTS) or (n.checkable and not n.scrollable):
        return "switch"
    if n.editable or "EditText" in cls:
        return "input"
    if n.scrollable:
        return "list"
    if n.clickable or n.long_clickable:
        return "button"
    return "other"


def _summary_of(tree: Tree, target: Node, anchor_idx: int) -> str | None:
    """Preference 行的副标题：resource_id 以 ':id/summary' 结尾的节点。

    先找锚点的兄弟（标准 Preference 布局），再退回到目标的后代。
    """
    anchor = tree.by_idx(anchor_idx)
    sibs = tree.children(anchor.parent) if anchor.parent is not None else []
    for i in sibs:
        n = tree.by_idx(i)
        if n.resource_id and n.resource_id.endswith(":id/summary") and n.text:
            return n.text
    for i in tree.descendants(target.idx, max_depth=config.ANCHOR_LOOKAHEAD):
        n = tree.by_idx(i)
        if n.resource_id and n.resource_id.endswith(":id/summary") and n.text:
            return n.text
    return None


def _state_of(tree: Tree, target: Node, anchor_idx: int, kind: str) -> str | None:
    if target.checkable:
        return "On" if target.checked else "Off"
    if kind == "input":
        return target.effective_text or "(空)"
    if kind == "list":
        # 滚动容器没有自己的"当前值"。不设这条的话它会把列表里第一行的
        # summary 认领成自己的状态，观测里就多出一条假信息
        return None
    return _summary_of(tree, target, anchor_idx)


# ---------------------------------------------------------------- locator

def device_label(tree: Tree, n: Node) -> str | None:
    """执行侧「看得见」的文字：节点自身，或其 ≤3 层后代里的第一个文字。

    必须与 Kotlin 侧 LocatorResolver.labelMatches 同规则 —— L2 靠它在同 id 组里消歧，
    两侧规则不一致时会出现「Python 觉得能唯一确定、设备侧筛出 0 个候选」。
    注意这里**不跳过其他候选的子树**（设备侧也不跳），与 _descendant_anchor 有意不同。
    """
    own = _own_label(n)
    if own:
        return own
    frontier, depth = tree.children(n.idx), 1
    while frontier and depth <= config.ANCHOR_LOOKAHEAD:
        for i in frontier:
            v = _own_label(tree.by_idx(i))
            if v:
                return v
        frontier = [c for i in frontier for c in tree.children(i)]
        depth += 1
    return None


def build_locator(tree: Tree, target: Node, hook: Node, rule: str, label: str | None,
                  universes: tuple[dict, dict, dict]) -> Locator:
    """按 L1→L6 顺序生成 locator。

    L1/L2 判在**执行节点**上（能直接指自己就别绕锚点，少一次爬取就少一处失败点）；
    L3/L4/L5 判在 **hook**（锚点）上，配合 rule 描述"找到锚点之后怎么走到执行节点"。
    唯一性一律在**当前这棵树**内判定 —— 同一个 id 在列表里出现 20 次是常态，
    不作任何全局假设。
    """
    by_id, by_desc, by_text = universes

    # L1：执行节点自己的 id 在全树唯一 —— 最稳，直接指自己
    if target.resource_id and len(by_id.get(target.resource_id, ())) == 1:
        return Locator(strategy="L1", resource_id=target.resource_id,
                       cls=target.cls, target="self")

    # L2：id 重复，但同 id 组内「执行侧看得见的文字」唯一
    #     裸 Switch 这类节点走不到这里：它自己和后代都没有文字，
    #     device_label 返回 None，交给下面的锚点路径处理
    if target.resource_id and label:
        group = by_id.get(target.resource_id, [])
        same = [i for i in group if device_label(tree, tree.by_idx(i)) == label]
        if same == [target.idx]:
            return Locator(strategy="L2", resource_id=target.resource_id, text=label,
                           cls=target.cls, target="self")

    # hook 自己有唯一 id 时，用它当抓手比用文字稳
    if hook.idx != target.idx and hook.resource_id \
            and len(by_id.get(hook.resource_id, ())) == 1:
        return Locator(strategy="L1", resource_id=hook.resource_id,
                       cls=hook.cls, target=rule)

    hook_label = _own_label(hook)

    # L3：content_desc 在 desc 宇宙内唯一
    if hook.content_desc and len(by_desc.get(hook.content_desc, ())) == 1:
        return Locator(strategy="L3", content_desc=hook.content_desc,
                       cls=hook.cls, target=rule)

    # L4 / L5：findByText 宇宙 = text ∪ content_desc（C3 实测，执行侧同规则）
    if hook_label:
        hits = by_text.get(hook_label, [])
        if len(hits) == 1:
            return Locator(strategy="L4", text=hook_label, cls=hook.cls, target=rule)
        if hook.idx in hits:
            return Locator(strategy="L5", text=hook_label, cls=hook.cls,
                           index=hits.index(hook.idx), target=rule)

    # L6：结构路径，直指执行节点本身
    return Locator(strategy="L6", cls=target.cls, target="self",
                   path=path_from_root(tree, target.idx))


# ---------------------------------------------------------------- 主流程

def compress(tree: Tree, max_items: int = config.MAX_ITEMS_SHOWN) -> list[Item]:
    nodes = tree.nodes
    universes = (count_by_id(nodes), count_by_desc(nodes), find_text_universe(nodes))
    screen = screen_rect(tree)

    # ① 候选集
    cands = [n for n in nodes if n.interactive and n.visible and n.enabled]
    cand_ids = {n.idx for n in cands}

    # ② 锚点：自身文字 → 后代文字 → 借祖先候选的锚点
    anchor_of: dict[int, int] = {}          # 候选 idx -> 锚点 idx
    inherited: set[int] = set()
    for n in cands:
        if _own_label(n) is not None:
            anchor_of[n.idx] = n.idx
    for n in cands:
        if n.idx in anchor_of:
            continue
        a = _descendant_anchor(tree, n, cand_ids)
        if a is not None:
            anchor_of[n.idx] = a
    for n in cands:                          # 第三遍才借祖先，保证祖先的锚点已定
        if n.idx in anchor_of:
            continue
        a = _inherited_anchor(tree, n, anchor_of)
        if a is not None:
            anchor_of[n.idx] = a
            inherited.add(n.idx)

    # ③ 去重：共享同一锚点且 **kind 相同** 的，只留一条。
    #    kind 不同的一律都留 —— 整行(button) 与 开关(switch) 行为完全不同，
    #    合成一条就等于让 LLM 在两种结果之间抛硬币。
    #
    #    同 kind 时留谁，两条规则按顺序：
    #
    #    (a) **锚点的主人优先于借用者。** 自己就带着那段文字的节点，才是这段文字
    #        描述的东西；借用祖先/后代文字的节点只是它的一部分。
    #        依据（`runs/2026-08-09T18-36-02`）：Gmail 会话列表里整行 ViewGroup 自带
    #        contentDescription（"Unread, , , Wang, Yiduo, …"），而行内的联系人头像
    #        ImageView 没有文字、借用了整行的锚点 —— 两者 kind 都是 button。
    #        旧规则只按 depth 取最内层，于是**整行被头像挤掉**：
    #        点整行是"打开邮件"，点头像是"勾选" —— agent 反复勾选/取消，
    #        一次都没能打开那封邮件，最后判 impossible。
    #        这与 §4 记的 Settings 那个坑同源：**同一段文字，两种完全不同的行为。**
    #
    #    (b) 双方都是借用者时才比 depth，留最内层。Settings 的整行就走这条 ——
    #        它的文字在不可交互的 TextView 上，行与外层包装都是借用者，
    #        此时最内层才是真正能执行的那个。
    kinds = {n.idx: _kind_of(n) for n in cands}
    keep: dict[tuple[int, str], Node] = {}
    no_anchor: list[Node] = []
    for n in cands:
        a = anchor_of.get(n.idx)
        if a is None:
            no_anchor.append(n)
            continue
        key = (a, kinds[n.idx])
        prev = keep.get(key)
        if prev is None:
            keep[key] = n
            continue
        n_owns, prev_owns = (a == n.idx), (a == prev.idx)
        if n_owns != prev_owns:
            keep[key] = n if n_owns else prev      # (a) 主人赢
        elif n.depth > prev.depth:
            keep[key] = n                          # (b) 同为借用者，留最内层

    chosen = sorted([*keep.values(), *no_anchor], key=lambda n: n.idx)

    # ④ 组装 Item
    items: list[Item] = []
    for n in chosen:
        a_idx = anchor_of.get(n.idx, n.idx)
        anchor = tree.by_idx(a_idx)
        kind = kinds[n.idx]

        if a_idx == n.idx:
            hook, rule = n, "self"
        elif n.idx in inherited:
            # 锚点在祖先那边：执行侧从容器往下按 class 找回本节点
            hook, rule = anchor, f"descendant_class:{n.cls}"
        else:
            hook, rule = anchor, "ancestor_clickable"

        label = _own_label(anchor) or ""
        loc = build_locator(tree, n, hook, rule, label or None, universes)
        if not label and kind == "input" and n.text:
            label = n.text          # 空输入框的 hint 就是它的名字（"搜索设置"）
        if kind == "list" and (not label or a_idx != n.idx):
            # 滚动容器不能直接借后代的文字当名字。真机上 RecyclerView 会认领第一个
            # 分组标题，于是显示成「[2] Brightness | list」—— 读起来像个亮度控件，
            # 而它其实是"这一整块可滚动区域"。
            # 但也不能一律叫「（可滚动区域）」：一页上常有两个（外层 ScrollView +
            # 内层 RecyclerView），同名两条 LLM 没法选，首次真机跑就选错了外层那个。
            # 折中：前缀点明它是区域，再带上区域里第一条文字用于区分。
            label = f"（可滚动区域：{label}…）" if label else "（可滚动区域）"
        items.append(Item(
            sid=len(items),
            label=label,
            kind=kind,
            state=_state_of(tree, n, a_idx, kind),
            locator=loc,
            anchor_idx=a_idx,
            target_idx=n.idx,
            onscreen=onscreen(n.bounds, screen),
            checked=n.checked if n.checkable else None,
            text_value=n.effective_text if kind == "input" else None,
            res_id=n.resource_id,
        ))
    return items


def trim_for_display(items: list[Item], limit: int = config.MAX_ITEMS_SHOWN
                     ) -> tuple[list[Item], int]:
    """呈现上限（SPEC §6）：other → 无 state 的 text → 屏幕外条目，按序裁剪。

    只裁**呈现**，不裁 items 本身 —— sid 与 locator 仍然可用，
    LLM 滚动后下一轮会重新看到。
    """
    if len(items) <= limit:
        return items, 0
    keep = list(items)
    for pred in (lambda i: i.kind == "other",
                 lambda i: i.kind == "text" and not i.state,
                 lambda i: not i.onscreen):
        if len(keep) <= limit:
            break
        keep = [i for i in keep if not pred(i)] or keep
    dropped = len(items) - len(keep)
    return keep[:limit], dropped + max(0, len(keep) - limit)
