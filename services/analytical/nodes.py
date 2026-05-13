"""
KOBİ AI Platform — Analytical Multi-Agent Node Fonksiyonları
=============================================================
Her node, LangGraph StateGraph içinde bir adıma karşılık gelir.

TYF'den farklar:
  - data_filter.needs_age_filter / add_age_filter → ensure_active_filters
    (Mikro'da yaş filtresi yok, iptal/hidden filtresi var)
  - ZeroResultHandler arayüzü: (sql, question, result) → Dict
    (TYF'de was_retried tuple'ı vardı, Mikro'da Dict döner)
  - _dedup_result korundu (gereksiz tekrar satırları bellekte tekilleştir)
"""

import logging
from typing import Any, Optional

from services.analytical.state import AnalysisState, ComparisonPlan, SecondaryResult
from services.analytical.chains import (
    run_sql_description_chain,
    run_comparison_planner_chain,
    run_secondary_sql_chain,
    run_insight_chain,
)
from services.sql_executor import SQLExecutor

logger = logging.getLogger(__name__)


# ── Yardımcı: QueryResult → Kısa Metin Özeti ─────────────────────────────

def _summarize_result(result) -> str:
    """QueryResult nesnesini insight chain için kısa metin özetine çevir."""
    if result is None or not result.success:
        return "Veri getirilemedi."
    if result.row_count == 0:
        return "Sonuç bulunamadı."
    if result.row_count == 1 and len(result.columns) == 1:
        val = list(result.data[0].values())[0]
        # Para birimi formatı uygula (sayı ise)
        try:
            num = float(val)
            if num >= 1000:
                return f"Sonuç: ₺{num:,.2f}"
            return f"Sonuç: {val}"
        except (TypeError, ValueError):
            return f"Sonuç: {val}"
    if result.row_count > 20:
        col     = result.columns[0]
        samples = [str(r[col]) for r in result.data[:5]]
        return f"Toplam {result.row_count} kayıt. İlk 5: {', '.join(samples)}..."
    lines = []
    for row in result.data[:10]:
        vals = [str(v) for v in row.values() if v is not None]
        lines.append(" | ".join(vals))
    return f"{result.row_count} kayıt:\n" + "\n".join(lines)


# ── Yardımcı: Tekrar Satır Tekilleştirme ─────────────────────────────────

def _dedup_result(result):
    """
    Sonuç satırları tamamen aynıysa bellekte tekilleştir (yeniden sorgu atmadan).
    Örnek: [(A, 100), (A, 100), (B, 200)] → [(A, 100), (B, 200)]
    """
    if not result or not result.success or result.row_count <= 1:
        return result
    seen       = set()
    unique     = []
    for row in result.data:
        key = tuple(sorted(row.items()))
        if key not in seen:
            seen.add(key)
            unique.append(row)
    if len(unique) < result.row_count:
        import dataclasses
        result = dataclasses.replace(result, data=unique, row_count=len(unique))
        logger.info(f"[Dedup] {len(unique)} tekil satır kaldı")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# NODE 1 — Primary SQL Generator
# ─────────────────────────────────────────────────────────────────────────────

def node_primary_sql_generator(
    state: AnalysisState,
    generate_sql_fn,
    data_filter,
    skip_filters: bool,
) -> AnalysisState:
    """
    rag_service._generate_sql'yi çağırır.
    Mikro filtresi: iptal/hidden kontrolü (yaş filtresi yok).
    """
    logger.info("[Node] Primary SQL Generator başladı")
    try:
        sql_resp     = generate_sql_fn(question=state["question"], context="")
        sql_original = sql_resp.get("sql") or ""
        sql_filtered = sql_original

        # Mikro filtresi: iptal/hidden kolonları eksikse ekle
        if not skip_filters and sql_filtered:
            sql_filtered = data_filter.ensure_active_filters(sql_filtered)
            logger.debug("[Node] iptal/hidden filtreleri kontrol edildi")

        return {
            **state,
            "primary_sql":              sql_filtered,
            "total_prompt_tokens":      state["total_prompt_tokens"] + sql_resp.get("prompt_tokens", 0),
            "total_completion_tokens":  state["total_completion_tokens"] + sql_resp.get("completion_tokens", 0),
            "agent_count":              state["agent_count"] + 1,
        }
    except Exception as e:
        logger.error(f"[Node] Primary SQL Generator hatası: {e}")
        return {
            **state,
            "primary_sql":  "",
            "errors":       state["errors"] + [f"primary_sql_generator: {e}"],
            "agent_count":  state["agent_count"] + 1,
        }


