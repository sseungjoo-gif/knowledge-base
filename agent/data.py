"""워커힐 호텔 성과관리 샘플 데이터 — agent/sample_data_gen.py에서 생성한 48개월(2023-01~2026-12) 데이터를
그대로 불러와 metrics.py가 바로 쓸 수 있는 형태로 노출한다.

실제 숫자/배부 규칙은 전부 sample_data_gen.py에 있고, 여기서는 재생성하지 않도록
모듈 로드 시 한 번만 build_all()을 호출해 캐싱한다 (난수 시드가 고정돼 있어 재현 가능).
"""

from . import sample_data_gen as _gen

_DATA = _gen.build_all()

ROOM_COUNT = _gen.ROOM_COUNT
OTA_COMMISSION_RATE = _gen.OTA_COMMISSION_RATE
ALLOCATION_BASIS = _gen.ALLOCATION_BASIS

ROOM_INVENTORY = _DATA["room_inventory"]
DEPARTMENTS_BY_PERIOD = _DATA["department_pl"]
UNDISTRIBUTED_EXPENSE_BY_PERIOD = _DATA["undistributed_expense"]
FB_COST_BY_PERIOD = _DATA["fb_cost"]
MARKET_BENCHMARK_BY_PERIOD = _DATA["market_benchmark"]
CUSTOMERS = _DATA["customers"]
CUSTOMER_USAGE = _DATA["customer_usage"]

AVAILABLE_PERIODS = list(ROOM_INVENTORY.keys())  # "2023-01" ~ "2026-12", 48개
