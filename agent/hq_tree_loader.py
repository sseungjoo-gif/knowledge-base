"""전개표.xlsx의 질문 계보(HQ→SQ→DQ→BQ→KPI→Dataset→Gap)를 그래프에 적재한다.

- 구조(엣지)는 HQ-1~7_전개표 시트의 "경로" 컬럼에서 뽑는다. 경로는 각 행의 전체 조상 ID 체인을
  " › "로 이어둔 문자열이라, 여기서 정규식으로 "정식 ID"(HQ-/SQ-/DQ-/BQ-/KPI-/D-/G-)만 남기고
  나머지(L0/L1/L2, 층2 USALI 같은 분해축 라벨, "(신설)")는 걸러낸 뒤 연속한 두 개씩을 엣지로 만든다.
  분해축 라벨은 ID가 전역적으로 유일하지 않아(L1이 여러 의미로 재사용됨) 그래프 노드로 올리면
  서로 다른 개념이 하나로 합쳐지는 오류가 생기므로, 이번 적재에서는 의도적으로 제외한다.
- 속성(판정·우선순위 등)은 구조와 분리해서, 전용 목록 시트에서 가져온다 — HQ-N 시트 안에서는 같은
  컬럼 위치가 행 종류에 따라 의미가 달라져서(예: Gap 행에서는 "수치·상태" 칸에 우선순위가 들어있음)
  신뢰하기 어렵다. HQ/SQ/DQ/BQ/KPI는 HQ-N 시트 자신에서, Dataset/Gap은 "필요데이터 목록"·
  "보유/미보유데이터 목록" 시트에서 가져온다.

실행:
    cd "D:\\knowledge\\files (2)"
    py -m agent.hq_tree_loader
"""

import re

import openpyxl

from .graph_loader import get_driver

XLSX_PATH = "전개표.xlsx"

ID_PATTERNS = [
    r"^HQ-\d+$", r"^SQ-\d+$", r"^DQ-[\d.]+$", r"^BQ-[\d.\-]+$",
    r"^KPI-[A-Za-z0-9\-]+$", r"^D-\d+$", r"^G-[A-Za-z0-9]+$",
]


def _well_formed(seg: str) -> bool:
    seg = seg.strip()
    return any(re.match(p, seg) for p in ID_PATTERNS)


def _label_for(item_id: str) -> str:
    if item_id.startswith("HQ-"):
        return "HQ"
    if item_id.startswith("SQ-"):
        return "SQ"
    if item_id.startswith("DQ-"):
        return "DQ"
    if item_id.startswith("BQ-"):
        return "BQ"
    if item_id.startswith("KPI-"):
        return "KPI"
    if item_id.startswith("D-"):
        return "Dataset"
    if item_id.startswith("G-"):
        return "Gap"
    return "Unknown"


def _sheet_rows(ws, header_row=1):
    rows = list(ws.iter_rows(values_only=True))
    headers = rows[header_row - 1]
    out = []
    for r in rows[header_row:]:
        if all(c is None for c in r):
            continue
        out.append({h: v for h, v in zip(headers, r) if h is not None})
    return out


def parse_hq_trees(wb):
    """HQ-1~7_전개표에서 (노드 속성 업데이트들, 엣지 집합)을 뽑는다."""
    node_updates = {}  # id -> dict(props)
    edges = set()

    for sheet_name in [f"HQ-{i}_전개표" for i in range(1, 8)]:
        ws = wb[sheet_name]
        for row in _sheet_rows(ws):
            item_id = row.get("항목 ID")
            path = row.get("경로")
            if not item_id or not path:
                continue
            item_id = str(item_id).strip()

            # HQ/SQ/DQ/BQ/KPI 타입 판별 (어느 컬럼이 채워져 있는지로 결정)
            text = None
            for col in ("HQ", "SQ", "DQ", "BQ", "지표"):
                v = row.get(col)
                if v:
                    text = str(v).strip()
                    break

            if text is not None:  # HQ/SQ/DQ/BQ/KPI 중 하나인 행
                props = node_updates.setdefault(item_id, {})
                props["id"] = item_id
                props["text"] = text
                if row.get("판정"):
                    props["status"] = row["판정"]
                if row.get("수치·상태"):
                    props["valueState"] = row["수치·상태"]
                if row.get("산출 · 판정 기준"):
                    props["criteria"] = row["산출 · 판정 기준"]
                if row.get("해결 조건"):
                    props["resolution"] = row["해결 조건"]

            segments = [s.strip() for s in str(path).split("›")]
            chain = [s for s in segments if _well_formed(s)]
            for a, b in zip(chain, chain[1:]):
                edges.add((a, b))

    return node_updates, edges


