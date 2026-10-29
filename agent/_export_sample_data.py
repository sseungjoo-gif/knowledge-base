"""공유용 Artifact에 내장할 샘플 데이터를 JSON으로 한 번 뽑아내는 스크립트.
sample_data_gen.py는 시드(42)가 고정돼 있어 재현 가능 — 여기서 한 번 실행한 결과를
정적 JSON으로 굳혀서 JS에서 그대로 쓴다 (JS에서 Python random을 재구현할 필요 없음)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import sample_data_gen as gen

data = gen.build_all()
data["_meta"] = {
    "room_count": gen.ROOM_COUNT,
    "ota_commission_rate": gen.OTA_COMMISSION_RATE,
    "standard_food_cost_rate": gen.STANDARD_FOOD_COST_RATE,
    "allocation_basis": gen.ALLOCATION_BASIS,
    "undistributed_ratio": gen.UNDISTRIBUTED_RATIO,
}

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_export_sample_data.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

print("wrote", out_path, os.path.getsize(out_path), "bytes")
print("periods:", len(data["room_inventory"]), "customers:", len(data["customers"]), "usage_rows:", len(data["customer_usage"]))
