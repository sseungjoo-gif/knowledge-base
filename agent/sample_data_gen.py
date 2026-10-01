"""워커힐 호텔 가상 샘플 데이터 생성기 (2023-01 ~ 2026-12, 48개월).

전부 가상의 데이터이며, 1.1(hotel-metrics.md)·1.3(hotel-ontology.md)과 연속성을 갖도록
2026-12 한 달만은 1.1의 예시 숫자와 정확히 일치하게 고정(anchor)하고, 나머지 47개월은
아래 규칙(배부 기준 등)에 따라 추세·계절성·약간의 노이즈를 섞어 만들었다.

이 모듈이 "진실의 원천"이며, agent/data.py(에이전트가 쓰는 데이터)와
agent/build_sample_excel.py(다운로드용 엑셀)가 둘 다 여기서 값을 가져온다.
"""

import random

# ── 고정 규칙(배부 기준) — 1.4 샘플데이터 문서에도 동일하게 기재 ──────────────
ROOM_COUNT = 500
OTA_COMMISSION_RATE = 0.18          # OTA 판매분에 대한 채널 수수료율 (1.1과 동일 가정)
ROOMS_FIXED_COST_RATIO = 0.145      # 객실 직접비 중 수수료를 뺀 고정 운영비 비율 (하우스키핑·소모품·인건비 등)
DEPT_COST_RATIO = {"FB": 0.70, "Banquet": 0.625, "Other": 0.25}  # 부문 직접비 ÷ 부문 매출
UNDISTRIBUTED_RATIO = {"관리": 0.0882, "마케팅": 0.0588, "시설": 0.0441, "에너지": 0.0588}  # ÷ 부문 매출 합계
STANDARD_FOOD_COST_RATE = 0.32      # 표준원가율(양목표 기준) — 전 기간 고정 정책값
ALLOCATION_BASIS = "revenue"        # 공통비 배부 기준 = 부문 매출 비례

MONTH_SEASONALITY = {
    1: 0.94, 2: 0.93, 3: 0.97, 4: 1.00, 5: 1.03, 6: 0.98,
    7: 1.05, 8: 1.06, 9: 1.00, 10: 1.02, 11: 0.98, 12: 1.08,
}

CUSTOMER_SEGMENTS = ["개인레저", "개인비즈니스", "기업", "단체", "MICE", "컴프"]
SEGMENT_WEIGHTS = [0.40, 0.20, 0.15, 0.10, 0.10, 0.05]

_rng = random.Random(42)


def _months():
    out = []
    for y in (2023, 2024, 2025, 2026):
        for m in range(1, 13):
            out.append((y, m))
    return out


MONTHS = _months()  # 48개, index 0~47 (2023-01 ~ 2026-12)
ANCHOR_INDEX = len(MONTHS) - 1  # 2026-12


def label(y, m):
    return f"{y:04d}-{m:02d}"


def _days_in_month(y, m):
    import calendar
    return calendar.monthrange(y, m)[1]


def _lerp(t, a, b):
    return a + (b - a) * t


def _noise(center=1.0, sigma=0.03, lo=0.9, hi=1.1):
    return max(lo, min(hi, _rng.gauss(center, sigma)))


# ── 2026-12 고정값 (1.1 hotel-metrics.md과 동일) ──────────────────────────
ANCHOR_ROOM = {"days": 30, "sold_rooms": 12_000, "revenue": 3_600_000_000,
               "ota_sold_rooms": 7_000, "ota_revenue": 2_100_000_000}
ANCHOR_DEPT = {
    "Rooms":   {"revenue": 3_600_000_000, "direct_cost": 900_000_000},
    "FB":      {"revenue": 2_000_000_000, "direct_cost": 1_400_000_000},
    "Banquet": {"revenue":   800_000_000, "direct_cost":   500_000_000},
    "Other":   {"revenue":   400_000_000, "direct_cost":   100_000_000},
}
ANCHOR_UNDIST = {"관리": 600_000_000, "마케팅": 400_000_000, "시설": 300_000_000, "에너지": 400_000_000}
ANCHOR_FB_COST = {"food_revenue": 2_000_000_000, "actual_food_cost": 700_000_000,
                   "standard_food_cost_rate": 0.32}
ANCHOR_MARKET = {"market_occ": 0.72, "market_adr": 270_000, "market_revpar": 194_400}


