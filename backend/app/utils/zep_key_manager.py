"""多 Zep 账号密钥的故障转移管理。

按顺序持有多个密钥；当前密钥用尽/被限流时 rotate() 切换到下一个；全部用尽抛出。
用于免费额度耗尽后自动切换到备用账号。
Spec: docs/specs/2026-07-24-zep-burn-reduction-spec.md
"""


class AllKeysExhausted(Exception):
    """所有 Zep 密钥都已用尽。"""


class ZepKeyManager:
    def __init__(self, keys):
        seen = set()
        cleaned = []
        for k in keys or []:
            k = (k or "").strip()
            if k and k not in seen:
                seen.add(k)
                cleaned.append(k)
        if not cleaned:
            raise ValueError("ZepKeyManager requires at least one non-empty key")
        self.keys = cleaned
        self._i = 0

    def current(self) -> str:
        return self.keys[self._i]

    def rotate(self) -> str:
        """切换到下一个密钥并返回；已是最后一个则抛 AllKeysExhausted。"""
        if self._i + 1 >= len(self.keys):
            raise AllKeysExhausted(f"all {len(self.keys)} Zep keys exhausted")
        self._i += 1
        return self.current()


def keys_from_env(env) -> list:
    """从环境变量收集有序密钥：ZEP_API_KEY(, ZEP_API_KEY_2, ZEP_API_KEY_3 …)。

    主键 ZEP_API_KEY 也支持逗号分隔多个。
    """
    out = []
    primary = env.get("ZEP_API_KEY", "")
    out.extend(p.strip() for p in primary.split(",") if p.strip())
    i = 2
    while True:
        v = env.get(f"ZEP_API_KEY_{i}")
        if not v:
            break
        out.append(v.strip())
        i += 1
    return out
