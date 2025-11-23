"""Pacote com processadores para diferentes modelos de extração."""

from .ficha_financeira_processor import FichaFinanceiraProcessor
from .planilha_dados_processor import PlanilhaDadosProcessor

__all__ = ["FichaFinanceiraProcessor", "PlanilhaDadosProcessor"]
