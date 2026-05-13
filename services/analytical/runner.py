"""
KOBİ AI Platform — Analytical Runner (Entry Point)

Dışarıdan tek çağrı noktası: run_analytical_query()
rag_service.query() içindeki `if analytical:` bloğundan çağrılır.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Literal, Optional

from services.analytical.graph import build_analytical_graph
from services.analytical.state import AnalysisState
from services.usage_logger import UsageLogData

logger = logging.getLogger(__name__)


def run_analytical_query(
    question: str,
    openai_client,
    model: str,
    generate_sql_fn,
    data_filter,
    executor,
    sql_agent,
    usage_logger,
    user_id: Optional[str] = None,
    user_ip: Optional[str] = None,
    session_id: Optional[str] = None,
    analytical_depth: Literal["light", "medium", "deep"] = "medium",
    skip_filters: bool = False,
    insight_mode: bool = True,
) -> Dict[str, Any]:
    """
    Analytical multi-agent pipeline'ını çalıştırır.

    Args:
        question: Kullanıcı sorusu
        openai_client: OpenAI client instance (rag_service'den geçilir)
        model: Chat model adı
        generate_sql_fn: rag_service._generate_sql callable
        data_filter: DataQualityFilter instance
        executor: SQLExecutor instance
        sql_agent: SQLAgent instance
        usage_logger: UsageLogger instance
        user_id, user_ip, session_id: Log bilgileri
        analytical_depth: "light" | "medium" | "deep"
        skip_filters: Veri kalite filtrelerini atla

    Returns:
        rag_service.query() ile aynı dict formatı:
        {
          "success": bool,
          "answer": str,                  # insight metni
          "sql": str,                     # primary SQL
          "sql_description": str,         # SQL'in ne yaptığı (SQL yerine gösterilir)
          "result": QueryResult,          # primary result
          "secondary_results": [...],     # karşılaştırma sonuçları
          "insight": str,
          "filtered_count": int,
          "has_filters": bool,
          "log_id": int | None,
          "tokens": {prompt, completion, total},
          "error": str | None,
          "analytical": True,
          "agent_count": int,
          "comparison_sql_count": int,
        }
    """
    start_time = datetime.now()
    logger.info(f"[Runner] Analytical sorgu başladı: '{question[:80]}' (depth={analytical_depth})")

    # ── Initial State ───────────────────────────────────────────────
    initial_state: AnalysisState = {
        "question": question,
        "user_id": user_id,
        "user_ip": user_ip,
        "session_id": session_id,
        "analytical_depth": analytical_depth,
        "skip_filters": skip_filters,

        # Primary SQL
        "primary_sql": "",
        "primary_sql_description": "",
        "primary_result": None,

        # Comparison
        "comparison_plans": [],
        "secondary_sqls": [],
        "secondary_results": [],

        # Insight
        "insight": "",

        # Hata takibi
        "errors": [],

        # Token/agent sayaçları
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "agent_count": 0,
        "comparison_sql_count": 0,
    }

    # ── Graph ───────────────────────────────────────────────────────
    try:
        graph = build_analytical_graph(
            client=openai_client,
            model=model,
            generate_sql_fn=generate_sql_fn,
            data_filter=data_filter,
            executor=executor,
            sql_agent=sql_agent,
        )
    except Exception as e:
        logger.error(f"[Runner] Graph derleme hatası: {e}")
        return {
            "success": False,
            "answer": f"Analiz sistemi başlatılamadı: {e}",
            "error": str(e),
            "analytical": True,
            "insight_mode": insight_mode,
            "data": None, "columns": None, "visualization_type": None,
            "secondary_results": [],
        }

    # ── Çalıştır ────────────────────────────────────────────────────
    try:
        final_state = graph.invoke(initial_state)
    except Exception as e:
        logger.error(f"[Runner] Graph invoke hatası: {e}")
        import traceback; traceback.print_exc()
        return {
            "success": False,
            "answer": f"Analiz sırasında hata oluştu: {e}",
            "error": str(e),
            "analytical": True,
            "insight_mode": insight_mode,
            "data": None, "columns": None, "visualization_type": None,
            "secondary_results": [],
        }

    # ── Sonuçları topla ─────────────────────────────────────────────
    response_time_ms = (datetime.now() - start_time).total_seconds() * 1000
    primary_result = final_state.get("primary_result")
    insight = final_state.get("insight") or ""
    errors = final_state.get("errors", [])

    prompt_tokens = final_state.get("total_prompt_tokens", 0)
    completion_tokens = final_state.get("total_completion_tokens", 0)
    total_tokens = prompt_tokens + completion_tokens

    success = bool(primary_result and primary_result.success)

    if errors:
        logger.warning(f"[Runner] Pipeline hataları: {errors}")

    # ── Usage Log ───────────────────────────────────────────────────
    try:
        import json
        extra = {
            "analytical": True,
            "analytical_depth": analytical_depth,
            "agent_count": final_state.get("agent_count", 0),
            "comparison_sql_count": final_state.get("comparison_sql_count", 0),
            "intent": final_state.get("intent", ""),
            "errors": errors[:3],  # İlk 3 hata yeterli
        }
        log_data = UsageLogData(
            question=question,
            status="success" if success else "error",
            user_id=user_id,
            user_ip=user_ip,
            session_id=session_id,
            generated_sql=final_state.get("primary_sql", ""),
            sql_execution_time_ms=primary_result.execution_time_ms if primary_result else None,
            row_count=primary_result.row_count if primary_result else 0,
            ai_model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            response_time_ms=response_time_ms,
            error_message="; ".join(errors) if errors else None,
            error_type="analytical_pipeline_error" if errors else None,
            extra_data=json.dumps(extra, ensure_ascii=False)[:1000],
        )
        log_id = usage_logger.log_usage(log_data)
    except Exception as e:
        logger.error(f"[Runner] Log hatası: {e}")
        log_id = None

    logger.info(
        f"[Runner] Tamamlandı: success={success}, "
        f"agents={final_state.get('agent_count')}, "
        f"comparisons={final_state.get('comparison_sql_count')}, "
        f"tokens={total_tokens}, "
        f"süre={response_time_ms:.0f}ms"
    )

    # ── Dönüş ───────────────────────────────────────────────────────
    return {
        "success": success,
        "answer": insight or (primary_result and str(primary_result.row_count) + " sonuç bulundu." or "Sonuç bulunamadı."),
        "insight": insight,
        "sql": final_state.get("primary_sql", "") if not insight_mode else None,
        "sql_original": final_state.get("primary_sql", "") if not insight_mode else None,
        "sql_description": final_state.get("primary_sql_description", ""),
        "result": primary_result,
        "data": primary_result.data if primary_result and primary_result.success and not insight_mode else None,
        "columns": primary_result.columns if primary_result and primary_result.success and not insight_mode else None,
        "visualization_type": primary_result.visualization_type if primary_result and primary_result.success and not insight_mode else None,
        "secondary_results": final_state.get("secondary_results", []) if not insight_mode else [],
        "filtered_count": 0,
        "has_filters": not skip_filters and bool(primary_result),
        "log_id": log_id,
        "insight_mode": insight_mode,
        "tokens": {
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "total": total_tokens,
        },
        "error": "; ".join(errors) if errors and not success else None,
        "analytical": True,
        "agent_count": final_state.get("agent_count", 0),
        "comparison_sql_count": final_state.get("comparison_sql_count", 0),
        "intent": final_state.get("intent", ""),
    }