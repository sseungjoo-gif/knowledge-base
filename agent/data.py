"""워커힐 호텔 성과관리 샘플 데이터.

1.1(hotel-metrics.md)의 예시 숫자를 기준(2026-12)으로 삼고,
온톨로지(1.3 hotel-ontology.md)의 함정 ①⑤를 재현하도록 몇 개월치 시나리오를 추가했다.

- 2025-12: 전년 동기 (Flow-through 비교 기준)
- 2026-10, 2026-11: OTA 비중이 점점 올라가는 트렌드 (RevPAR는 그대로인데 NRevPAR만 빠지는 함정 ①)
- 2026-12: 1.1의 기준 월 (부문 손익·공통비 배부·식자재 원가 누수까지 전부 포함)
"""

ROOM_COUNT = 500

# 기간별 재고/판매 (객실 부문 전용)
ROOM_INVENTORY = {
    "2026-10": {"days": 31, "sold_rooms": 11_780, "revenue": 3_430_000_000, "ota_sold_rooms": 5_890, "ota_revenue": 1_715_000_000},
    "2026-11": {"days": 30, "sold_rooms": 11_850, "revenue": 3_495_000_000, "ota_sold_rooms": 7_110, "ota_revenue": 2_097_000_000},
    "2026-12": {"days": 30, "sold_rooms": 12_000, "revenue": 3_600_000_000, "ota_sold_rooms": 7_000, "ota_revenue": 2_100_000_000},
}

OTA_COMMISSION_RATE = 0.18

# 부문별 매출·직접비 (2026-12 기준, 1.1 4장 표와 동일)
DEPARTMENTS_2026_12 = {
    "Rooms":   {"revenue": 3_600_000_000, "direct_cost": 900_000_000},   # 직접비에 OTA 수수료 3.78억 포함
    "FB":      {"revenue": 2_000_000_000, "direct_cost": 1_400_000_000},
    "Banquet": {"revenue":   800_000_000, "direct_cost":   500_000_000},
    "Other":   {"revenue":   400_000_000, "direct_cost":   100_000_000},
}

UNDISTRIBUTED_EXPENSE_2026_12 = {
    "관리": 600_000_000,
    "마케팅": 400_000_000,
    "시설": 300_000_000,
    "에너지": 400_000_000,
}

ALLOCATION_BASIS = "revenue"  # 배부 기준: 매출 비례

# 전년 동기 (Flow-through 비교용, 1.1 7장과 동일한 총액만 보유)
PRIOR_YEAR_2025_12 = {
    "total_revenue": 6_000_000_000,
    "total_gop": 2_000_000_000,
    "FB_revenue": 1_600_000_000,
    "FB_profit": 540_000_000,
}

# F&B 원가 (2026-12, 1.1 3장과 동일) — 식자재원가율 함정 ⑤
FB_COST_2026_12 = {
    "food_revenue": 2_000_000_000,
    "actual_food_cost": 700_000_000,       # 실제원가율 35%
    "standard_food_cost_rate": 0.32,       # 표준원가율 32%
}

# 시장 벤치마크 (2026-12, STR 유사 데이터) — MPI·ARI·RGI 계산용
MARKET_BENCHMARK_2026_12 = {
    "market_occ": 0.72,
    "market_adr": 270_000,
    "market_revpar": 194_400,
}
