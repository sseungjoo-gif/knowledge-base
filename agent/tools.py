"""metrics.py의 계산 함수를 Claude 도구(tool)로 노출한다.

도구 함수는 전부 계산을 metrics.py에 위임하고, 여기서는 Claude가 호출할 수 있는
인터페이스(스키마 + 에러를 문자열로 변환)만 담당한다.
"""

from anthropic import beta_tool

from . import metrics
from .metrics import MetricError


def _safe(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except MetricError as e:
        return {"error": str(e)}


@beta_tool
def list_available_data() -> dict:
    """이 에이전트가 가진 샘플 데이터의 범위(기간·부문)를 알려준다.

    다른 지표 도구를 호출하기 전에, 어떤 기간/부문이 존재하는지 먼저 확인할 때 쓴다.
    """
    from . import data

    return {
        "room_inventory_periods": list(data.ROOM_INVENTORY.keys()),
        "departmental_detail_period": "2026-12",
        "departments": list(data.DEPARTMENTS_2026_12.keys()),
        "flow_through_comparison": "2025-12(전년) vs 2026-12(당월)",
        "note": "고객(Attach Rate·CLV) 데이터는 이 샘플에는 아직 없습니다.",
    }


@beta_tool
def get_room_sales_metrics(period: str) -> dict:
    """특정 기간의 객실 판매 지표(OCC·ADR·RevPAR·Net ADR·NRevPAR)를 계산한다.

    Args:
        period: "2026-10", "2026-11", "2026-12" 중 하나.
    """
    return _safe(
        lambda: {
            "occ": round(metrics.occ(period), 4),
            "adr": round(metrics.adr(period)),
            "revpar": round(metrics.revpar(period)),
            "net_adr": round(metrics.net_adr(period)),
            "nrevpar": round(metrics.nrevpar(period)),
        }
    )


@beta_tool
def get_channel_mix_trend(period: str) -> dict:
    """OTA 비중과, RevPAR·NRevPAR 간 격차를 함께 보여준다 (수수료 유출 진단용).

    Args:
        period: "2026-10", "2026-11", "2026-12" 중 하나.
    """
    return _safe(metrics.channel_mix, period)


@beta_tool
def get_departmental_profit(period: str, department: str, basis: str) -> dict:
    """부문 이익을 배부 전/후 중 선택해서 계산한다. 반드시 basis를 명시해야 한다.

    Args:
        period: 부문 상세 데이터는 "2026-12"만 존재한다.
        department: "Rooms", "FB", "Banquet", "Other" 중 하나.
        basis: "preAllocation"(배부 전) 또는 "postAllocation"(배부 후).
    """
    return _safe(metrics.departmental_profit, period, department, basis)


@beta_tool
def get_gop_and_goppar(period: str) -> dict:
    """GOP(총영업이익)와 GOPPAR를 계산한다. 호텔 전체 범위 지표이며 부문별로는 존재하지 않는다.

    Args:
        period: GOP 데이터는 "2026-12"만 존재한다.
    """
    return _safe(
        lambda: {**metrics.gop(period), "goppar": round(metrics.goppar(period))}
    )


@beta_tool
def get_flow_through(period_current: str, period_prior: str, department: str = "") -> dict:
    """Flow-through(이익 전환율)를 계산한다. 서로 다른 두 기간이 반드시 필요하다.

    Args:
        period_current: 비교 대상 당기 (예: "2026-12").
        period_prior: 비교 대상 전기 (예: "2025-12").
        department: 비워두면 전사 기준. "FB"를 넣으면 F&B 부문 기준.
    """
    dept = department if department else None
    return _safe(metrics.flow_through, period_current, period_prior, dept)


@beta_tool
def get_food_cost_rate(period: str) -> dict:
    """F&B 식자재 원가율을 표준원가율과 함께 비교해서 반환한다 (단독 판단 금지).

    Args:
        period: F&B 원가 데이터는 "2026-12"만 존재한다.
    """
    return _safe(metrics.food_cost_rate, period)


@beta_tool
def get_market_benchmark(period: str) -> dict:
    """시장 대비 경쟁력 지표(MPI·ARI·RGI)를 계산한다.

    Args:
        period: 시장 벤치마크 데이터는 "2026-12"만 존재한다.
    """
    return _safe(metrics.market_benchmark_indices, period)


ALL_TOOLS = [
    list_available_data,
    get_room_sales_metrics,
    get_channel_mix_trend,
    get_departmental_profit,
    get_gop_and_goppar,
    get_flow_through,
    get_food_cost_rate,
    get_market_benchmark,
]