# ─────────────────────────────────────────────────────────────────────────────
# NODE 2 — Primary SQL Executor
# ─────────────────────────────────────────────────────────────────────────────

def node_primary_sql_executor(
    state: AnalysisState,
    executor: SQLExecutor,
    sql_agent,
    zero_result_handler=None,   # Mikro'da Dict döner (was_retried yok)
) -> AnalysisState:
    """
    Primary SQL'i çalıştırır.
    Hata → sql_agent ile düzelt.
    0 satır → ZeroResultHandler ile öneri al (analitik modda sadece log, düzeltme yok).
    """
    logger.info("[Node] Primary SQL Executor başladı")
    sql = state.get("primary_sql", "")

    if not sql:
        return {
            **state,
            "primary_result": None,
            "errors":         state["errors"] + ["primary_sql_executor: SQL boş"],
            "agent_count":    state["agent_count"] + 1,
        }

    try:
        result = executor.execute_query(sql)

        # SQL hatası → agent
        if not result.success:
            logger.warning(f"[Node] Primary SQL hatası → agent: {result.error}")
            result, sql = sql_agent.run(
                sql=sql,
                question=state["question"],
                schema_context="",
            )

        # 0 satır → ZeroResultHandler (analitik modda loglama amaçlı)
        if result and result.success and result.row_count == 0 and zero_result_handler:
            logger.info("[Node] 0 satır — ZeroResultHandler (analitik modda öneri yok, sadece log)")
            suggestion = zero_result_handler.handle(
                sql=sql,
                question=state["question"],
                original_result=result,
            )
            # Analitik modda clarification döndürmüyoruz; insight agent "veri yok" der
            if suggestion.get("clarification_needed"):
                logger.info(
                    f"[Node] ZeroResult önerileri: "
                    f"{[s.get('label') for s in suggestion.get('suggestions', [])]}"
                )

        # Tekrar eden satırları tekilleştir
        result = _dedup_result(result)

        logger.info(f"[Node] Primary SQL sonuç: {result.row_count if result else 0} satır")
        return {
            **state,
            "primary_sql":    sql,
            "primary_result": result,
            "agent_count":    state["agent_count"] + 1,
        }

    except Exception as e:
        logger.error(f"[Node] Primary SQL Executor hatası: {e}")
        return {
            **state,
            "primary_result": None,
            "errors":         state["errors"] + [f"primary_sql_executor: {e}"],
            "agent_count":    state["agent_count"] + 1,
        }


# ─────────────────────────────────────────────────────────────────────────────
# NODE 3 — SQL Description
# ─────────────────────────────────────────────────────────────────────────────

def node_sql_description(state: AnalysisState, client, model: str) -> AnalysisState:
    """SQL'in ne getirdiğini 1 cümleyle açıklar — sorudan bağımsız."""
    logger.info("[Node] SQL Description başladı")
    try:
        desc, pt, ct = run_sql_description_chain(
            client=client,
            sql=state.get("primary_sql", ""),
            model=model,
        )
        return {
            **state,
            "primary_sql_description":  desc,
            "total_prompt_tokens":      state["total_prompt_tokens"] + pt,
            "total_completion_tokens":  state["total_completion_tokens"] + ct,
            "agent_count":              state["agent_count"] + 1,
        }
    except Exception as e:
        logger.error(f"[Node] SQL Description hatası: {e}")
        return {
            **state,
            "primary_sql_description":  "Sorgu çalıştırıldı.",
            "errors":                   state["errors"] + [f"sql_description: {e}"],
            "agent_count":              state["agent_count"] + 1,
        }


