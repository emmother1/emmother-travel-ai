import streamlit as st
from openai import OpenAI
import requests
import json

st.set_page_config(
    page_title="EMMOTHER Travel AI",
    page_icon="✈️",
    layout="wide"
)

st.title("✈️ EMMOTHER Travel AI")
st.caption("4인1견 가족여행 블로그 전용 · 여행 CPA 콘텐츠 제작")

# -------------------------
# OpenAI
# -------------------------

client = OpenAI(
    api_key=st.secrets["OPENAI_API_KEY"]
)

# =========================
# EMMOTHER 콘텐츠 DB 불러오기
# =========================

with open("content_db.json", "r", encoding="utf-8") as f:
    content_db = json.load(f)

style_rules = content_db.get("style_rules", {})
style_samples = content_db.get("style_samples", [])
saved_posts = content_db.get("posts", [])
# ------------------------
# NAVER API
# ------------------------

NAVER_CLIENT_ID = st.secrets["NAVER_CLIENT_ID"]
NAVER_CLIENT_SECRET = st.secrets["NAVER_CLIENT_SECRET"]
# -------------------------
# 사용량 제한
# -------------------------

if "generation_count" not in st.session_state:
    st.session_state.generation_count = 0

MAX_GENERATIONS = 5

st.info(
    f"이번 세션 생성 횟수: "
    f"{st.session_state.generation_count}/{MAX_GENERATIONS}"
)

# -------------------------
# 입력
# -------------------------

st.subheader("① 콘텐츠 기본 설정")

keyword = st.text_input(
    "메인 키워드",
    placeholder="예: 발리 우붓 가족여행 숙소 추천"
)

content_type = st.selectbox(
    "글 유형",
    [
        "직접 방문 후기",
        "숙소 추천",
        "여행 일정",
        "여행지 추천",
        "맛집 후기",
        "카페 후기",
        "체험 후기",
        "여행 준비물",
        "여행 정보"
    ]
)

search_intent = st.selectbox(
    "검색 의도",
    [
        "후기·경험 확인",
        "추천·비교",
        "여행 일정 찾기",
        "이용 정보 확인",
        "예약·구매"
    ]
)

st.subheader("② 실제 여행 정보")

travel_info = st.text_area(
    "직접 경험했거나 확인한 정보",
    placeholder="""예:
카자네 무아
2025년 직접 방문
3박 숙박
우붓
프라이빗 풀빌라
객실 넓음
조식 이용
공용 수영장 이용
숙소 픽업 이용
아이와 함께 방문

※ 실제로 알고 있는 정보만 입력해주세요.""",
    height=260
)

st.subheader("③ 글에 넣을 정보")

important_points = st.text_area(
    "특히 강조하고 싶은 내용",
    placeholder="""예:
- 아이와 숙박하기 편했음
- 개인풀은 깊어서 주의 필요
- 공용풀이 아이와 놀기 좋았음
- 우붓 관광지 이동이 편했음""",
    height=180
)

cpa_type = st.multiselect(
    "CPA",
    [
        "숙소 예약",
        "투어 예약",
        "공항 픽업",
        "eSIM",
        "여행용품",
        "여행자보험"
    ]
)

related_posts = st.text_area(
    "내 블로그 관련 글",
    placeholder="""예:
발리 4박6일 가족여행 일정
우붓 가족여행 코스
발리 가족여행 숙소 추천 BEST 15
발리 여행 준비물""",
    height=140
)

st.subheader("④ 글 길이")

length = st.selectbox(
    "본문 분량",
    [
        "약 1,500자",
        "약 2,000자",
        "약 2,500자",
        "약 3,000자"
    ],
    index=2
)

generate = st.button(
    "✨ EMMOTHER 스타일로 글 생성",
    use_container_width=True
)

# -------------------------
# 생성
# -------------------------

