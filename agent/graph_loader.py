"""1.3 온톨로지의 클래스를 그래프 스키마로 옮기고, sample_data_gen.py의 데이터를 Neo4j(AuraDB)에 적재한다.

노드: Hotel, Period(48개월, 월별 스칼라 사실 전부 보유), Department(4),
      DepartmentPeriodFact(기간×부문), UndistributedExpense(기간×카테고리),
      Customer(300), CustomerUsage(연도별 이용)
관계: Hotel-[:HAS_PERIOD]->Period, Period-[:HAS_DEPT_FACT]->DepartmentPeriodFact-[:FOR_DEPARTMENT]->Department,
      Period-[:HAS_UNDISTRIBUTED]->UndistributedExpense, Customer-[:USAGE_IN_YEAR]->CustomerUsage

GOP·GOPPAR·Flow-through 같은 파생 지표는 그래프에 저장하지 않고, 필요할 때 Cypher 집계로 계산한다
(1.3 0장 원칙 — 사실과 지표를 분리).

실행:
    cd "D:\\knowledge\\files (2)"
    py -m agent.graph_loader
"""

import os

from dotenv import load_dotenv
from neo4j import GraphDatabase

from . import sample_data_gen as gen

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

URI = os.getenv("NEO4J_URI")
USER = os.getenv("NEO4J_USER")
PASSWORD = os.getenv("NEO4J_PASSWORD")


def get_driver():
    return GraphDatabase.driver(URI, auth=(USER, PASSWORD))


def load(driver):
    data = gen.build_all()

    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")  # 매번 깨끗하게 재적재 (idempotent)

        session.run(
            "MERGE (h:Hotel {name: 'Walkerhill'}) SET h.roomCount = $roomCount",
            roomCount=gen.ROOM_COUNT,
        )

        for dept in ["Rooms", "FB", "Banquet", "Other"]:
            session.run("MERGE (:Department {name: $name})", name=dept)

        period_rows = []
        for lbl, inv in data["room_inventory"].items():
            y, m = lbl.split("-")
            mb = data["market_benchmark"][lbl]
            fb = data["fb_cost"][lbl]
            period_rows.append({
                "label": lbl, "year": int(y), "month": int(m),
                "days": inv["days"], "availableRooms": gen.ROOM_COUNT * inv["days"],
                "soldRooms": inv["sold_rooms"], "roomRevenue": inv["revenue"],
                "otaSoldRooms": inv["ota_sold_rooms"], "otaRevenue": inv["ota_revenue"],
                "marketOcc": mb["market_occ"], "marketAdr": mb["market_adr"],
                "marketRevpar": mb["market_revpar"],
                "fbFoodRevenue": fb["food_revenue"], "fbActualFoodCost": fb["actual_food_cost"],
                "fbStandardRate": fb["standard_food_cost_rate"],
            })
        session.run(
            """
            UNWIND $rows AS row
            MATCH (h:Hotel {name: 'Walkerhill'})
            MERGE (p:Period {label: row.label})
            SET p += row
            MERGE (h)-[:HAS_PERIOD]->(p)
            """,
            rows=period_rows,
        )

        dept_fact_rows = []
        undist_rows = []
        for lbl, depts in data["department_pl"].items():
            for dept, v in depts.items():
                dept_fact_rows.append({
                    "period": lbl, "department": dept,
                    "revenue": v["revenue"], "directCost": v["direct_cost"],
                })
            for cat, amt in data["undistributed_expense"][lbl].items():
                undist_rows.append({"period": lbl, "category": cat, "amount": amt})

        session.run(
            """
            UNWIND $rows AS row
            MATCH (p:Period {label: row.period})
            MATCH (d:Department {name: row.department})
            MERGE (f:DepartmentPeriodFact {period: row.period, department: row.department})
            SET f.revenue = row.revenue, f.directCost = row.directCost
            MERGE (p)-[:HAS_DEPT_FACT]->(f)
            MERGE (f)-[:FOR_DEPARTMENT]->(d)
            """,
            rows=dept_fact_rows,
        )

        session.run(
            """
            UNWIND $rows AS row
            MATCH (p:Period {label: row.period})
            MERGE (u:UndistributedExpense {period: row.period, category: row.category})
            SET u.amount = row.amount
            MERGE (p)-[:HAS_UNDISTRIBUTED]->(u)
            """,
            rows=undist_rows,
        )

        session.run(
            """
            UNWIND $rows AS row
            MERGE (c:Customer {customerId: row.customer_id})
            SET c.segment = row.segment, c.nationality = row.nationality,
                c.membershipTier = row.membership_tier,
                c.integrationKeyMatched = row.integration_key_matched
            """,
            rows=data["customers"],
        )

        session.run(
            """
            UNWIND $rows AS row
            MATCH (c:Customer {customerId: row.customer_id})
            CREATE (u:CustomerUsage {
                year: row.year, roomNights: row.room_nights,
                roomRevenue: row.room_revenue, fbRevenue: row.fb_revenue, channel: row.channel
            })
            MERGE (c)-[:USAGE_IN_YEAR]->(u)
            """,
            rows=data["customer_usage"],
        )


if __name__ == "__main__":
    driver = get_driver()
    load(driver)
    with driver.session() as session:
        rows = session.run(
            "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY label"
        ).data()
        for row in rows:
            print(row["label"], row["n"])
    driver.close()
