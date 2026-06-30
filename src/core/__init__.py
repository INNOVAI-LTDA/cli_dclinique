"""Core domain types and repositories for the MAP v2 model.

See ``docs/data_model.md`` for the full design and ``docs/caminho_b_plano.md``
for the implementation plan. This package is the translation layer between the
v1 schema (11 tables) and the v2 model (4 entities + associations).

Phase 0: skeleton (this file + ``_typing.py``).
Phase 1: ``types.py`` (6 dataclasses), ``repos.py`` (6 load functions),
         ``mapping.py`` (v1 row → v2 helpers). All read-only.
Phase 2: ``frequency.py`` (4 pure functions + ``PERIOD_DAYS``).
Phase 3: ``alerts.py`` (THRESHOLDS + ``detect_frequency_alerts``) +
         ``persistence.py`` (``save_frequency_alerts`` idempotente via
         ``data_layer.append_row``).
Phase 4: ``attendance_rate`` consumida em ``src/pages/mapa_decisao.py``
         como 3a dimensao visual (5a classe "Sem comparecimento"). Sem
         mudanca na API do core; bump para v0.4.0 reflete a adocao
         na camada de pagina.
"""
from __future__ import annotations

from src.core import alerts, frequency, mapping, persistence, repos, types
from src.core.alerts import (
    THRESHOLDS,
    Thresholds,
    detect_frequency_alerts,
)
from src.core.frequency import (
    ATTENDED_STATUS,
    PERIOD_DAYS,
    actual_sessions,
    attendance_rate,
    expected_sessions,
    max_consecutive_missed,
)
from src.core.persistence import save_frequency_alerts
from src.core.repos import (
    load_client_deliverables,
    load_client_sessions,
    load_clients,
    load_deliverables,
    load_organizations,
    load_users,
)
from src.core.types import (
    Client,
    ClientDeliverable,
    ClientSession,
    Deliverable,
    Organization,
    User,
)

__version__ = "0.4.0"

__all__ = [
    "__version__",
    # Repositories (load functions)
    "load_organizations",
    "load_users",
    "load_deliverables",
    "load_clients",
    "load_client_deliverables",
    "load_client_sessions",
    # Domain types
    "Organization",
    "User",
    "Deliverable",
    "Client",
    "ClientDeliverable",
    "ClientSession",
    # Frequency (Phase 2)
    "PERIOD_DAYS",
    "ATTENDED_STATUS",
    "expected_sessions",
    "actual_sessions",
    "attendance_rate",
    "max_consecutive_missed",
    # Alerts + Persistence (Phase 3)
    "Thresholds",
    "THRESHOLDS",
    "detect_frequency_alerts",
    "save_frequency_alerts",
    # Submodules
    "alerts",
    "frequency",
    "mapping",
    "persistence",
    "repos",
    "types",
]
