"""
TYF Analytical Multi-Agent - State Tanımı
LangGraph StateGraph için AnalysisState TypedDict
"""

from typing import Any, Dict, List, Optional, TypedDict


class ComparisonPlan(TypedDict):
    """Tek bir karşılaştırma planı"""
    description: str       # "2023 yılı yarış sayısıyla karşılaştır"
    sql_hint: str          # LLM'e SQL üretiminde yardımcı ipucu
    rationale: str         # Neden bu karşılaştırma anlamlı?


class SecondaryResult(TypedDict):
    """Secondary SQL sonucu"""
    description: str       # Planner'ın açıklaması (karşılaştırma türü)
    sql_description: str   # SQL'in ne getirdiği (sorudan bağımsız)
    rationale: str         # Neden bu karşılaştırma seçildi
    sql: str               # Çalışan SQL
    data: List[Dict]
    columns: List[str]
    row_count: int
    visualization_type: str
    success: bool
    error: Optional[str]


class AnalysisState(TypedDict):
    """
    Tüm analytical pipeline boyunca taşınan state.
    Her node bu dict'i okuyup günceller.
    """

    # ── Giriş ──────────────────────────────────────────────────────
    question: str
    user_id: Optional[str]
    user_ip: Optional[str]
    session_id: Optional[str]
    analytical_depth: str         # "light" | "medium" | "deep"
    skip_filters: bool

    # ── Primary SQL ─────────────────────────────────────────────
    primary_sql: str
    primary_sql_description: str  # SQL'in ne getirdiği (sorudan bağımsız)
    primary_result: Optional[Any] # QueryResult nesnesi

    # ── Comparison & Secondary ───────────────────────────────────
    comparison_plans: List[ComparisonPlan]     # Planner kararları (max 1)
    secondary_sqls: List[str]                  # Üretilen secondary SQL'ler
    secondary_results: List[SecondaryResult]   # Çalıştırılan sonuçlar

    # ── Insight ─────────────────────────────────────────────────
    insight: str              # Türkçe doğal dil özet + içgörü

    # ── Hata takibi ─────────────────────────────────────────────
    errors: List[str]

    # ── Token / Log takibi ───────────────────────────────────────
    total_prompt_tokens: int
    total_completion_tokens: int
    agent_count: int              # Kaç agent çalıştı
    comparison_sql_count: int     # Kaç secondary SQL çalıştı