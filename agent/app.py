"""워커힐 호텔 추정/추론 에이전트 — 웹 채팅 UI (Streamlit).

실행:
    cd "D:\\knowledge\\files (2)"
    py -m streamlit run agent/app.py
"""

import os
import sys

# `streamlit run agent/app.py`로 실행하면 이 파일이 패키지 밖에서 단독 스크립트로 열리므로,
# 프로젝트 루트를 sys.path에 넣어서 `agent.agent`를 일반 패키지로 import할 수 있게 한다.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

from agent.agent import run_turn

st.set_page_config(page_title="워커힐 추정/추론 에이전트", page_icon="🏨", layout="centered")
st.title("🏨 워커힐 호텔 성과관리 추정/추론 에이전트")
st.caption("1.3 온톨로지 + Neo4j 그래프 + 샘플데이터(2023~2026) 기반. 모든 수치는 가상 데이터입니다.")

if "messages" not in st.session_state:
    st.session_state.messages = []       # API에 보내는 실제 대화 이력
if "display" not in st.session_state:
    st.session_state.display = []        # 화면에 그릴 (role, text, tool_calls, image_paths, usage)
if "session_cost_usd" not in st.session_state:
    st.session_state.session_cost_usd = 0.0

with st.sidebar:
    st.metric("이번 세션 누적 비용(추정)", f"${st.session_state.session_cost_usd:.4f}")
    st.caption(
        "대화 이력이 길어질수록 질문 1건당 비용도 같이 올라갑니다 — "
        "판단 근거 후속질문처럼 이전 답변을 이어서 물을 게 아니면 자주 눌러서 리셋하세요."
    )
    if st.button("🔄 새 대화 시작 (이력 초기화)", use_container_width=True):
        st.session_state.messages = []
        st.session_state.display = []
        st.session_state.session_cost_usd = 0.0
        st.rerun()

for turn in st.session_state.display:
    with st.chat_message(turn["role"]):
        st.markdown(turn["text"])
        for path in turn.get("image_paths", []):
            if os.path.exists(path):
                st.image(path)
        if turn.get("tool_calls"):
            with st.expander(f"도구 호출 {len(turn['tool_calls'])}건"):
                for call in turn["tool_calls"]:
                    st.code(f"{call['name']}({call['input']})", language="python")
        if turn.get("usage"):
            u = turn["usage"]
            st.caption(f"입력 {u['input_tokens']:,} + 출력 {u['output_tokens']:,} 토큰 ≈ ${u['cost_usd']:.4f}")

question = st.chat_input("질문을 입력하세요 (예: RevPAR랑 NRevPAR 차이가 왜 나는거야?)")

if question:
    with st.chat_message("user"):
        st.markdown(question)
    st.session_state.display.append({"role": "user", "text": question})

    with st.chat_message("assistant"):
        with st.spinner("분석 중... (도구 호출·그래프 조회·차트 생성에 시간이 걸릴 수 있습니다)"):
            result = run_turn(st.session_state.messages, question)
        st.session_state.messages = result["messages"]
        st.session_state.session_cost_usd += result["usage"]["cost_usd"]

        st.markdown(result["text"])
        for path in result["image_paths"]:
            if os.path.exists(path):
                st.image(path)
        if result["tool_calls"]:
            with st.expander(f"도구 호출 {len(result['tool_calls'])}건"):
                for call in result["tool_calls"]:
                    st.code(f"{call['name']}({call['input']})", language="python")
        u = result["usage"]
        st.caption(f"입력 {u['input_tokens']:,} + 출력 {u['output_tokens']:,} 토큰 ≈ ${u['cost_usd']:.4f}")

    st.session_state.display.append({
        "role": "assistant",
        "text": result["text"],
        "tool_calls": result["tool_calls"],
        "image_paths": result["image_paths"],
        "usage": result["usage"],
    })
    st.rerun()
