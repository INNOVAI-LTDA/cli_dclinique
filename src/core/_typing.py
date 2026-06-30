"""Shared type aliases for ``src.core``.

All annotations use ``from __future__ import annotations`` so the underlying
types (e.g., ``pandas.DataFrame``) are NOT imported at module load time. This
keeps the cold-start cost of ``import src.core`` to a bare minimum — important
because the MAP's lazy-loading pattern (``app.py``) imports the data layer
inside ``get_data``, but core types should be cheap to reference.
"""
from __future__ import annotations

import pandas as pd

#: Shape returned by ``src.data_layer.load_all()``: table_name -> DataFrame.
DataDict = dict[str, "pd.DataFrame"]