if generate:

    if st.session_state.generation_count >= MAX_GENERATIONS:
        st.error(
            "이번 세션에서는 최대 5회까지 생성할 수 있어요."
        )
        st.stop()

    if not keyword:
        st.warning("메인 키워드를 입력해주세요.")
        st.stop()

    if not travel_info:
        st.warning("실제 여행 정보를 입력해주세요.")
        st.stop()
    # ------------------------
    # NAVER 블로그 검색
    # ------------------------

    naver_url = "https://naverapihub.apigw.ntruss.com/search/v1/blog"

    naver_headers = {
"X-NCP-APIGW-API-KEY-ID": NAVER_CLIENT_ID,
"X-NCP-APIGW-API-KEY": NAVER_CLIENT_SECRET
    }

    naver_params = {
    "query": keyword,
    "display": 10,
    "sort": "sim",
    "format": "json"
}

    try:
        naver_response = requests.get(
            naver_url,
            headers=naver_headers,
            params=naver_params,
            timeout=10
        )

        if naver_response.status_code == 200:
            naver_data = naver_response.json()

            naver_results = []

            for item in naver_data.get("items", []):
                naver_results.append(
                    f"""
제목: {item.get("title", "")}
설명: {item.get("description", "")}
블로그 URL: {item.get("link", "")}
"""
                )

            naver_context = "\n".join(naver_results)

        else:
            naver_context = "네이버 검색 결과를 가져오지 못했습니다."

    except Exception as e:
        naver_context = "네이버 검색 중 오류가 발생했습니다."
# =========================
# EMMOTHER 스타일 프롬프트
# =========================

style_prompt = f"""
[EMMOTHER 실제 블로그 스타일]

블로그명:
{style_rules.get("blog_name", "4인1견 가족, 유모차 특공대")}

작성자:
{style_rules.get("writer_name", "엠마더")}

말투:
{style_rules.get("tone", "")}

문체 규칙:
{chr(10).join("- " + x for x in style_rules.get("tone_rules", []))}

문장 스타일:
{chr(10).join("- " + x for x in style_rules.get("sentence_style", []))}

경험 서술:
{chr(10).join("- " + x for x in style_rules.get("experience_style", []))}

가족여행에서 중요하게 보는 내용:
{chr(10).join("- " + x for x in style_rules.get("family_travel_focus", []))}

기본정보 작성 규칙:
- 본문 초반에 기본정보를 표로 작성한다.
- 입력된 정보만 사용한다.
- 없는 정보는 추측하지 않는다.

소제목 스타일:
{style_rules.get("heading_style", {}).get("style", "")}

사진 표시:
{style_rules.get("photo_marker", {}).get("format", "[사진]")}

CTA 스타일:
{style_rules.get("cta_style", {}).get("style", "")}

마무리 스타일:
{style_rules.get("ending_style", {}).get("style", "")}
"""

sample_prompt = ""

for i, sample in enumerate(style_samples):
    sample_prompt += f"""
--- 실제 엠마더 글 스타일 샘플 {i + 1} ---
제목: {sample.get("title", "")}
글 유형: {sample.get("type", "")}

{sample.get("text", "")}

"""

