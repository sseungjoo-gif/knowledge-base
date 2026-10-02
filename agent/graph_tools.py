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
