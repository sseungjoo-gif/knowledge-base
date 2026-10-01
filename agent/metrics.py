"""1.3 온톨로지(hotel-ontology.md)의 Metric 정의를 그대로 구현한 결정론적 계산 함수들.

원칙(온톨로지 0장):
- 계산은 전부 여기서 코드로 하고, LLM에게 숫자 계산을 맡기지 않는다.
- 온톨로지 6장의 함정 방지 제약을 함수 시그니처/검증으로 강제한다.
"""

from . import data


class MetricError(Exception):
    """제약 위반 등으로 계산을 거부할 때 사용."""


def _inventory(period: str) -> dict:
    if period not in data.ROOM_INVENTORY:
        raise MetricError(f"'{period}' 기간의 객실 재고 데이터가 없습니다. 사용 가능한 기간: {list(data.ROOM_INVENTORY)}")
    return data.ROOM_INVENTORY[period]


def available_rooms(period: str) -> int:
    inv = _inventory(period)
    return data.ROOM_COUNT * inv["days"]


def occ(period: str) -> float:
    inv = _inventory(period)
    return inv["sold_rooms"] / available_rooms(period)


def adr(period: str) -> float:
    inv = _inventory(period)
    return inv["revenue"] / inv["sold_rooms"]


def revpar(period: str) -> float:
    inv = _inventory(period)
    return inv["revenue"] / available_rooms(period)


def ota_commission(period: str) -> float:
    inv = _inventory(period)
    return inv["ota_revenue"] * data.OTA_COMMISSION_RATE


def net_adr(period: str) -> float:
    """채널 수수료를 뺀 실수취 단가 (OTA 매출분만 수수료 차감, 직판은 그대로)."""
    inv = _inventory(period)
    commission = ota_commission(period)
    net_revenue = inv["revenue"] - commission
    return net_revenue / inv["sold_rooms"]


def nrevpar(period: str) -> float:
    inv = _inventory(period)
    commission = ota_commission(period)
    return (inv["revenue"] - commission) / available_rooms(period)


def channel_mix(period: str) -> dict:
    """진단용 보조 지표 — OTA 비중이 올라가는지 확인할 때 쓴다 (함정 ①)."""
    inv = _inventory(period)
    ota_ratio = inv["ota_sold_rooms"] / inv["sold_rooms"]
    return {
        "ota_room_ratio": round(ota_ratio, 4),
        "revpar": round(revpar(period)),
        "nrevpar": round(nrevpar(period)),
        "gap": round(revpar(period) - nrevpar(period)),
    }


def departmental_profit(period: str, department: str, basis: str = "preAllocation") -> dict:
    """온톨로지 DepartmentalProfit — basis가 preAllocation/postAllocation 둘 다 명시적으로 요구된다 (함정 ②)."""
    if period != "2026-12":
        raise MetricError("부문별 손익 상세 데이터는 2026-12 기준만 보유하고 있습니다.")
    if department not in data.DEPARTMENTS_2026_12:
        raise MetricError(f"'{department}' 부문이 없습니다. 사용 가능: {list(data.DEPARTMENTS_2026_12)}")
    if basis not in ("preAllocation", "postAllocation"):
        raise MetricError("basis는 'preAllocation' 또는 'postAllocation' 중 하나여야 합니다 — 둘을 구분하지 않으면 함정 ②(이익률 30% vs 5%)에 빠집니다.")

    dept = data.DEPARTMENTS_2026_12[department]
    pre_profit = dept["revenue"] - dept["direct_cost"]

    if basis == "preAllocation":
        return {"basis": basis, "profit": pre_profit, "margin": round(pre_profit / dept["revenue"], 4)}

    total_revenue = sum(d["revenue"] for d in data.DEPARTMENTS_2026_12.values())
    total_undistributed = sum(data.UNDISTRIBUTED_EXPENSE_2026_12.values())
    allocated_share = total_undistributed * (dept["revenue"] / total_revenue)  # ALLOCATION_BASIS = revenue
    post_profit = pre_profit - allocated_share
    return {
        "basis": basis,
        "profit": round(post_profit),
        "margin": round(post_profit / dept["revenue"], 4),
        "allocated_undistributed_expense": round(allocated_share),
    }