# ─────────────────────────────────────────────────────────────────────────────
# NODE 4 — Comparison Planner
# ─────────────────────────────────────────────────────────────────────────────

def node_comparison_planner(state: AnalysisState, client, model: str) -> AnalysisState:
    """Anlamlı e-ticaret karşılaştırmalarını planlar."""
    logger.info("[Node] Comparison Planner başladı")
    try:
        result_summary = _summarize_result(state.get("primary_result"))

        plans, pt, ct = run_comparison_planner_chain(
            client=client,
            question=state["question"],
            rewritten_question=state.get("rewritten_question", state["question"]),
            primary_sql=state.get("primary_sql", ""),
            primary_result_summary=result_summary,
            analytical_depth=state.get("analytical_depth", "medium"),
            model=model,
        )
        return {
            **state,
            "comparison_plans":         plans,
            "total_prompt_tokens":      state["total_prompt_tokens"] + pt,
            "total_completion_tokens":  state["total_completion_tokens"] + ct,
            "agent_count":              state["agent_count"] + 1,
        }
    except Exception as e:
        logger.error(f"[Node] Comparison Planner hatası: {e}")
        return {
            **state,
            "comparison_plans": [],
            "errors":           state["errors"] + [f"comparison_planner: {e}"],
            "agent_count":      state["agent_count"] + 1,
        }


# ─────────────────────────────────────────────────────────────────────────────
# NODE 5 — Secondary SQL Runner
# ─────────────────────────────────────────────────────────────────────────────

def node_secondary_sql_runner(
    state: AnalysisState,
    client,
    model: str,
    executor: SQLExecutor,
    sql_agent,
    data_filter,
    skip_filters: bool,
) -> AnalysisState:
    """
    Her comparison plan için secondary SQL üretir ve çalıştırır.
    Hata durumunda sql_agent ile düzeltmeyi dener.
    """
    logger.info("[Node] Secondary SQL Runner başladı")
    plans = state.get("comparison_plans", [])
    if not plans:
        return {**state, "secondary_results": [], "comparison_sql_count": 0}

    secondary_results = []
    total_pt  = 0
    total_ct  = 0
    sql_count = 0

    for plan in plans:
        description = plan.get("description", "")
        sql_hint    = plan.get("sql_hint", "")
        rationale   = plan.get("rationale", "")

        logger.info(f"[Node] Secondary SQL: {description}")

        # ── SQL Üret ────────────────────────────────────────────────────
        try:
            sql, pt, ct = run_secondary_sql_chain(
                client=client,
                original_question=state["question"],
                primary_sql=state.get("primary_sql", ""),
                comparison_description=description,
                sql_hint=sql_hint,
                model=model,
            )
            total_pt += pt
            total_ct += ct
        except Exception as e:
            logger.error(f"Secondary SQL üretim hatası: {e}")
            secondary_results.append({
                "description":      description,
                "sql_description":  "",
                "rationale":        rationale,
                "sql":              "",
                "data":             [],
                "columns":          [],
                "row_count":        0,
                "visualization_type": "table",
                "success":          False,
                "error":            str(e),
            })
            continue

        if not sql:
            secondary_results.append({
                "description":      description,
                "sql_description":  "",
                "rationale":        rationale,
                "sql":              "",
                "data":             [],
                "columns":          [],
                "row_count":        0,
                "visualization_type": "table",
                "success":          False,
                "error":            "SQL üretilemedi",
            })
            continue

        # ── Mikro Filtresi ───────────────────────────────────────────────
        if not skip_filters:
            sql = data_filter.ensure_active_filters(sql)

        # ── Çalıştır ────────────────────────────────────────────────────
        try:
            result = executor.execute_query(sql)

            if not result.success:
                logger.warning(f"Secondary SQL hatası → agent: {result.error}")
                result, sql = sql_agent.run(
                    sql=sql,
                    question=f"{state['question']} — {description}",
                    schema_context="",
                )

            sql_count += 1
            result = _dedup_result(result)

            # SQL açıklaması
            sql_desc = ""
            try:
                sql_desc, desc_pt, desc_ct = run_sql_description_chain(
                    client=client, sql=sql, model=model,
                )
                total_pt += desc_pt
                total_ct += desc_ct
            except Exception:
                sql_desc = description

            secondary_results.append({
                "description":      description,
                "sql_description":  sql_desc,
                "rationale":        rationale,
                "sql":              sql,
                "data":             result.data    if result and result.success else [],
                "columns":          result.columns if result and result.success else [],
                "row_count":        result.row_count if result and result.success else 0,
                "visualization_type": result.visualization_type if result and result.success else "table",
                "success":          bool(result and result.success),
                "error":            result.error if result and not result.success else None,
                # insight chain için özet
                "summary":          _summarize_result(result) if result and result.success else "Veri yok",
            })
            logger.info(f"Secondary SQL OK: {result.row_count if result else 0} satır ({description})")

        except Exception as e:
            logger.error(f"Secondary SQL execute hatası: {e}")
            secondary_results.append({
                "description":      description,
                "sql_description":  "",
                "rationale":        rationale,
                "sql":              sql,
                "data":             [],
                "columns":          [],
                "row_count":        0,
                "visualization_type": "table",
                "success":          False,
                "error":            str(e),
            })

    return {
        **state,
        "secondary_sqls":           [r["sql"] for r in secondary_results],
        "secondary_results":        secondary_results,
        "comparison_sql_count":     sql_count,
        "total_prompt_tokens":      state["total_prompt_tokens"] + total_pt,
        "total_completion_tokens":  state["total_completion_tokens"] + total_ct,
        "agent_count":              state["agent_count"] + len(plans),
    }