def generate_room_inventory():
    """월별 객실 재고/판매. OCC 68%→80%, ADR 25.5만→30만, OTA비중 35%→58.3% 추세."""
    out = {}
    for i, (y, m) in enumerate(MONTHS):
        lbl = label(y, m)
        days = _days_in_month(y, m)
        if i == ANCHOR_INDEX:
            out[lbl] = {"days": days, **ANCHOR_ROOM}
            continue

        t = i / ANCHOR_INDEX
        season = MONTH_SEASONALITY[m]
        available = ROOM_COUNT * days

        occ = _lerp(t, 0.68, 0.80) * (0.85 + 0.15 * season) * _noise(sigma=0.025)
        occ = max(0.55, min(0.93, occ))
        sold_rooms = round(available * occ)

        adr = _lerp(t, 255_000, 300_000) * (0.9 + 0.1 * season) * _noise(sigma=0.02)
        revenue = round(sold_rooms * adr)

        ota_ratio = max(0.25, min(0.65, _lerp(t, 0.35, 0.5833) * _noise(sigma=0.04)))
        ota_sold_rooms = round(sold_rooms * ota_ratio)
        ota_revenue = round(ota_sold_rooms * adr * _noise(center=1.0, sigma=0.015))

        out[lbl] = {
            "days": days, "sold_rooms": sold_rooms, "revenue": revenue,
            "ota_sold_rooms": ota_sold_rooms, "ota_revenue": ota_revenue,
        }
    return out


def generate_department_pl(room_inventory):
    """부문별 매출·직접비. FB/연회/기타는 객실 매출 대비 비율로 산출(배부 기준 = 매출 비례)."""
    out = {}
    for i, (y, m) in enumerate(MONTHS):
        lbl = label(y, m)
        if i == ANCHOR_INDEX:
            out[lbl] = {k: dict(v) for k, v in ANCHOR_DEPT.items()}
            continue

        t = i / ANCHOR_INDEX
        rooms_revenue = room_inventory[lbl]["revenue"]
        ota_commission = room_inventory[lbl]["ota_revenue"] * OTA_COMMISSION_RATE
        rooms_direct_cost = round(ota_commission + ROOMS_FIXED_COST_RATIO * rooms_revenue)

        fb_ratio = _lerp(t, 0.40, 0.5556) * _noise(sigma=0.03)
        banquet_ratio = _lerp(t, 0.15, 0.2222) * _noise(sigma=0.04)
        other_ratio = _lerp(t, 0.09, 0.1111) * _noise(sigma=0.03)

        fb_revenue = round(rooms_revenue * fb_ratio)
        banquet_revenue = round(rooms_revenue * banquet_ratio)
        other_revenue = round(rooms_revenue * other_ratio)

        out[lbl] = {
            "Rooms":   {"revenue": rooms_revenue, "direct_cost": rooms_direct_cost},
            "FB":      {"revenue": fb_revenue, "direct_cost": round(fb_revenue * DEPT_COST_RATIO["FB"])},
            "Banquet": {"revenue": banquet_revenue, "direct_cost": round(banquet_revenue * DEPT_COST_RATIO["Banquet"])},
            "Other":   {"revenue": other_revenue, "direct_cost": round(other_revenue * DEPT_COST_RATIO["Other"])},
        }
    return out


def generate_undistributed_expense(department_pl):
    """미배부 공통비 = 부문 매출 합계 × 카테고리별 고정 비율."""
    out = {}
    for i, (y, m) in enumerate(MONTHS):
        lbl = label(y, m)
        if i == ANCHOR_INDEX:
            out[lbl] = dict(ANCHOR_UNDIST)
            continue
        total_revenue = sum(d["revenue"] for d in department_pl[lbl].values())
        out[lbl] = {cat: round(total_revenue * ratio * _noise(sigma=0.02))
                     for cat, ratio in UNDISTRIBUTED_RATIO.items()}
    return out


def generate_fb_cost(department_pl):
    """F&B 식자재 원가. 표준원가율은 전 기간 고정(32%), 실제원가율은 평소 표준 근방이다가
    2026년 하반기에 누수가 누적되어 12월에 35%로 정점을 찍는 시나리오."""
    out = {}
    for i, (y, m) in enumerate(MONTHS):
        lbl = label(y, m)
        if i == ANCHOR_INDEX:
            out[lbl] = dict(ANCHOR_FB_COST)
            continue

        food_revenue = department_pl[lbl]["FB"]["revenue"]
        rate = STANDARD_FOOD_COST_RATE + _rng.gauss(0.0, 0.01)
        if y == 2026 and m >= 9:            # 하반기 누수 누적 구간
            rate += _lerp((m - 9) / 3, 0.0, 0.03)
        if (y, m) == (2024, 7):              # 과거 1회성 원자재 가격 충격
            rate += 0.04
        rate = max(0.27, min(0.37, rate))

        out[lbl] = {
            "food_revenue": food_revenue,
            "actual_food_cost": round(food_revenue * rate),
            "standard_food_cost_rate": STANDARD_FOOD_COST_RATE,
        }
    return out