def parse_kpi_registry(wb):
    ws = wb["KPI 보유 목록"]
    out = {}
    for row in _sheet_rows(ws, header_row=3):
        kpi_id = row.get("KPI ID")
        if not kpi_id:
            continue
        out[kpi_id] = {
            "id": kpi_id,
            "family": row.get("지표군"),
            "name": row.get("지표명"),
            "axis": row.get("소속 축"),
            "valueStateControlled": row.get("값 상태(통제)"),
            "status": row.get("보유 판정"),
            "rationale": row.get("판정 근거"),
        }
    return out


def parse_dataset_registry(wb):
    ws = wb["필요데이터 목록"]
    out = {}
    for row in _sheet_rows(ws, header_row=3):
        d_id = row.get("D ID")
        if not d_id:
            continue
        out[d_id] = {
            "id": d_id,
            "name": row.get("데이터 항목"),
            "grain": row.get("데이터 구조"),
            "frequency": row.get("필요 주기"),
            "status": row.get("보유 판정"),
            "linkedGaps": row.get("연결 GAP"),
            "impactIfMissing": row.get("없으면 무엇이 막히나"),
        }
    return out


def parse_gap_registry(wb):
    out = {}
    for sheet_name, has_action in [("보유데이터 목록", False), ("미보유데이터 목록", True)]:
        ws = wb[sheet_name]
        for row in _sheet_rows(ws, header_row=3):
            g_id = row.get("GAP ID")
            if not g_id:
                continue
            out[g_id] = {
                "id": g_id,
                "priority": row.get("우선순위"),
                "name": row.get("갭 항목 · 필요 데이터"),
                "status": row.get("판정"),
                "sourceInfo": row.get("보유 현황 · 원천"),
                "affectedQuestions": row.get("영향 질문"),
                "action": row.get("조치") if has_action else None,
            }
    return out


def parse_hq_summary(wb):
    ws = wb["HQ Summary"]
    out = {}
    for row in _sheet_rows(ws, header_row=1):
        hq_id = row.get("HQ")
        if not hq_id:
            continue
        out[hq_id] = {
            "id": hq_id,
            "text": row.get("지주사 질문"),
            "lever": row.get("Lever"),
            "decisionMaker": row.get("결정권자"),
        }
    return out


def load(driver):
    wb = openpyxl.load_workbook(XLSX_PATH, data_only=True)

    node_updates, edges = parse_hq_trees(wb)
    kpis = parse_kpi_registry(wb)
    datasets = parse_dataset_registry(wb)
    gaps = parse_gap_registry(wb)
    hq_summary = parse_hq_summary(wb)

    # HQ Summary가 더 정확한 질문문/Lever를 갖고 있으므로 덮어쓴다
    for hq_id, props in hq_summary.items():
        node_updates.setdefault(hq_id, {})["id"] = hq_id
        node_updates[hq_id].update({k: v for k, v in props.items() if v})

    # KPI/Dataset/Gap은 전용 목록이 더 정확하므로 그걸로 교체한다
    for kpi_id, props in kpis.items():
        node_updates[kpi_id] = {**node_updates.get(kpi_id, {}), **props}
    for d_id, props in datasets.items():
        node_updates[d_id] = {**node_updates.get(d_id, {}), **props}
    for g_id, props in gaps.items():
        node_updates[g_id] = {**node_updates.get(g_id, {}), **props}

    rows_by_label = {}
    for item_id, props in node_updates.items():
        label = _label_for(item_id)
        rows_by_label.setdefault(label, []).append(props)

    with driver.session() as session:
        session.run("MATCH (n:HQ|SQ|DQ|BQ|KPI|Dataset|Gap) DETACH DELETE n")

        for label, rows in rows_by_label.items():
            if label == "Unknown":
                continue
            session.run(
                f"""
                UNWIND $rows AS row
                MERGE (n:{label} {{id: row.id}})
                SET n += row
                """,
                rows=rows,
            )

        edge_rows = [{"a": a, "b": b} for a, b in edges]
        session.run(
            """
            UNWIND $rows AS row
            MATCH (a {id: row.a})
            MATCH (b {id: row.b})
            MERGE (a)-[:LEADS_TO]->(b)
            """,
            rows=edge_rows,
        )

    return {
        "nodes": sum(len(v) for v in rows_by_label.values()),
        "edges": len(edges),
        "by_label": {k: len(v) for k, v in rows_by_label.items()},
    }


if __name__ == "__main__":
    driver = get_driver()
    summary = load(driver)
    print(summary)
    driver.close()
