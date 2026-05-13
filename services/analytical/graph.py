"""
KOBİ AI Platform — Analytical Multi-Agent StateGraph

Akış:
  intent_router
       ↓
  primary_sql_generator
       ↓
  primary_sql_executor
       ↓
  sql_description
       ↓
  [primary başarılı mı?]
     YES → comparison_planner → secondary_sql_runner → insight_agent
     NO  → insight_agent (graceful degradation)
       ↓
      END

NOT: Kullanıcı analitik modu zaten açtığı için karşılaştırma kararını
intent chain'e bırakmıyoruz. Comparison planner LLM'i zaten anlamlı
karşılaştırma yoksa boş liste döner.
"""

import logging
from typing import Literal

from langgraph.graph import END, StateGraph

from services.analytical.state import AnalysisState
from services.analytical.nodes import (
    node_primary_sql_generator,
    node_primary_sql_executor,
    node_sql_description,
    node_comparison_planner,
    node_secondary_sql_runner,
    node_insight_agent,
)

logger = logging.getLogger(__name__)


def build_analytical_graph(
    client,
    model: str,
    generate_sql_fn,
    data_filter,
    executor,
    sql_agent,
):
    """
    Tüm servis bağımlılıklarını alarak StateGraph'i derler ve döner.
    """

    def _primary_sql_generator(state: AnalysisState) -> AnalysisState:
        return node_primary_sql_generator(
            state,
            generate_sql_fn=generate_sql_fn,
            data_filter=data_filter,
            skip_filters=state.get("skip_filters", False),
        )

    def _primary_sql_executor(state: AnalysisState) -> AnalysisState:
        return node_primary_sql_executor(state, executor=executor, sql_agent=sql_agent)

    def _sql_description(state: AnalysisState) -> AnalysisState:
        return node_sql_description(state, client=client, model=model)

    def _comparison_planner(state: AnalysisState) -> AnalysisState:
        return node_comparison_planner(state, client=client, model=model)

    def _secondary_sql_runner(state: AnalysisState) -> AnalysisState:
        return node_secondary_sql_runner(
            state,
            client=client,
            model=model,
            executor=executor,
            sql_agent=sql_agent,
            data_filter=data_filter,
            skip_filters=state.get("skip_filters", False),
        )

    def _insight_agent(state: AnalysisState) -> AnalysisState:
        return node_insight_agent(state, client=client, model=model)

    # ── Routing ────────────────────────────────────────────────────
    #
    # DÜZELTME: needs_comparison flag'ine BAKMA.
    # Kullanıcı analitik modu açtı → her zaman comparison_planner'a git.
    # Comparison planner anlamlı karşılaştırma yoksa boş liste döner,
    # secondary_sql_runner o zaman hiçbir şey çalıştırmaz.
    # Sadece primary SQL başarısızsa kısa devre yap.

    def route_after_description(state: AnalysisState) -> Literal["comparison_planner", "insight_agent"]:
        primary_ok = bool(state.get("primary_result") and state["primary_result"].success)

        if primary_ok:
            logger.info("[Router] Primary başarılı → Comparison Planner")
            return "comparison_planner"

        logger.warning("[Router] Primary başarısız → Doğrudan Insight")
        return "insight_agent"

    # ── Graph inşası ───────────────────────────────────────────────

    g = StateGraph(AnalysisState)

    g.add_node("primary_sql_generator", _primary_sql_generator)
    g.add_node("primary_sql_executor",  _primary_sql_executor)
    g.add_node("sql_description",       _sql_description)
    g.add_node("comparison_planner",    _comparison_planner)
    g.add_node("secondary_sql_runner",  _secondary_sql_runner)
    g.add_node("insight_agent",         _insight_agent)

    g.set_entry_point("primary_sql_generator")
    g.add_edge("primary_sql_generator", "primary_sql_executor")
    g.add_edge("primary_sql_executor",  "sql_description")

    g.add_conditional_edges(
        "sql_description",
        route_after_description,
        {
            "comparison_planner": "comparison_planner",
            "insight_agent":      "insight_agent",
        },
    )

    g.add_edge("comparison_planner",   "secondary_sql_runner")
    g.add_edge("secondary_sql_runner", "insight_agent")
    g.add_edge("insight_agent",        END)

    compiled = g.compile()
    logger.info("Analytical graph derlendi ✅")
    return compiled