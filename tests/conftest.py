"""Configuração do pytest para testes do app Streamlit."""
from __future__ import annotations

import pytest


@pytest.fixture
def mock_data():
    """Fixture que fornece dados mockados para testes."""
    from src.mock_data import load_mock_data
    return load_mock_data()


@pytest.fixture
def patient_summary(mock_data):
    """Fixture que fornece o resumo de pacientes."""
    from src.metrics import patient_summary
    return patient_summary(mock_data)
