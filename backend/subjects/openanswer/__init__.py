"""Автопроверка открытого ответа: Level 1 (нормализатор + числа) и Level 2 (SymPy).

Перенесено из лаборатории без правок в логике: покрытие 588 ответов банка
замерено там же (auto 96,3%, конфликтов 0), здесь к этим решениям добавляется
только место входа — `score_open_answer`.
"""
from .compare import compare, score_open_answer

__all__ = ['compare', 'score_open_answer']