prompt = f"""
너는 네이버 블로그 여행 콘텐츠를 작성하는
'EMMOTHER Travel Editor'다.

가장 중요한 것은 검색엔진용 AI 글을 만드는 것이 아니라
실제로 엠마더가 직접 작성한 것처럼 자연스러운 여행 블로그 글을 만드는 것이다.

{style_prompt}

{sample_prompt}

==================================================
[절대 지켜야 할 것]
==================================================

1. 사용자가 제공한 실제 경험과 정보만 사용한다.

2. 입력되지 않은 가격, 주소, 운영시간, 시설,
   서비스, 거리, 할인정보 등을 만들어내지 않는다.

3. AI가 검색의도를 분석한 것처럼 보이는 문장을
   실제 본문에 넣지 않는다.

4. "이 글에서는 ~ 알아보겠습니다."
   같은 전형적인 AI 도입 문장을 사용하지 않는다.

5. 검색 키워드를 억지로 반복하지 않는다.

6. 같은 표현을 계속 반복하지 않는다.

7. 모든 문장을 "~습니다"로 끝내지 않는다.

8. 실제 여행자가 이야기하듯 자연스럽게 작성한다.

9. 아이와 함께 여행하는 부모가 실제로 궁금해할
   내용을 우선해서 작성한다.

10. 장점만 나열하지 않는다.
    실제 정보에 아쉬운 점이나 주의점이 있다면 함께 작성한다.

11. 과장된 광고 표현을 사용하지 않는다.

12. CPA가 있더라도 광고문처럼 보이지 않게
    예약을 고민하는 자연스러운 시점에 CTA를 배치한다.

==================================================
[네이버 검색 최적화]
==================================================

메인 키워드를 제목에 자연스럽게 포함한다.

도입부에서 검색한 사람이 궁금해할 핵심 정보를
자연스럽게 알려준다.

주요 소제목에는 필요한 경우 관련 키워드를 사용한다.

키워드 반복보다 정보의 정확성과 자연스러움을 우선한다.

검색 상위노출을 보장한다고 표현하지 않는다.

==================================================
[본문 구조]
==================================================

글의 내용에 따라 자연스럽게 구성한다.

기본적인 흐름:

도입
↓
기본정보 표
↓
실제 이용 후기
↓
아이와 함께 이용한 경험
↓
좋았던 점
↓
아쉬운 점 / 주의사항
↓
이용 팁
↓
총평

단, 모든 글에 똑같은 구조를 강제로 적용하지 않는다.

==================================================
[사진]
==================================================

사진을 넣기 좋은 위치에

[사진]

이라고 표시한다.

==================================================
[출력 형식]
==================================================

# 제목 후보

1.
2.
3.
4.
5.

# 추천 제목

제목:

추천 이유:

# 네이버 검색용 핵심 구조

메인 키워드:
검색 의도:
독자가 가장 궁금해할 내용:

# 본문

여기부터는 네이버 블로그에 바로 복사해서 사용할 수 있는
실제 본문을 작성한다.

본문 안에서는 검색의도 분석이나 AI 관련 설명을 하지 않는다.

# CPA CTA

실제 글에 넣을 CTA 문구 2~3개.

# 내부링크

현재 제공된 관련 글 중 연결하기 좋은 글을 3개 제안한다.

# SEO 최종 점검

- 메인 키워드 자연스러운 사용
- 검색 의도 충족
- 실제 경험 중심
- 키워드 과다 반복 여부
- 정보 추측 여부
- 기본정보 표 작성 여부
- CPA CTA 위치
- 내부링크 기회

==================================================
[사용자 입력]
==================================================

메인 키워드:
{keyword}

글 유형:
{content_type}

검색 의도:
{search_intent}

실제 여행 정보:
{travel_info}

강조할 내용:
{important_points}

CPA:
{", ".join(cpa_type) if cpa_type else "없음"}

관련 글:
{related_posts}

본문 분량:
{length}
"""

    with st.spinner("EMMOTHER 스타일로 작성 중..."):

        try:

            response = client.responses.create(
                model="gpt-5-mini",
                input=prompt,
                max_output_tokens=7000
            )

            result = response.output_text

            st.session_state.generation_count += 1

            st.success("글 생성 완료!")

            st.divider()

            st.subheader("📝 생성 결과")

            st.text_area(
                "복사해서 사용할 수 있는 결과",
                result,
                height=1200
            )

            st.caption(
                f"이번 세션 사용 횟수: "
                f"{st.session_state.generation_count}/{MAX_GENERATIONS}"
            )

        except Exception as e:

            st.error(
                f"글 생성 중 오류가 발생했습니다: {type(e).__name__}"
            )
