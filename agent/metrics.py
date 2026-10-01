"""1.3 온톨로지(hotel-ontology.md)의 Metric 정의를 구현한 결정론적 계산 함수들.

2023-01~2026-12(48개월) 전 기간에 대해 동작한다 — 특정 월로 제한하지 않는다.
원칙(온톨로지 0장): 계산은 전부 여기서 코드로 하고, LLM에게 숫자 계산을 맡기지 않는다.
"""

from . import data


class MetricError(Exception):
    """존재하지 않는 기간·부문을 요청하는 등 제약 위반 시 사용."""


def _inventory(period: str) -> dict:
    if period not in data.ROOM_INVENTORY:
        raise MetricError(f"'{period}' 기간 데이터가 없습니다. 사용 가능 범위: {data.AVAILABLE_PERIODS[0]} ~ {data.AVAILABLE_PERIODS[-1]}")
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
    inv = _inventory(period)
    commission = ota_commission(period)
    return (inv["revenue"] - commission) / inv["sold_rooms"]


def nrevpar(period: str) -> float:
    inv = _inventory(period)
    commission = ota_commission(period)
    return (inv["revenue"] - commission) / available_rooms(period)


def channel_mix(period: str) -> dict:
    """진단용 보조 지표 — OTA 비중과 RevPAR·NRevPAR 격차 (함정 ①)."""
    inv = _inventory(period)
    ota_ratio = inv["ota_sold_rooms"] / inv["sold_rooms"]
    return {
        "ota_room_ratio": round(ota_ratio, 4),
        "revpar": round(revpar(period)),
        "nrevpar": round(nrevpar(period)),
        "gap": round(revpar(period) - nrevpar(period)),
    }


def _departments(period: str) -> dict:
    if period not in data.DEPARTMENTS_BY_PERIOD:
        raise MetricError(f"'{period}' 기간의 부문 손익 데이터가 없습니다.")
    return data.DEPARTMENTS_BY_PERIOD[period]


def departmental_profit(period: str, department: str, basis: str = "preAllocation") -> dict:
    """온톨로지 DepartmentalProfit — basis가 preAllocation/postAllocation 둘 다 명시적으로 요구된다 (함정 ②)."""
    depts = _departments(period)
    if department not in depts:
        raise MetricError(f"'{department}' 부문이 없습니다. 사용 가능: {list(depts)}")
    if basis not in ("preAllocation", "postAllocation"):
        raise MetricError("basis는 'preAllocation' 또는 'postAllocation' 중 하나여야 합니다 — 둘을 구분하지 않으면 함정 ②(이익률 착시)에 빠집니다.")

    dept = depts[department]
    pre_profit = dept["revenue"] - dept["direct_cost"]

    if basis == "preAllocation":
        return {"basis": basis, "profit": pre_profit, "margin": round(pre_profit / dept["revenue"], 4)}

    total_revenue = sum(d["revenue"] for d in depts.values())
    total_undistributed = sum(data.UNDISTRIBUTED_EXPENSE_BY_PERIOD[period].values())
    allocated_share = total_undistributed * (dept["revenue"] / total_revenue)  # ALLOCATION_BASIS = revenue
    post_profit = pre_profit - allocated_share
    return {
        "basis": basis,
        "profit": round(post_profit),
        "margin": round(post_profit / dept["revenue"], 4),
        "allocated_undistributed_expense": round(allocated_share),
    }


def gop(period: str) -> dict:
    """GOP = 부문 이익(배부 전) 합계 − 미배부 공통비."""
    depts = _departments(period)
    total_profit = sum(d["revenue"] - d["direct_cost"] for d in depts.values())
    total_undistributed = sum(data.UNDISTRIBUTED_EXPENSE_BY_PERIOD[period].values())
    return {
        "departmental_profit_sum": total_profit,
        "undistributed_expense": total_undistributed,
        "gop": total_profit - total_undistributed,
    }


def goppar(period: str) -> float:
    """GOP ÷ 가용객실. 호텔 전체 범위에만 존재 — department 파라미터를 애초에 받지 않는다 (함정 ③)."""
    return gop(period)["gop"] / available_rooms(period)


