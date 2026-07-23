"""历史记录排序：按 created_at 倒序（最新在前）。

无日期或空日期的记录排在最后。返回新列表，不修改输入。
"""


def sort_by_created_desc(items):
    """Return items sorted newest-first by created_at; blanks sink to bottom."""
    # ("" sorts below any real ISO timestamp under reverse=True, so blank/missing
    # dates naturally end up last)
    return sorted(items, key=lambda r: (r.get("created_at") or ""), reverse=True)