# ─────────────────────────────────────────────────────────────────────────────
# NODE 6 — Insight Agent
# ─────────────────────────────────────────────────────────────────────────────

def node_insight_agent(state: AnalysisState, client, model: str) -> AnalysisState:
    """Tüm sorgu sonuçlarını alır, Türkçe e-ticaret içgörüsü yazar."""
    logger.info("[Node] Insight Agent başladı")
    try:
        primary_result  = state.get("primary_result")
        primary_summary = _summarize_result(primary_result)

        # Secondary sonuçları insight chain formatına hazırla
        secondary_summaries = []
        for sec in state.get("secondary_results", []):
            # sec artık dict (TYF'de TypedDict, Mikro'da sade dict)
            sec_data = sec if isinstance(sec, dict) else dict(sec)
            secondary_summaries.append({
                "description":    sec_data.get("description", ""),
                "sql_description": sec_data.get("sql_description", sec_data.get("description", "")),
                "summary":        sec_data.get("summary", ""),
                "success":        sec_data.get("success", False),
            })

        insight, pt, ct = run_insight_chain(
            client=client,
            question=state["question"],
            primary_description=state.get("primary_sql_description", "Sorgu çalıştırıldı."),
            primary_result_summary=primary_summary,
            secondary_summaries=secondary_summaries,
            analytical_depth=state.get("analytical_depth", "medium"),
            model=model,
        )
        return {
            **state,
            "insight":                  insight,
            "total_prompt_tokens":      state["total_prompt_tokens"] + pt,
            "total_completion_tokens":  state["total_completion_tokens"] + ct,
            "agent_count":              state["agent_count"] + 1,
        }
    except Exception as e:
        logger.error(f"[Node] Insight Agent hatası: {e}")
        primary_result = state.get("primary_result")
        return {
            **state,
            "insight":  _summarize_result(primary_result),
            "errors":   state["errors"] + [f"insight_agent: {e}"],
            "agent_count": state["agent_count"] + 1,
        }