def flow_through(period_current: str, period_prior: str, department: str | None = None) -> dict:
    """Δ이익 ÷ Δ매출. 두 기간이 반드시 있어야 계산할 수 있다 (함정 ④) — 임의의 두 기간을 비교할 수 있다."""
    if period_current == period_prior:
        raise MetricError("Flow-through는 서로 다른 두 기간이 필요합니다 (전년 동월, 전월 등).")

    if department is None:
        curr_revenue = sum(d["revenue"] for d in _departments(period_current).values())
        curr_profit = gop(period_current)["gop"]
        prior_revenue = sum(d["revenue"] for d in _departments(period_prior).values())
        prior_profit = gop(period_prior)["gop"]
    else:
        curr_revenue = _departments(period_current)[department]["revenue"]
        curr_profit = departmental_profit(period_current, department, "preAllocation")["profit"]
        prior_revenue = _departments(period_prior)[department]["revenue"]
        prior_profit = departmental_profit(period_prior, department, "preAllocation")["profit"]

    delta_revenue = curr_revenue - prior_revenue
    delta_profit = curr_profit - prior_profit
    return {
        "delta_revenue": delta_revenue,
        "delta_profit": delta_profit,
        "flow_through": round(delta_profit / delta_revenue, 4) if delta_revenue else None,
    }


def food_cost_rate(period: str) -> dict:
    """실제 원가율은 항상 표준 원가율과 함께 반환한다 (함정 ⑤ — 단독 판단 금지)."""
    if period not in data.FB_COST_BY_PERIOD:
        raise MetricError(f"'{period}' 기간의 F&B 원가 데이터가 없습니다.")
    fb = data.FB_COST_BY_PERIOD[period]
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
    if period not in data.MARKET_BENCHMARK_BY_PERIOD:
        raise MetricError(f"'{period}' 기간의 시장 벤치마크 데이터가 없습니다.")
    mb = data.MARKET_BENCHMARK_BY_PERIOD[period]
    mpi = occ(period) / mb["market_occ"] * 100
    ari = adr(period) / mb["market_adr"] * 100
    rgi = revpar(period) / mb["market_revpar"] * 100
    return {"mpi": round(mpi, 1), "ari": round(ari, 1), "rgi": round(rgi, 1)}


def attach_rate(year: int, matched_only: bool = True) -> dict:
    """F&B attach rate = F&B 이용(매출>0) 고객-연 레코드 수 ÷ 전체 고객-연 레코드 수.

    matched_only=True면 고객 통합키가 매핑된(integration_key_matched='Y') 레코드만 쓴다
    (온톨로지 6장 — CLV·attach rate는 매핑율이 신뢰도를 좌우한다).
    """
    matched_ids = {c["customer_id"] for c in data.CUSTOMERS if c["integration_key_matched"] == "Y"}
    rows = [u for u in data.CUSTOMER_USAGE if u["year"] == year]
    if matched_only:
        rows = [u for u in rows if u["customer_id"] in matched_ids]
    if not rows:
        raise MetricError(f"{year}년 고객 이용 데이터가 없습니다.")
    attached = sum(1 for u in rows if u["fb_revenue"] > 0)
    return {
        "year": year, "matched_only": matched_only,
        "customer_year_records": len(rows), "attached": attached,
        "attach_rate": round(attached / len(rows), 4),
    }


def clv(matched_only: bool = True) -> dict:
    """고객 전체가치(2023~2026 누적) — 객실+F&B 매출 합계를 고객별로 더한 평균.

    매핑이 안 된 고객은 여러 시스템의 이용 기록이 한 사람으로 합쳐지지 않으므로,
    matched_only=False로 두면 "매핑 안 된 고객은 개별 방문마다 별도 고객으로 과소 산정된다"는
    왜곡이 어떻게 평균을 낮추는지 비교해볼 수 있다.
    """
    matched_ids = {c["customer_id"] for c in data.CUSTOMERS if c["integration_key_matched"] == "Y"}
    totals: dict[str, int] = {}
    for u in data.CUSTOMER_USAGE:
        if matched_only and u["customer_id"] not in matched_ids:
            continue
        totals[u["customer_id"]] = totals.get(u["customer_id"], 0) + u["room_revenue"] + u["fb_revenue"]
    if not totals:
        raise MetricError("집계할 고객 데이터가 없습니다.")
    values = list(totals.values())
    return {
        "matched_only": matched_only, "customer_count": len(values),
        "average_clv": round(sum(values) / len(values)),
        "max_clv": max(values), "min_clv": min(values),
    }
