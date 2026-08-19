import streamlit as st
from openai import OpenAI

st.set_page_config(
    page_title="EMMOTHER Travel AI",
    page_icon="✈️",
    layout="wide"
)

st.title("✈️ EMMOTHER Travel AI")
st.caption("여행 CPA 블로그 글쓰기 AI")

# OpenAI API 연결
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.divider()

# -------------------------
# 입력 영역
# -------------------------

keyword = st.text_input(
    "메인 키워드",
    placeholder="예: 발리 가족여행 숙소 추천"
)

content_type = st.selectbox(
    "글 유형",
    [
        "숙소 추천",
        "여행 일정",
        "투어 추천",
        "여행 준비물",
        "맛집 추천",
        "카페 추천",
        "여행지 후기",
        "기타"
    ]
)

travel_info = st.text_area(
    "가지고 있는 여행 정보",
    placeholder="""예:
까자네 무아
- 우붓에 위치
- 가족여행에 적합
- 수영장 있음
- 조식 이용
- 객실 넓음
- 2025년에 직접 방문""",
    height=220
)

cpa_type = st.multiselect(
    "넣고 싶은 CPA",
    [
        "숙소 예약",
        "투어 예약",
        "공항 픽업",
        "eSIM",
        "여행용품",
        "기타"
    ]
)

generate = st.button(
    "✨ 여행 CPA 글 생성",
    use_container_width=True
)

# -------------------------
# AI 글 생성
# -------------------------

if generate:

    if not keyword:
        st.warning("메인 키워드를 입력해주세요.")
        st.stop()

    prompt = f"""
너는 네이버 블로그 여행 콘텐츠 전문 에디터다.

사용자는 '4인1견 가족, 유모차 특공대'라는
가족여행 블로그를 운영하고 있다.

블로그의 핵심 독자는
아이와 함께 여행하는 부모이며,
여행 정보를 실제 예약과 구매로 연결하는
CPA 콘텐츠가 중요한 목적이다.

다음 정보를 기반으로 여행 블로그 글을 작성한다.

[메인 키워드]
{keyword}

[글 유형]
{content_type}

[사용자가 가진 실제 여행 정보]
{travel_info}

[사용할 CPA]
{", ".join(cpa_type) if cpa_type else "없음"}

작성 규칙:

1. 메인 키워드를 중심으로 검색 의도를 먼저 파악한다.

2. 제목 후보를 5개 만든다.
   - 검색 키워드를 자연스럽게 포함한다.
   - 클릭하고 싶은 제목으로 만든다.
   - 과도한 낚시성 제목은 사용하지 않는다.

3. 가장 적합한 제목 1개를 추천한다.

4. 목차를 만든다.

5. 네이버 블로그에 바로 붙여넣을 수 있는
   자연스러운 본문을 작성한다.

6. 글은 정보 전달이 우선이며,
   억지로 키워드를 반복하지 않는다.

7. 가족여행자의 관점에서
   아이 동반 시 중요한 정보를 강조한다.

8. 실제 경험 정보가 제공된 경우
   그것을 중심으로 작성한다.

9. 제공되지 않은 가격, 운영시간, 주소,
   이용요금 등의 정보를 임의로 만들어내지 않는다.

10. CPA가 있는 경우
    독자가 예약을 결정하기 좋은 위치에
    자연스럽게 CTA를 제안한다.

11. 마지막에 관련 글 내부링크를 넣기 좋은
    위치와 앵커텍스트를 3개 제안한다.

다음 형식으로 출력한다.

[제목 후보 5개]

1.
2.
3.
4.
5.

[추천 제목]

[목차]

[본문]

[CPA CTA 제안]

[내부링크 제안]
"""

    with st.spinner("AI가 여행 글을 작성하고 있습니다..."):

        response = client.responses.create(
            model="gpt-5-mini",
            input=prompt
        )

        result = response.output_text

    st.divider()

    st.subheader("📝 생성된 여행 CPA 글")

    st.text_area(
        "결과",
        result,
        height=900
    )

    st.success("글 생성 완료!")
