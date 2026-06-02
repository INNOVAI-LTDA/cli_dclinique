"""Decision map grouping helpers."""
from __future__ import annotations

import pandas as pd


def quadrants(summary: pd.DataFrame) -> dict[str, pd.DataFrame]:
    engaged = summary["is_engaged"]
    satisfied = summary["is_satisfied"].fillna(False)
    return {
        "Engajado + Satisfeito": summary[engaged & satisfied],
        "Engajado + Não satisfeito": summary[engaged & ~satisfied],
        "Não engajado + Satisfeito": summary[~engaged & satisfied],
        "Não engajado + Não satisfeito": summary[~engaged & ~satisfied],
    }
