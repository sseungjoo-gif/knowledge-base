"""워커힐 호텔 성과관리 추정/추론 에이전트.

1.3 온톨로지(hotel-ontology.md)를 기준으로 동작한다:
- 숫자 계산은 전부 도구(tools.py → metrics.py)가 하고, 모델은 해석/진단만 한다.
- 온톨로지 6장의 함정 방지 제약을 시스템 프롬프트로도 한 번 더 명시해 둔다.

실행:
    cd "D:\\knowledge\\files (2)"
    py -m agent.agent "RevPAR는 그대로인데 왜 실수익이 떨어졌어?"
"""

import os
import sys

import anthropic
from dotenv import load_dotenv

from .tools import ALL_TOOLS

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "outputs")

# 서버 도구. web_search(기본형)와 code_execution을 같이 쓴다 — 최신(동적 필터링) web_search는
# 내부적으로 code_execution을 자체적으로 돌려서, 차트 생성용 code_execution과 같이 선언하면
# "실행 환경이 두 개"로 모델이 혼동할 수 있다는 경고가 있어 기본형으로 고정했다.
SERVER_TOOLS = [
    {"type": "web_search_20250305", "name": "web_search", "max_uses": 3},
    {"type": "code_execution_20260120", "name": "code_execution"},
]

SYSTEM_PROMPT = """\
당신은 워커힐 호텔의 성과관리 추정/추론 에이전트입니다.
1.3 온톨로지(hotel-ontology.md) 기준으로 동작하며, 아래 원칙을 반드시 지킵니다.

[도구를 두 종류로 나눠 씁니다]
- 숫자 계산(OCC·ADR·GOP·Flow-through·CLV 등)은 반드시 전용 계산 도구를 호출해서 얻습니다.
  도구가 없는 계산(임의의 산술)을 본문에서 직접 수행하지 않습니다.
- "이 질문이 어느 KPI로 연결되나", "이 KPI는 어떤 Gap 때문에 막혀있나", "이 Gap이 어떤 BQ에
  영향을 주나" 같이 전용 계산 도구가 없는 탐색형/무작위 질문은 run_cypher_query로 그래프를
  직접 조회합니다 (그래프 스키마는 그 도구 설명에 있습니다). 질문 계보는 HQ→SQ→DQ→BQ→KPI→
  Dataset→Gap 순으로 LEADS_TO 관계를 따라갑니다.

[원칙]
1. 어떤 기간/부문 데이터가 있는지 모르면 먼저 list_available_data를 호출합니다.
2. 다음 6가지 제약을 항상 지킵니다 (1.3 온톨로지 6장과 동일):
   ① 매출만 보고 수수료 유출을 판단하지 않습니다 — RevPAR와 NRevPAR를 항상 같이 봅니다.
   ② 부문 이익을 말할 때는 배부 전(preAllocation)·배부 후(postAllocation)를 반드시 구분해서 밝힙니다.
   ③ GOPPAR는 호텔 전체 지표입니다. 특정 부문(F&B 등)의 성과를 GOPPAR로 평가하지 않습니다.
   ④ Flow-through는 반드시 두 기간 비교가 있어야 계산됩니다. 한 기간만으로는 계산하지 않습니다.
   ⑤ 식자재 원가율은 표준원가율과 반드시 같이 제시합니다.
   ⑥ CLV·attach rate는 integration_key_matched=Y(매핑된) 고객만 신뢰도가 높습니다 — matched_only
      기본값을 그대로 쓰고, 매핑 안 된 고객까지 섞으면 왜곡될 수 있다는 점을 밝힙니다.
3. HQ 질문 계보에서 KPI·Dataset·Gap의 status가 "미보유"/"부분보유"이면, 숫자를 계산해서 보여주더라도
   "실제 판정은 OO 상태"라고 같이 밝힙니다 — 1.3 8절처럼 "지금 샘플은 actual 가정, 실제 운영 데이터는
   이 갭이 해소돼야 신뢰 가능"이라는 점을 분명히 합니다.
4. 답변은 항상 아래 3단 구조로 씁니다.
   - **결론**: 질문에 대한 답을 숫자/판정과 함께 한두 문장으로 먼저 제시
   - **원인**: 1.1 문서 톤처럼 원인을 분해해서 설명 (물량/단가/채널/원가 등 — 왜 그런 결론이 나왔는지)
   - **해결방법(제안)**: 할 수 있는 대응·다음 행동을 구체적으로 제시 (데이터 갭이 원인이면 어떤 갭부터
     해소해야 하는지, 지표 악화가 원인이면 어떤 조치를 검토할지 등)
5. 추정이 필요한 질문(예: "다음 달엔 어떨까")에는 최근 추세(여러 기간 도구 호출 결과)를 근거로 들되,
   "추정"이라는 점과 그 근거를 명시적으로 밝힙니다. 근거 없는 숫자를 단정적으로 말하지 않습니다.
6. 해결방법(제안)에 **향후 추정**을 항상 같이 넣습니다 — 지금 추세가 이어진다면 다음 달/다음 분기가
   어떻게 될지, 어떤 조치를 하면 어떻게 달라질지를 "추정"이라고 밝히고 근거(어떤 기간 데이터를
   봤는지)와 함께 제시합니다.
7. 해결방법·advice에 외부 맥락(날씨·뉴스·시장 동향 등)이 실제로 도움이 될 질문이면 web_search
   도구로 찾아보고 근거로 씁니다. 호텔 성과 자체는 내부 데이터로 설명하고, web_search는 "왜
   외부 환경이 이렇게 영향을 줬는지"를 보강할 때만 보조적으로 씁니다.
8. 기간·부문 등을 비교하는 숫자가 2개 이상이면, 말로만 나열하지 말고 code_execution(matplotlib)으로
   막대·꺾은선 차트를 그려서 보여줍니다. 생성된 이미지 파일은 저장되고, 어디에 저장됐는지 답변에
   알려줍니다. 비교 항목이 2~3개뿐이고 추이가 중요하지 않으면 표로 대체해도 됩니다.
"""


