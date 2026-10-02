"""그래프 DB(Neo4j)를 Claude 도구로 노출한다.

metrics.py(결정론적 계산)와 역할을 나눈다:
- 숫자 계산(OCC·GOP·Flow-through 등)은 여전히 metrics.py 도구를 쓴다.
- "이 질문은 어느 KPI로 연결되나", "이 Gap이 막고 있는 BQ가 뭔가" 같이 미리 만들어둔
  함수가 없는 탐색형 질문은 이 Cypher 도구로 그래프를 직접 조회한다.
"""

import re

from anthropic import beta_tool

from .graph_loader import get_driver

_WRITE_KEYWORDS = re.compile(
    r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP|DETACH|CALL\s+apoc\.|LOAD\s+CSV)\b",
    re.IGNORECASE,
)

_driver = None


def _get_driver():
    global _driver
    if _driver is None:
        _driver = get_driver()
    return _driver


@beta_tool
def run_cypher_query(query: str) -> dict:
    """그래프 DB에 읽기 전용 Cypher 쿼리를 실행한다 (쓰기 금지).

    그래프 스키마:
      노드 — Hotel, Period(년월별 OCC·ADR·매출·OTA·시장벤치마크·F&B원가 속성 보유),
             Department, DepartmentPeriodFact(기간×부문 매출·직접비),
             UndistributedExpense(기간×카테고리), Customer, CustomerUsage,
             HQ/SQ/DQ/BQ(전략 질문 계보), KPI(id·family·name·axis·status·valueState 등),
             Dataset(id·name·grain·status·impactIfMissing), Gap(id·priority·status·action 등)
      관계 — (Hotel)-[:HAS_PERIOD]->(Period),
             (Period)-[:HAS_DEPT_FACT]->(DepartmentPeriodFact)-[:FOR_DEPARTMENT]->(Department),
             (Period)-[:HAS_UNDISTRIBUTED]->(UndistributedExpense),
             (Customer)-[:USAGE_IN_YEAR]->(CustomerUsage),
             (HQ|SQ|DQ|BQ|KPI|Dataset|Gap)-[:LEADS_TO]->(다음 단계) — 질문 계보를 따라간다

    Args:
        query: 읽기 전용 Cypher 쿼리 (MATCH/RETURN/WHERE/WITH 등만 — CREATE·MERGE·DELETE·SET 금지).
    """
    if _WRITE_KEYWORDS.search(query):
        return {"error": "쓰기 쿼리는 허용되지 않습니다. MATCH/RETURN 중심의 읽기 쿼리만 쓸 수 있습니다."}
    try:
        with _get_driver().session() as session:
            result = session.run(query)
            rows = [dict(r) for r in result]
            return {"row_count": len(rows), "rows": rows[:50]}
    except Exception as e:  # noqa: BLE001 — Cypher 문법 오류 등을 그대로 모델에게 보여준다
        return {"error": str(e)}


def _fetch_lineage(node_id: str):
    """node_id까지의 (루트에서부터의) 조상 경로 하나와, node_id 아래의 전체 하위 트리 엣지를 가져온다."""
    with _get_driver().session() as session:
        anc = session.run(
            """
            MATCH path = (root)-[:LEADS_TO*0..]->(n {id: $id})
            WHERE NOT ( ()-[:LEADS_TO]->(root) )
            RETURN [x IN nodes(path) | properties(x)] AS chain
            ORDER BY length(path) ASC LIMIT 1
            """,
            id=node_id,
        ).single()
        ancestor_chain = anc["chain"] if anc and anc["chain"] else None

        edges = session.run(
            """
            MATCH (n {id: $id})
            OPTIONAL MATCH (n)-[:LEADS_TO*1..]->(d)
            WITH n, collect(DISTINCT d) AS descendants
            WITH [n] + descendants AS scope
            UNWIND scope AS s
            MATCH (s)-[:LEADS_TO]->(c)
            RETURN s.id AS parent, properties(c) AS child
            """,
            id=node_id,
        ).data()

    if ancestor_chain is None:
        self_props = {"id": node_id}
        with _get_driver().session() as session:
            r = session.run("MATCH (n {id: $id}) RETURN properties(n) AS p", id=node_id).single()
            if r:
                self_props = r["p"]
        ancestor_chain = [self_props]

    children_by_parent: dict = {}
    node_props: dict = {p["id"]: p for p in ancestor_chain}
    for e in edges:
        children_by_parent.setdefault(e["parent"], []).append(e["child"]["id"])
        node_props[e["child"]["id"]] = e["child"]

    return ancestor_chain, children_by_parent, node_props


def _label(props: dict) -> str:
    text = props.get("text") or props.get("name") or props.get("id")
    status = props.get("status")
    return f"{text} [{status}]" if status else str(text)


def _render_subtree(node_id, children_by_parent, node_props, prefix, is_last, depth, max_depth=10):
    connector = "└─ " if is_last else "├─ "
    line = prefix + connector + _label(node_props.get(node_id, {"id": node_id}))
    lines = [line]
    if depth >= max_depth:
        return lines
    child_prefix = prefix + ("    " if is_last else "│   ")
    kids = children_by_parent.get(node_id, [])
    for i, kid in enumerate(kids):
        lines.extend(_render_subtree(kid, children_by_parent, node_props, child_prefix, i == len(kids) - 1, depth + 1, max_depth))
    return lines


@beta_tool
def get_judgment_basis(node_id: str) -> dict:
    """사용자가 "판단 근거를 알려줘"처럼 물으면, 방금 답변에 쓴 KPI/Dataset/Gap/BQ 등의 id로
    이 도구를 호출한다. 그 노드가 어떤 전략 질문(HQ)에서 내려왔는지(위쪽 경로)와, 그 판단이
    어떤 데이터·갭에 근거했는지(아래쪽 하위 트리)를 트리 구조 텍스트로 보여준다.

    Args:
        node_id: HQ-3, BQ-1.1-1, KPI-FT-05, G-01 등 조회할 노드의 id.
    """
    ancestor_chain, children_by_parent, node_props = _fetch_lineage(node_id)

    lines = []
    prefix = ""
    for i, props in enumerate(ancestor_chain):
        connector = "" if i == 0 else "└─ "
        lines.append(prefix + connector + _label(props))
        prefix += "   "

    kids = children_by_parent.get(node_id, [])
    for i, kid in enumerate(kids):
        lines.extend(_render_subtree(kid, children_by_parent, node_props, prefix, i == len(kids) - 1, depth=1))

    return {"tree": "\n".join(lines)}
