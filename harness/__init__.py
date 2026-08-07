"""PC 侧 harness。

依赖方向严格自下而上：
    config / models  ← 不依赖任何本地模块
    tree             ← models
    compress         ← models, tree
    verify           ← models
    observe          ← models, compress
    transport        ← models, config
    planner          ← models
    loop             ← 以上全部
    cli              ← loop

护栏（不可配置）：焦点归还、动作后自检、每轮状态自检、归还失败必须上报。
策略（可配置）：动作选择、绕路、礼貌等级、完成判定 —— 都在 planner 里。
"""

__all__ = ["config", "models", "transport", "tree", "compress", "verify",
           "observe", "planner", "loop", "trace", "adbutil"]
