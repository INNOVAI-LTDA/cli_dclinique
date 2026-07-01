"""Derive ``periodicity_days`` from a ``frequency_type`` label.

MVP Jornada Clinica, Fase 2 (ver ``docs/mvp_plano.md`` §Fase 2).

Este modulo traduz o rotulo canonico de frequencia que o parser / wizard
produz (ex.: ``"Semanal"``, ``"semanal"``, ``"Quinzenal"``, ``"Diário"``)
para o inteiro ``periodicity_days`` que a Fase 4 (regra rolante -- ver
memory ``[[mvp-jornada-clinica-2026-06-30]]``) usa para calcular
``expected_date = last_session + periodicity_days``.

Decisao de design: ``dose única`` -> ``None`` (sentinela, NAO ``0``).
Licão Caminho B Fase 6: zero e' marcador sentinela problematico (caller
pode somar ``0`` sem perceber). ``None`` força tratamento explicito.

Cobre as 9 opcoes do dropdown do wizard (ver
``tests/test_pdf_frequency.py::test_period_days_covers_all_frequency_options``):

  ``dose única``     -> ``None``
  ``Diário``         -> ``1``
  ``a cada 5 dias``  -> ``5``
  ``Semanal``        -> ``7``
  ``a cada 10 dias`` -> ``10``
  ``Quinzenal``      -> ``15``
  ``Mensal``         -> ``30``
  ``Bimestral``      -> ``60``
  ``Trimestral``     -> ``90``

Acentos preservados nas chaves (decisao Caminho B Fase 6). Lookup e'
case-insensitive + strip de whitespace (parser pode retornar
``"Semanal"`` capitalizado; wizard grava ``"semanal"`` -- ambos
resolvem para o mesmo inteiro).

N7: nunca levanta. Tipo desconhecido -> ``None``.
"""
from __future__ import annotations

# Frequencias periodicas com periodicidade conhecida.
# Chaves duplicadas para "Diário"/"dose única" cobrem o output do
# parser (``_norm_frequency_type`` retorna "Diário" com acento, e
# o wizard grava "semanal"/"diario" lowercase sem acento). Lookup
# e' feito apos ``.strip().lower()`` -- entao qualquer das duas
# variantes casa. Ver ``test_period_days_has_only_known_labels``.
_PERIODIC_DAYS: dict[str, int] = {
    "diario": 1,
    "diário": 1,
    "a cada 5 dias": 5,
    "semanal": 7,
    "a cada 10 dias": 10,
    "quinzenal": 15,
    "mensal": 30,
    "bimestral": 60,
    "trimestral": 90,
}

# Tabela publica: contem tambem o caso sentinela ``None`` para
# ``dose única``. Mantem todos os 9 valores canônicos em um único
# dicionario para o caller nao precisar ramificar.
PERIOD_DAYS: dict[str, int | None] = {
    **_PERIODIC_DAYS,
    "dose unica": None,
    "dose única": None,
}


def derive_periodicity(frequency_type: str | None) -> int | None:
    """Mapeia ``frequency_type`` para ``periodicity_days``.

    Parameters
    ----------
    frequency_type:
        Rotulo canônico (qualquer case, com ou sem acento, com whitespace
        residual). Aceita tanto a forma capitalizada do parser
        (``"Semanal"``) quanto a lowercase do wizard (``"semanal"``).
        ``None``/vazio -> ``None``.

    Returns
    -------
    int | None
        Dias entre sessoes (``7`` para Semanal, etc.), ou ``None`` se:

        - ``frequency_type`` for ``None`` / vazio / so whitespace;
        - rotulo nao constar em :data:`PERIOD_DAYS` (ex.: typo);
        - rotulo for ``dose única`` (sentinela -- nao ha periodicidade
          relevante para dose pontual).

    Notes
    -----
    - Nao levanta nunca (N7).
    - Acentos preservados -- ``"Diário"`` mapeia para ``"diario"`` antes
      de consultar a tabela (lookup case-insensitive via ``.lower()``).
    - ``"dose única"`` retorna ``None`` por design (sentinela) -- ver
      memoria ``[[mvp-jornada-clinica-2026-06-30]]`` regra rolante.
    """
    if not frequency_type:
        return None
    return PERIOD_DAYS.get(frequency_type.strip().lower())


__all__ = ["PERIOD_DAYS", "derive_periodicity"]
