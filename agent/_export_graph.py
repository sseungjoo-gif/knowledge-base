"""공유용 Artifact에 내장할 질문 계보 그래프(HQ..Gap, LEADS_TO)를 JSON으로 뽑아내는 스크립트.
hq_tree_loader.py와 동일한 파싱 로직이지만 Neo4j에 올리지 않고 노드/엣지를 그대로 JSON으로 덤프한다."""
import json
import os
import re

import openpyxl

XLSX_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "전개표.xlsx")

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
    node_updates = {}
    edges = set()
    for sheet_name in [f"HQ-{i}_전개표" for i in range(1, 8)]:
        ws = wb[sheet_name]
        for row in _sheet_rows(ws):
            item_id = row.get("항목 ID")
            path = row.get("경로")
            if not item_id or not path:
                continue
            item_id = str(item_id).strip()

            text = None
            for col in ("HQ", "SQ", "DQ", "BQ", "지표"):
                v = row.get(col)
                if v:
                    text = str(v).strip()
                    break

            if text is not None:
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
            "id": kpi_id, "family": row.get("지표군"), "name": row.get("지표명"),
            "axis": row.get("소속 축"), "valueStateControlled": row.get("값 상태(통제)"),
            "status": row.get("보유 판정"), "rationale": row.get("판정 근거"),
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
            "id": d_id, "name": row.get("데이터 항목"), "grain": row.get("데이터 구조"),
            "frequency": row.get("필요 주기"), "status": row.get("보유 판정"),
            "linkedGaps": row.get("연결 GAP"), "impactIfMissing": row.get("없으면 무엇이 막히나"),
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
                "id": g_id, "priority": row.get("우선순위"), "name": row.get("갭 항목 · 필요 데이터"),
                "status": row.get("판정"), "sourceInfo": row.get("보유 현황 · 원천"),
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
            "id": hq_id, "text": row.get("지주사 질문"),
            "lever": row.get("Lever"), "decisionMaker": row.get("결정권자"),
        }
    return out


def main():
    wb = openpyxl.load_workbook(XLSX_PATH, data_only=True)

    node_updates, edges = parse_hq_trees(wb)
    kpis = parse_kpi_registry(wb)
    datasets = parse_dataset_registry(wb)
    gaps = parse_gap_registry(wb)
    hq_summary = parse_hq_summary(wb)

    for hq_id, props in hq_summary.items():
        node_updates.setdefault(hq_id, {})["id"] = hq_id
        node_updates[hq_id].update({k: v for k, v in props.items() if v})

    for kpi_id, props in kpis.items():
        node_updates[kpi_id] = {**node_updates.get(kpi_id, {}), **props}
    for d_id, props in datasets.items():
        node_updates[d_id] = {**node_updates.get(d_id, {}), **props}
    for g_id, props in gaps.items():
        node_updates[g_id] = {**node_updates.get(g_id, {}), **props}

    nodes = []
    for item_id, props in node_updates.items():
        label = _label_for(item_id)
        if label == "Unknown":
            continue
        nodes.append({"label": label, **props})

    edge_rows = [{"a": a, "b": b} for a, b in edges if a in node_updates and b in node_updates]

    out = {"nodes": nodes, "edges": edge_rows}
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_export_graph.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, default=str, separators=(",", ":"))

    by_label = {}
    for n in nodes:
        by_label[n["label"]] = by_label.get(n["label"], 0) + 1
    print("wrote", out_path, os.path.getsize(out_path), "bytes")
    print("nodes:", len(nodes), "edges:", len(edge_rows), "by_label:", by_label)


if __name__ == "__main__":
    main()