def gop(period: str) -> dict:
    """GOP = 부문 이익(배부 전) 합계 − 미배부 공통비. 호텔 전체 1개 숫자만 존재한다."""
    if period != "2026-12":
        raise MetricError("GOP는 2026-12 기준 데이터만 보유하고 있습니다.")
    total_profit = sum(d["revenue"] - d["direct_cost"] for d in data.DEPARTMENTS_2026_12.values())
    total_undistributed = sum(data.UNDISTRIBUTED_EXPENSE_2026_12.values())
    return {
        "departmental_profit_sum": total_profit,
        "undistributed_expense": total_undistributed,
        "gop": total_profit - total_undistributed,
    }


def goppar(period: str) -> float:
    """GOP ÷ 가용객실. 호텔 전체 범위에만 존재 — department 파라미터를 애초에 받지 않는다 (함정 ③)."""
    return gop(period)["gop"] / available_rooms(period)


def flow_through(period_current: str, period_prior: str, department: str | None = None) -> dict:
    """Δ이익 ÷ Δ매출. 두 기간이 반드시 있어야 계산할 수 있다 (함정 ④)."""
    if period_current == period_prior:
        raise MetricError("Flow-through는 서로 다른 두 기간이 필요합니다 (전년 대비 등).")

    if department is None:
        if period_current != "2026-12" or period_prior != "2025-12":
            raise MetricError("전사 Flow-through는 2025-12 → 2026-12 비교만 지원합니다.")
        curr_revenue = sum(d["revenue"] for d in data.DEPARTMENTS_2026_12.values())
        curr_profit = gop(period_current)["gop"]
        prior_revenue = data.PRIOR_YEAR_2025_12["total_revenue"]
        prior_profit = data.PRIOR_YEAR_2025_12["total_gop"]
    elif department == "FB":
        if period_current != "2026-12" or period_prior != "2025-12":
            raise MetricError("F&B Flow-through는 2025-12 → 2026-12 비교만 지원합니다.")
        curr_revenue = data.DEPARTMENTS_2026_12["FB"]["revenue"]
        curr_profit = departmental_profit(period_current, "FB", "preAllocation")["profit"]
        prior_revenue = data.PRIOR_YEAR_2025_12["FB_revenue"]
        prior_profit = data.PRIOR_YEAR_2025_12["FB_profit"]
    else:
        raise MetricError("department는 None(전사) 또는 'FB'만 지원합니다 (현재 샘플 데이터 범위).")

    delta_revenue = curr_revenue - prior_revenue
    delta_profit = curr_profit - prior_profit
    return {
        "delta_revenue": delta_revenue,
        "delta_profit": delta_profit,
        "flow_through": round(delta_profit / delta_revenue, 4) if delta_revenue else None,
    }


def food_cost_rate(period: str) -> dict:
    """실제 원가율은 항상 표준 원가율과 함께 반환한다 (함정 ⑤ — 단독으로 보지 말 것)."""
    if period != "2026-12":
        raise MetricError("F&B 원가 데이터는 2026-12 기준만 보유하고 있습니다.")
    fb = data.FB_COST_2026_12
    actual_rate = fb["actual_food_cost"] / fb["food_revenue"]
    standard_rate = fb["standard_food_cost_rate"]
    standard_cost = fb["food_revenue"] * standard_rate
    leakage = fb["actual_food_cost"] - standard_cost
    return {
        "actual_rate": round(actual_rate, 4),
        "standard_rate": round(standard_rate, 4),
        "gap_pp": round((actual_rate - standard_rate) * 100, 2),
        "leakage_amount": round(leakage),
    }


def market_benchmark_indices(period: str) -> dict:
    """MPI / ARI / RGI."""
    if period != "2026-12":
        raise MetricError("시장 벤치마크 데이터는 2026-12 기준만 보유하고 있습니다.")
    mb = data.MARKET_BENCHMARK_2026_12
    mpi = occ(period) / mb["market_occ"] * 100
    ari = adr(period) / mb["market_adr"] * 100
    rgi = revpar(period) / mb["market_revpar"] * 100
    return {"mpi": round(mpi, 1), "ari": round(ari, 1), "rgi": round(rgi, 1)}