def generate_market_benchmark(room_inventory):
    """경쟁 Comp Set 벤치마크(가상). 자사 대비 약 90% 수준으로 움직여 MPI·ARI·RGI가 110~125 사이."""
    out = {}
    for i, (y, m) in enumerate(MONTHS):
        lbl = label(y, m)
        if i == ANCHOR_INDEX:
            out[lbl] = dict(ANCHOR_MARKET)
            continue
        days = room_inventory[lbl]["days"]
        occ = room_inventory[lbl]["sold_rooms"] / (ROOM_COUNT * days)
        adr = room_inventory[lbl]["revenue"] / room_inventory[lbl]["sold_rooms"]
        market_occ = round(occ / 1.111 * _noise(sigma=0.02), 4)
        market_adr = round(adr / 1.111 * _noise(sigma=0.02))
        out[lbl] = {
            "market_occ": market_occ,
            "market_adr": market_adr,
            "market_revpar": round(market_occ * market_adr),
        }
    return out


def generate_customers(n=300):
    customers = []
    for i in range(1, n + 1):
        segment = _rng.choices(CUSTOMER_SEGMENTS, weights=SEGMENT_WEIGHTS, k=1)[0]
        nationality = _rng.choices(["내국인", "외국인"], weights=[0.75, 0.25], k=1)[0]
        tier = _rng.choices(["일반", "실버", "골드", "VIP"], weights=[0.55, 0.25, 0.15, 0.05], k=1)[0]
        matched = _rng.choices(["Y", "N"], weights=[0.70, 0.30], k=1)[0]  # 가정 매핑율 70% (실측 아님)
        customers.append({
            "customer_id": f"CUS-{i:04d}",
            "segment": segment,
            "nationality": nationality,
            "membership_tier": tier,
            "integration_key_matched": matched,
        })
    return customers


_SEGMENT_NIGHTS = {  # (평균 연간 숙박일수, 표준편차)
    "개인레저": (3, 1.5), "개인비즈니스": (5, 2), "기업": (8, 3),
    "단체": (12, 4), "MICE": (6, 2), "컴프": (2, 1),
}
_SEGMENT_FB_ATTACH_P = {
    "개인레저": 0.55, "개인비즈니스": 0.35, "기업": 0.40,
    "단체": 0.70, "MICE": 0.75, "컴프": 0.20,
}


def generate_customer_annual_usage(customers, adr_by_year):
    rows = []
    for c in customers:
        for year in (2023, 2024, 2025, 2026):
            if _rng.random() > 0.6:  # 해당 연도에 비활성(미방문) 고객
                continue
            mean_nights, sd = _SEGMENT_NIGHTS[c["segment"]]
            nights = max(0, round(_rng.gauss(mean_nights, sd)))
            if nights == 0:
                continue
            adr = adr_by_year[year] * _noise(sigma=0.08)
            if c["segment"] == "컴프":
                room_revenue = 0
            else:
                discount = 0.85 if c["segment"] in ("기업", "단체", "MICE") else 1.0
                room_revenue = round(nights * adr * discount)

            attach_p = _SEGMENT_FB_ATTACH_P[c["segment"]]
            fb_revenue = 0
            if _rng.random() < attach_p:
                fb_revenue = round(nights * _rng.gauss(90_000, 30_000))
                fb_revenue = max(0, fb_revenue)

            channel = _rng.choices(["OTA", "Direct"], weights=[0.5, 0.5], k=1)[0]
            rows.append({
                "customer_id": c["customer_id"], "year": year, "room_nights": nights,
                "room_revenue": room_revenue, "fb_revenue": fb_revenue, "channel": channel,
            })
    return rows


def build_all():
    room_inventory = generate_room_inventory()
    department_pl = generate_department_pl(room_inventory)
    undistributed = generate_undistributed_expense(department_pl)
    fb_cost = generate_fb_cost(department_pl)
    market_benchmark = generate_market_benchmark(room_inventory)
    customers = generate_customers()
    adr_by_year = {}
    for year in (2023, 2024, 2025, 2026):
        decs = [room_inventory[label(year, m)]["revenue"] / room_inventory[label(year, m)]["sold_rooms"]
                for m in range(1, 13)]
        adr_by_year[year] = sum(decs) / len(decs)
    usage = generate_customer_annual_usage(customers, adr_by_year)
    return {
        "room_inventory": room_inventory,
        "department_pl": department_pl,
        "undistributed_expense": undistributed,
        "fb_cost": fb_cost,
        "market_benchmark": market_benchmark,
        "customers": customers,
        "customer_usage": usage,
    }
