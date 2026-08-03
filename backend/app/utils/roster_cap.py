"""Agent 花名册上限（成本闸门三号）。

合并前的低成本是个意外：本体只读文档前 5 万字，一单只出 3-11 个实体。
全文采样修好后花名册涨到 14-17，而每次推理的提示词都随世界规模膨胀
（信息流更肥 + 记忆更多）——动作数差不多，单 token 却翻倍。

刻意重建旧经济学：按连接度（related_edges 数）保留最重要的 N 个实体
作为 Agent。环境变量 MAX_SIM_AGENTS 可调，默认 12（旧意外区间的上沿）。
"""

import os

from .logger import logger


def _cap_from_env() -> int:
    try:
        return int(os.environ.get("MAX_SIM_AGENTS", "12"))
    except ValueError:
        return 12


def cap_roster(entities: list, max_agents: int = None) -> list:
    """Keep the max_agents most-connected entities; under cap = untouched."""
    cap = max_agents if max_agents is not None else _cap_from_env()
    if cap <= 0 or len(entities) <= cap:
        return entities
    ranked = sorted(entities,
                    key=lambda e: len(getattr(e, "related_edges", []) or []),
                    reverse=True)
    kept = ranked[:cap]
    logger.warning(
        f"花名册超上限：{len(entities)} 个实体，按连接度保留 {cap} 个"
        f"（MAX_SIM_AGENTS={cap}；被裁剪的实体仍在图谱中，仅不生成 Agent）"
    )
    return kept