def _save_generated_files(client, message) -> None:
    for block in message.content:
        if block.type != "bash_code_execution_tool_result":
            continue
        result = block.content
        if getattr(result, "type", None) != "bash_code_execution_result" or not result.content:
            continue
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        for file_ref in result.content:
            if file_ref.type != "bash_code_execution_output":
                continue
            metadata = client.beta.files.retrieve_metadata(file_ref.file_id)
            safe_name = os.path.basename(metadata.filename)
            if not safe_name or safe_name in (".", ".."):
                continue
            out_path = os.path.join(OUTPUT_DIR, safe_name)
            client.beta.files.download(file_ref.file_id).write_to_file(out_path)
            print(f"\n[파일 저장] {out_path}")


def ask(question: str) -> None:
    client = anthropic.Anthropic()

    runner = client.beta.messages.tool_runner(
        model="claude-opus-5",
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        tools=ALL_TOOLS + SERVER_TOOLS,
        messages=[{"role": "user", "content": question}],
    )

    for message in runner:
        _save_generated_files(client, message)
        for block in message.content:
            if block.type == "text":
                print(block.text)
            elif block.type == "tool_use":
                print(f"\n[도구 호출] {block.name}({block.input})")
            elif block.type == "server_tool_use":
                print(f"\n[서버 도구] {block.name}: {block.input}")


def main() -> None:
    if len(sys.argv) > 1:
        ask(" ".join(sys.argv[1:]))
        return

    print("워커힐 호텔 추정/추론 에이전트 (종료: Ctrl+C)")
    while True:
        try:
            question = input("\n질문> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question:
            continue
        ask(question)


if __name__ == "__main__":
    main()
