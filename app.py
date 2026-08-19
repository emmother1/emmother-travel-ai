import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests
import streamlit as st
from openai import OpenAI


# =========================================================
# EMMOTHER Travel AI - 통합 버전
# =========================================================

st.set_page_config(
    page_title="EMMOTHER Travel AI",
    page_icon="✈️",
    layout="wide",
)

MAX_GENERATIONS = 5

CONTENT_TYPES = [
    "여행후기",
    "투어/액티비티 후기",
    "CPA 투어/액티비티 후기",
    "숙박후기",
    "CPA 숙박후기",
    "맛집리뷰",
    "제품리뷰",
    "정보성꿀팁",
    "프로모션숙소",
    "항공권 특가/프로모션",
    "비교글 (A vs B)",
    "렌터카",
]

PLATFORMS = [
    "없음",
    "마이리얼트립",
    "여기어때",
    "마이리얼트립 + 여기어때",
]

WRITING_MODES = ["후기형", "정보형"]
WRITING_STYLES = [
    "꼼꼼정보형",
    "감성분위기형",
    "솔직리뷰형",
    "가성비실속형",
]
LENGTHS = [
    "약 1,500자",
    "약 2,000자",
    "약 2,500자",
    "약 3,000자",
    "약 4,000자",
]


# =========================================================
# 공통 유틸
# =========================================================

def safe_text(value):
    if value is None:
        return ""
    return str(value).strip()


def load_content_db():
    try:
        with open("content_db.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_style_context():
    db = load_content_db()
    return json.dumps(db, ensure_ascii=False, indent=2)


def escape_md(value):
    value = safe_text(value)
    return value.replace("|", "\\|")


def normalize_url(url):
    url = safe_text(url)
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


# =========================================================
# 간단한 OpenGraph/HTML 메타 추출
# - 사이트 전체를 긁어오는 기능이 아니라
#   사용자가 직접 입력한 공개 상품 URL에서
#   제목/설명/대표 이미지 등의 메타정보를 읽어오는 보조 기능
# =========================================================

class MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.description = ""
        self.image = ""
        self.og_title = ""
        self.og_description = ""
        self.og_image = ""
        self.in_title = False
        self.title_chunks = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag.lower() == "title":
            self.in_title = True

        if tag.lower() == "meta":
            prop = attrs.get("property", "")
            name = attrs.get("name", "")
            content = attrs.get("content", "")

            if prop == "og:title":
                self.og_title = content
            elif prop == "og:description":
                self.og_description = content
            elif prop == "og:image":
                self.og_image = content
            elif name.lower() == "description":
                self.description = content

        if tag.lower() == "img" and not self.image:
            self.image = attrs.get("src", "")

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title_chunks.append(data)


def fetch_url_metadata(url):
    url = normalize_url(url)

    if not url:
        return {"error": "URL이 없습니다."}

    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/151 Safari/537.36"
                )
            },
            timeout=12,
        )
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type.lower():
            return {"error": "HTML 페이지가 아닙니다."}

        parser = MetaParser()
        parser.feed(response.text)

        title = (
            parser.og_title
            or "".join(parser.title_chunks).strip()
        )
        description = parser.og_description or parser.description
        image = parser.og_image or parser.image

        if image:
            image = urljoin(url, image)

        return {
            "url": url,
            "title": title,
            "description": description,
            "image": image,
        }

    except Exception as e:
        return {
            "error": f"{type(e).__name__}: {e}"
        }


# =========================================================
# 공식 페이지 링크
# - 실시간 TOP10/행사/도시별 페이지를 앱에서 보여주기 위한
#   공식 사이트 바로가기 모음.
# - 실제 상품 데이터 자동 연동은 제휴/API가 확보되면
#   별도 adapter로 교체할 수 있도록 분리.
# =========================================================

OFFICIAL_LINKS = {
    "마이리얼트립": [
        ("🎁 마이리얼트립 프로모션", "https://www.myrealtrip.com/promotions"),
        ("🔥 마이리얼트립 투어/티켓", "https://www.myrealtrip.com/tour"),
        ("🏨 마이리얼트립 숙소", "https://accommodation.myrealtrip.com/"),
        ("✈️ 마이리얼트립 항공권", "https://flight.myrealtrip.com/"),
    ],
    "여기어때": [
        ("🎁 여기어때 이벤트", "https://www.yeogi.com/event"),
        ("🏨 여기어때 숙소", "https://www.yeogi.com/"),
    ],
}


# =========================================================
# 스타일/글 유형별 프롬프트
# =========================================================

STYLE_GUIDE = {
    "꼼꼼정보형": """
정보 전달을 가장 중요하게 한다.
가격, 위치, 시간, 포함/불포함, 예약조건, 주의사항 등
실제 입력된 정보를 빠르게 찾을 수 있게 구성한다.
표와 체크리스트를 적극 활용한다.
다만 설명은 딱딱한 안내문이 아니라 실제 블로그 말투로 쓴다.
""",
    "감성분위기형": """
장소의 분위기와 여행 장면을 자연스럽게 살린다.
다만 문학적 표현을 과하게 사용하지 않는다.
실제로 입력된 경험과 사진에 근거한 분위기만 표현한다.
정보는 흐름을 끊지 않는 선에서 함께 제공한다.
""",
    "솔직리뷰형": """
좋았던 점만 칭찬하지 않는다.
실제로 입력된 아쉬운 점과 불편한 점을 분명하게 설명한다.
광고처럼 보이지 않게 장점과 단점을 균형 있게 보여준다.
""",
    "가성비실속형": """
가격 대비 무엇을 얻을 수 있는지 가장 빠르게 보여준다.
가격, 포함사항, 시간, 이동, 할인, 추천 대상을 중심으로 구성한다.
비슷한 상품과 비교할 수 있는 정보가 있으면 비교해서 설명한다.
""",
}


def common_rules():
    return """
[EMMOTHER 공통 작성 규칙]

- 블로그명: 4인1견 가족, 유모차 특공대
- 작성자: 엠마더
- 아이 둘과 강아지 하나와 여행하는 엄마의 관점
- 친근하고 자연스러운 존댓말
- 했어요, 좋았어요, 괜찮았어요, 있더라고요 등을 자연스럽게 섞는다.
- 짧은 문장을 많이 사용한다.
- 한 문단에 너무 많은 내용을 넣지 않는다.
- 문단 사이에 충분히 줄바꿈한다.
- 광고 문구처럼 과장하지 않는다.
- AI 보고서처럼 쓰지 않는다.
- '이 글에서는', '살펴보겠습니다', '종합적으로', '특히 주목할 점은'
  같은 전형적인 AI 문구를 사용하지 않는다.
- 사용자가 제공하지 않은 가격, 주소, 운영시간, 시설, 서비스,
  이동시간, 아이 반응, 강아지 반응, 할인정보 등을 절대 만들지 않는다.
- 사실이 없으면 빈칸으로 두거나 '직접 입력 필요'라고 표시한다.
- [사진] 표시를 사진이 들어갈 위치에 적절히 넣는다.
- 검색 키워드는 제목, 도입부, 필요한 소제목과 본문에 자연스럽게 사용한다.
- 같은 키워드를 과도하게 반복하지 않는다.
- 독자가 가장 궁금해할 정보를 앞쪽에 배치한다.
"""


def cpa_common_rules(platform, cpa_links):
    return f"""
[CPA 공통 규칙]

플랫폼:
{platform}

CPA 링크:
{cpa_links if cpa_links else "아직 입력되지 않음"}

CPA 글에서는 아래 5가지를 반드시 고려한다.

1. 제목
- 사람들이 실제로 검색하는 상품명을 우선한다.
- 상품명을 AI가 임의로 바꾸거나 과장하지 않는다.

2. 예약 이유 한 줄
- 실제 입력된 비교 정보가 있다면
  '비교해보니 여기가 더 저렴했어요'처럼 자연스럽게 설명한다.
- 사용자가 최저가라고 확인하지 않았다면 '최저가'라고 단정하지 않는다.

3. 할인 방법
- 쿠폰, 코드, 행사기간, 구매 시점 등
  사용자가 직접 입력한 정보만 사용한다.

4. 실측/상품정보
- 가격, 소요시간, 픽업, 포함/불포함, 주의사항 등
  입력된 정보만 사용한다.

5. CPA 링크
- 링크를 한 곳에 몰아넣지 않는다.
- 정보가 필요한 지점에 자연스럽게 배치한다.
- 링크가 실제로 제공되지 않았다면 링크를 만들어내지 않는다.
"""


def build_type_rules(content_type):
    if content_type in ("투어/액티비티 후기", "CPA 투어/액티비티 후기"):
        return """
[투어/액티비티 후기 구조]
- 검색자가 바로 이해할 수 있는 제목
- 맨 앞 핵심 요약
- 기본정보 표
- 실제 이용 후기
- 아이와 함께 이용한 경험
- 좋았던 점
- 아쉬운 점/주의사항
- 예약 전 체크
- 총평
""" + ("""
[CPA 투어/액티비티 전용]
- 상품명은 실제 검색되는 상품명을 우선한다.
- 왜 이 플랫폼에서 예약했는지 한 줄을 자연스럽게 넣는다.
- 가격, 소요시간, 픽업, 포함/불포함, 할인방법 등 입력된 실측정보를 앞쪽에서 보여준다.
- CPA 링크는 정보가 필요한 중간 지점과 마지막에 자연스럽게 삽입한다.
- 링크가 없으면 링크를 만들지 않는다.
""" if content_type == "CPA 투어/액티비티 후기" else "")

    if content_type in ("숙박후기", "CPA 숙박후기"):
        return """
[숙박후기 구조]
- 숙소 핵심 요약
- 기본정보 표
- 위치/이동
- 객실
- 부대시설
- 조식/식사
- 아이와 이용한 경험
- 강아지 동반 정보가 입력되어 있다면 해당 내용
- 좋았던 점
- 아쉬운 점
- 예약 전 체크
- 총평
""" + ("""
[CPA 숙박후기 전용]
- 숙소명은 실제 검색되는 숙소명을 우선한다.
- 왜 이 플랫폼에서 예약했는지 한 줄을 자연스럽게 넣는다.
- 가격, 객실, 조식, 부대시설, 위치, 할인방법 등 입력된 실측정보를 활용한다.
- CPA 링크는 정보가 필요한 중간 지점과 마지막에 자연스럽게 삽입한다.
- 링크가 없으면 링크를 만들지 않는다.
""" if content_type == "CPA 숙박후기" else "")

    if content_type == "맛집리뷰":
        return """
[맛집리뷰 구조]
- 핵심 메뉴/가격 요약
- 기본정보 표
- 방문 계기
- 매장 분위기
- 주문 메뉴
- 실제 먹어본 후기
- 아이와 방문하기 좋은지
- 주차/이동
- 아쉬운 점/주의사항
- 총평
"""

    if content_type == "제품리뷰":
        return """
[제품리뷰 구조]
- 제품명/핵심 특징
- 구매 이유
- 기본 제품정보
- 실제 사용 후기
- 장점
- 아쉬운 점
- 어떤 사람에게 맞는지
- 총평
"""

    if content_type == "정보성꿀팁":
        return """
[정보성꿀팁 구조]
- 맨 앞 핵심 요약
- 왜 필요한 정보인지
- 핵심 정보
- 실제로 적용하는 방법
- 놓치기 쉬운 부분
- 체크리스트
- 마지막 한 줄 정리
"""

    if content_type == "프로모션숙소":
        return """
[프로모션 숙소 구조]
- 맨 앞 핵심 가격/기간 요약
- 프로모션을 발견한 배경
- 숙소 기본정보
- 어떤 객실/조건인지
- 프로모션 조건
- 할인받는 방법
- 예약 전 주의사항
- 어떤 가족에게 좋은지
- 총평
"""

    if content_type == "항공권 특가/프로모션":
        return """
[항공권 CPA 전용 구조]

제목:
- 사람들이 검색하는 말을 맨 앞에 둔다.
- 노선 글이면 노선을 맨 앞에 둔다.
- 프로모션 글이면 항공사를 맨 앞에 둔다.
- 가격/기간 등 숫자가 중요하면 붙인다.

본문:
1. 맨 앞 요약
- 가장 중요한 숫자를 한 문장으로 먼저 쓴다.
- 예: '방콕 왕복 10만원, 8월 20일까지 특가예요.'
- 실제 입력된 숫자만 사용한다.

2. 서론
- 요약 다음에 항공권을 보다가 이 가격을 어떻게 발견했는지
  사용자가 입력한 내용을 자연스럽게 풀어낸다.

3. 조건
- 편도/왕복
- 수하물
- 변경
- 환불
- 프로모션 기간
- 기타 조건

4. 최저가
- 사용자가 직접 입력한 최저가만 사용한다.

CPA 링크 위치:
- 요약 끝에 1개
- 조건 뒤에 1개
- 마지막에 1개

없는 링크를 만들어내지 않는다.
"""

    if content_type == "렌터카":
        return """
[렌터카 전용 구조]

제목:
- 지역과 기간을 맨 앞에 둔다.
- 예: 제주 렌터카 3박 보험 포함 최저가
- 단, 사용자가 최저가라고 확인하지 않았다면 '최저가'를 단정하지 않는다.

본문:
1. 핵심 요약
2. 기본 조건
- 지역
- 기간
- 인원
- 캐리어

3. 차급 고르기
- 인원과 캐리어 수를 기준으로
  경차/준중형/중형/SUV/대형 중 어떤 차급이 맞는지 판단한다.
- 실제 입력값이 없는 부분은 추측하지 않는다.

4. 보험
- 자차/완전면책/면책금 등 실제 입력된 조건을 비교한다.
- 어떤 선택이 더 유리한지 사용자의 조건을 기준으로 판정한다.

5. 가격/보험 총액 표
- 차급별 대여료
- 보험
- 총액
- 추천 여부

6. 수령/반납
- 공항에서 몇 분인지
- 셔틀 여부
- 이동 방법
- 사용자가 입력한 정보만 사용한다.

CPA 링크:
- 비교표 아래 1개
- 차급별 설명 아래 1개
- 마지막 1개
"""

    if content_type == "비교글 (A vs B)":
        return """
[투어/액티비티 A vs B 비교 전용 구조]

제목:
- 상품 A 이름 + 상품 B 이름 + 비교항목
- 예: 나트랑 호핑 크레이지 vs 키즈 가격 비교
- 상품명은 입력된 그대로 사용한다.

서론:
- 왜 두 상품을 고민하는지 설명한다.
- 결론을 한 줄 먼저 보여준다.
- 실제 입력정보가 없으면 결론을 임의로 만들지 않는다.

한눈 비교:
| 비교항목 | A | B |
|---|---|---|
| 가격 | | |
| 소요시간 | | |
| 픽업 | | |
| 포함사항 | | |
| 아이 동반 | | |
| 기타 | | |

본론:
- 반드시 A를 먼저 설명한다.
- 그 다음 B를 설명한다.
- 순서를 바꾸지 않는다.

결론:
- '~이면 A'
- '~이면 B'
형태로 정리한다.

사용자가 입력하지 않은 차이점은 추측하지 않는다.
"""

    if content_type == "여행 일정":
        return """
[여행 일정 구조]
- 여행 전체 요약
- 날짜별 일정표
- 숙소
- 맛집
- 카페
- 체험
- 쇼핑
- 이동 팁
- 아이/강아지 동반 팁
"""

    if content_type == "여행지 추천":
        return """
[여행지 추천 구조]
- 어떤 가족에게 좋은지 맨 앞 요약
- 기본정보
- 핵심 볼거리
- 아이와 이용하기 좋은 점
- 강아지 동반 정보
- 방문 팁
- 추천 대상
"""

    if content_type == "여행후기":
        return """
[여행후기 구조]
- 자연스러운 도입
- 여행 기본정보
- 실제 방문 흐름
- 아이와 함께한 경험
- 좋았던 점
- 아쉬웠던 점
- 실용 팁
- 총평
"""

    return """
[일반 후기/정보 구조]
- 자연스러운 도입
- 핵심 정보
- 실제 경험
- 장점
- 주의사항
- 이용 팁
- 총평
"""


def build_prompt(
    keyword,
    content_type,
    search_intent,
    writing_mode,
    writing_style,
    length,
    platform,
    travel_info,
    important_points,
    product_info,
    cpa_info,
    cpa_links,
    related_posts,
    naver_context,
    compare_a,
    compare_b,
    airline_info,
    rental_info,
):
    style_guide = STYLE_GUIDE.get(writing_style, STYLE_GUIDE["꼼꼼정보형"])

    return f"""
너는 네이버 블로그 여행 콘텐츠를 작성하는
'EMMOTHER Travel Editor'다.

{common_rules()}

[사용자 선택 글 방식]
글 유형: {content_type}
글 형태: {writing_mode}
글 스타일: {writing_style}
분량: {length}
메인 키워드: {keyword}
검색 의도: {search_intent}
플랫폼: {platform}

[선택한 글 스타일]
{style_guide}

{build_type_rules(content_type)}

{cpa_common_rules(platform, cpa_links)}

==================================================
[사용자가 직접 제공한 실제 정보]
==================================================
{travel_info}

==================================================
[특히 알려주고 싶은 내용]
==================================================
{important_points}

==================================================
[선택된 상품 정보]
==================================================
{product_info}

==================================================
[CPA / 할인 / 예약 정보]
==================================================
{cpa_info}

==================================================
[CPA 링크]
==================================================
{cpa_links}

==================================================
[A 상품]
==================================================
{compare_a}

==================================================
[B 상품]
==================================================
{compare_b}

==================================================
[항공권 정보]
==================================================
{airline_info}

==================================================
[렌터카 정보]
==================================================
{rental_info}

==================================================
[내 블로그 관련 글]
==================================================
{related_posts}

==================================================
[네이버 검색 참고]
==================================================
{naver_context}

==================================================
[최종 작성 원칙]
==================================================

1. 사용자가 제공한 사실만 사용한다.
2. 가격/시간/거리/시설/서비스/할인/최저가 등을 추측하지 않는다.
3. 상품 정보가 자동으로 들어온 경우에도 실제 입력된 값만 사용한다.
4. 상품 URL 자체를 사실 근거로 삼아 새로운 경험을 만들어내지 않는다.
5. 직접 경험과 상품 설명을 구분해서 쓴다.
6. 후기형이면 경험과 느낌을 중심으로 한다.
7. 정보형이면 핵심 정보를 빠르게 찾을 수 있게 한다.
8. 사용자가 알려준 내용은 빠뜨리지 않는다.
9. 사진 위치에는 [사진]을 표시한다.
10. CPA 글이면 실제 입력된 CPA 링크를 정보 흐름 속에 자연스럽게 넣는다.
11. CPA가 아닌 글에는 CPA 문구나 CPA 링크를 넣지 않는다.
12. 제목은 검색자가 실제로 입력할 만한 표현을 우선한다.
13. 사용자가 입력하지 않은 정보는 '직접 입력 필요'라는 말을 남발하지 말고, 해당 내용을 생략한다.
14. AI가 설명하는 말투를 쓰지 않는다.

==================================================
[매우 중요 - 최종 출력 형식]
==================================================

사용자가 바로 네이버 블로그에 복사해서 붙여넣을 수 있는
'완성된 블로그 원고'만 출력한다.

절대로 아래 항목을 출력하지 않는다.
- 제목 후보
- 추천 이유
- SEO 최종 점검
- CPA 링크 위치 설명
- 내부링크 위치 설명
- 작성 방식 설명
- AI가 작성한 안내문
- '읽어주셔서 감사합니다'
- '더 궁금한 점이 있으면 알려주세요'
- '직접 입력 필요'를 별도 목록으로 반복하는 문구

출력은 반드시 다음처럼 시작한다.

첫 줄: 최종 제목
그 다음: 자연스러운 도입부
그 다음: 본문
필요하면 기본정보 표
필요하면 [사진]
필요하면 CPA 링크를 실제 링크와 함께 자연스러운 문장 속에 삽입
마지막: 자연스러운 총평

제목 후보를 여러 개 만들지 않는다.
추천 제목이라는 라벨도 쓰지 않는다.
최종 제목 하나만 쓴다.

[CPA 링크 규칙]
실제 링크가 입력된 경우에만 사용한다.
CPA_LINK_1 같은 자리표시자를 최종 원고에 출력하지 않는다.
입력된 실제 URL을 그대로 사용한다.
링크는 정보가 필요한 지점에 자연스럽게 넣고, 항공권/렌터카처럼 별도 규칙이 있는 글은 해당 구조를 따른다.

[내부링크 규칙]
관련 글이 입력되어 있으면 본문 흐름 안에 자연스럽게 연결할 수 있는 문장으로 넣는다.
'내부링크 위치'라는 별도 섹션은 만들지 않는다.
"""


# =========================================================
# 네이버 검색
# =========================================================

def naver_blog_search(keyword):
    try:
        client_id = st.secrets["NAVER_CLIENT_ID"]
        client_secret = st.secrets["NAVER_CLIENT_SECRET"]
    except Exception:
        return "네이버 API 키가 설정되지 않았습니다."

    url = "https://naverapihub.apigw.ntruss.com/search/v1/blog"

    headers = {
        "X-NCP-APIGW-API-KEY-ID": client_id,
        "X-NCP-APIGW-API-KEY": client_secret,
    }

    params = {
        "query": keyword,
        "display": 10,
        "sort": "sim",
        "format": "json",
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=10,
        )

        if response.status_code != 200:
            return "네이버 검색 결과를 가져오지 못했습니다."

        data = response.json()
        results = []

        for item in data.get("items", []):
            results.append(
                f"""
제목: {item.get("title", "")}
설명: {item.get("description", "")}
블로그 URL: {item.get("link", "")}
"""
            )

        return "\n".join(results) or "검색 결과가 없습니다."

    except Exception as e:
        return f"네이버 검색 중 오류: {type(e).__name__}: {e}"


# =========================================================
# UI
# =========================================================

st.markdown("""
<style>
div[data-testid="stTextArea"] textarea {
    font-size: 18px !important;
    line-height: 1.9 !important;
    padding: 18px !important;
}
div[data-testid="stTextArea"] label {
    font-size: 16px !important;
}
</style>
""", unsafe_allow_html=True)

st.title("✈️ EMMOTHER Travel AI")
st.caption(
    "4인1견 가족여행 블로그 · 일반 콘텐츠 + 마이리얼트립/여기어때 CPA 콘텐츠"
)

if "generation_count" not in st.session_state:
    st.session_state.generation_count = 0

if "product_meta" not in st.session_state:
    st.session_state.product_meta = {}

if "generated_result" not in st.session_state:
    st.session_state.generated_result = ""

st.info(
    f"이번 세션 생성 횟수: "
    f"{st.session_state.generation_count}/{MAX_GENERATIONS}"
)


# =========================================================
# ① 기본 설정
# =========================================================

st.subheader("① 글 기본 설정")

col1, col2 = st.columns(2)

with col1:
    keyword = st.text_input(
        "메인 키워드",
        placeholder="예: 나트랑 호핑투어 가격 / 발리 가족여행 숙소",
    )

with col2:
    content_type = st.selectbox(
        "글 유형",
        CONTENT_TYPES,
    )

col3, col4 = st.columns(2)

with col3:
    search_intent = st.selectbox(
        "검색 의도",
        [
            "후기·경험 확인",
            "추천·비교",
            "가격·특가 확인",
            "이용 정보 확인",
            "예약·구매",
            "여행 일정 찾기",
        ],
    )

with col4:
    writing_mode = st.selectbox(
        "글 형태",
        WRITING_MODES,
    )


# =========================================================
# ② 플랫폼
# =========================================================

st.subheader("② 예약/구매 플랫폼")

platform = st.selectbox(
    "CPA 플랫폼",
    PLATFORMS,
)

if platform != "없음":
    st.success(
        f"선택 플랫폼: {platform}"
    )

    link_cols = st.columns(2)

    if "마이리얼트립" in platform:
        with link_cols[0]:
            st.markdown("### 🌏 마이리얼트립")
            for label, url in OFFICIAL_LINKS["마이리얼트립"]:
                st.link_button(label, url, use_container_width=True)

    if "여기어때" in platform:
        with link_cols[1]:
            st.markdown("### 🏨 여기어때")
            for label, url in OFFICIAL_LINKS["여기어때"]:
                st.link_button(label, url, use_container_width=True)

    st.caption(
        "공식 페이지를 열어 현재 행사/상품을 확인할 수 있습니다. "
        "실시간 TOP10/도시별 순위의 자동 연동은 해당 플랫폼의 공식 API/제휴 데이터가 확보되면 "
        "상품 검색 모듈에 연결할 수 있습니다."
    )


# =========================================================
# ③ 상품 선택/자동 정보
# =========================================================

st.subheader("③ 상품 선택 / 상품정보 자동 입력")

product_url = st.text_input(
    "상품 페이지 URL",
    placeholder="마이리얼트립 또는 여기어때 상품 URL을 붙여넣으세요.",
)

meta_col1, meta_col2 = st.columns([1, 3])

with meta_col1:
    fetch_meta = st.button(
        "🔎 상품정보 불러오기",
        use_container_width=True,
    )

with meta_col2:
    if st.session_state.product_meta.get("title"):
        st.success(
            f"불러온 상품: {st.session_state.product_meta['title']}"
        )

if fetch_meta:
    if not product_url:
        st.warning("상품 URL을 입력해주세요.")
    else:
        with st.spinner("상품 페이지 정보를 확인하는 중..."):
            meta = fetch_url_metadata(product_url)

        if meta.get("error"):
            st.error(meta["error"])
        else:
            st.session_state.product_meta = meta
            st.success("페이지의 공개 메타정보를 불러왔습니다.")

            if meta.get("image"):
                st.image(
                    meta["image"],
                    caption="페이지에서 확인된 대표 이미지",
                    width=320,
                )

            st.write("**상품명:**", meta.get("title", ""))
            st.write("**설명:**", meta.get("description", ""))

st.markdown("#### 상품정보")

product_name = st.text_input(
    "상품명",
    value=st.session_state.product_meta.get("title", ""),
)

product_info = st.text_area(
    "상품정보",
    placeholder="""예:
가격:
소요시간:
픽업:
포함사항:
불포함사항:
이용 가능 연령:
취소 규정:
예약 조건:
주소/위치:
체크인:
체크아웃:
객실:
시설:
""",
    height=220,
)


# =========================================================
# ④ 직접 경험/입력 정보
# =========================================================

st.subheader("④ 내가 직접 알려줄 내용")

travel_info = st.text_area(
    "직접 경험했거나 직접 확인한 정보",
    placeholder="""예:
2025년 직접 방문
3박 숙박
아이 둘과 방문
실제로 이용한 시설
직접 느낀 장점
아쉬웠던 점
아이와 이용하면서 불편했던 부분
사진에서 꼭 설명하고 싶은 내용

※ AI가 추측하면 안 되는 실제 정보를 최대한 자세히 적어주세요.""",
    height=260,
)

important_points = st.text_area(
    "특히 알려주고 싶은 내용",
    placeholder="""예:
- 아이와 함께 이용하기 편했던 부분
- 실제로 불편했던 부분
- 내가 가장 강조하고 싶은 장점
- 예약 전에 꼭 알려주고 싶은 것
- 사진 순서에 맞춰 설명하고 싶은 내용""",
    height=180,
)


# =========================================================
# ⑤ 글 스타일
# =========================================================

st.subheader("⑤ 글 스타일")

style_col1, style_col2 = st.columns(2)

with style_col1:
    writing_style = st.selectbox(
        "글 스타일",
        WRITING_STYLES,
    )

with style_col2:
    length = st.selectbox(
        "본문 분량",
        LENGTHS,
        index=2,
    )


# =========================================================
# ⑥ CPA 정보
# =========================================================

CPA_CONTENT_TYPES = {
    "CPA 투어/액티비티 후기",
    "CPA 숙박후기",
    "항공권 특가/프로모션",
    "렌터카",
}
is_cpa = content_type in CPA_CONTENT_TYPES or platform != "없음"

if is_cpa:
    st.subheader("⑥ CPA 정보")

    cpa_info = st.text_area(
        "할인/예약/가격 정보",
        placeholder="""예:
쿠폰:
쿠폰 할인:
프로모션 코드:
프로모션 기간:
언제 구매하면 저렴한지:
내가 실제로 비교한 가격:
예약한 이유:
주의사항:
""",
        height=220,
    )

    cpa_link_1 = st.text_input(
        "CPA 링크 ①",
        placeholder="https://...",
    )
    cpa_link_2 = st.text_input(
        "CPA 링크 ②",
        placeholder="https://...",
    )
    cpa_link_3 = st.text_input(
        "CPA 링크 ③",
        placeholder="https://...",
    )

    cpa_links = "\n".join(
        [
            f"[CPA_LINK_1] {cpa_link_1}" if cpa_link_1 else "",
            f"[CPA_LINK_2] {cpa_link_2}" if cpa_link_2 else "",
            f"[CPA_LINK_3] {cpa_link_3}" if cpa_link_3 else "",
        ]
    ).strip()

else:
    cpa_info = ""
    cpa_links = ""


# =========================================================
# ⑦ 비교글 A/B
# =========================================================

compare_a = ""
compare_b = ""

if content_type == "비교글 (A vs B)":
    st.subheader("⑦ A vs B 비교")

    a_col, b_col = st.columns(2)

    with a_col:
        st.markdown("### 🅰️ 상품 A")
        compare_a = st.text_area(
            "A 상품 정보",
            placeholder="""상품명:
가격:
소요시간:
픽업:
포함사항:
아이 동반:
장점:
단점:
기타:""",
            height=260,
        )

    with b_col:
        st.markdown("### 🅱️ 상품 B")
        compare_b = st.text_area(
            "B 상품 정보",
            placeholder="""상품명:
가격:
소요시간:
픽업:
포함사항:
아이 동반:
장점:
단점:
기타:""",
            height=260,
        )


# =========================================================
# ⑧ 항공권
# =========================================================

airline_info = ""

if content_type == "항공권 특가/프로모션":
    st.subheader("⑧ 항공권 특가 정보")

    airline_info = st.text_area(
        "항공권 정보",
        placeholder="""항공사:
노선:
편도/왕복:
최저가:
프로모션 기간:
출발 가능 기간:
수하물:
변경 규정:
환불 규정:
기타 조건:
가격을 발견한 과정:
""",
        height=260,
    )


# =========================================================
# ⑨ 렌터카
# =========================================================

rental_info = ""

if content_type == "렌터카":
    st.subheader("⑨ 렌터카 비교 정보")

    rental_info = st.text_area(
        "렌터카 정보",
        placeholder="""지역:
대여 기간:
인원:
캐리어 개수:

[경차]
대여료:
보험:
면책금:
총액:

[준중형]
대여료:
보험:
면책금:
총액:

[SUV]
대여료:
보험:
면책금:
총액:

수령 장소:
공항에서 이동시간:
셔틀 여부:
반납 방법:
주의사항:
""",
        height=320,
    )


# =========================================================
# ⑩ 내부링크
# =========================================================

st.subheader("⑩ 내 블로그 관련 글")

related_posts = st.text_area(
    "관련 글",
    placeholder="""예:
발리 4박6일 가족여행 일정
발리 가족여행 숙소 추천 BEST 15
우붓 가족여행 코스
발리 여행 준비물""",
    height=140,
)


# =========================================================
# 생성
# =========================================================

st.divider()

generate = st.button(
    "✨ EMMOTHER 스타일로 글 생성",
    use_container_width=True,
    type="primary",
)

if generate:

    if st.session_state.generation_count >= MAX_GENERATIONS:
        st.error("이번 세션에서는 최대 5회까지 생성할 수 있어요.")
        st.stop()

    if not keyword:
        st.warning("메인 키워드를 입력해주세요.")
        st.stop()

    # 후기형/여행후기에서는 실제 정보가 사실상 필수.
    # 정보형/특가형은 사용자가 입력한 정보가 있어야 생성 가능.
    if not travel_info and not product_info and not airline_info and not rental_info:
        st.warning("AI가 추측하지 않도록 실제 정보나 상품정보를 입력해주세요.")
        st.stop()

    # 상품정보를 보기 좋게 하나로 정리
    selected_product_info = ""
    if product_name:
        selected_product_info += f"상품명: {product_name}\n"
    if product_info:
        selected_product_info += product_info

    with st.spinner("네이버 검색 + EMMOTHER 전용 글 구조로 작성 중..."):

        naver_context = naver_blog_search(keyword)

        prompt = build_prompt(
            keyword=keyword,
            content_type=content_type,
            search_intent=search_intent,
            writing_mode=writing_mode,
            writing_style=writing_style,
            length=length,
            platform=platform,
            travel_info=travel_info,
            important_points=important_points,
            product_info=selected_product_info,
            cpa_info=cpa_info,
            cpa_links=cpa_links,
            related_posts=related_posts,
            naver_context=naver_context,
            compare_a=compare_a,
            compare_b=compare_b,
            airline_info=airline_info,
            rental_info=rental_info,
        )

        try:
            client = OpenAI(
                api_key=st.secrets["OPENAI_API_KEY"]
            )

            response = client.responses.create(
                model="gpt-5-mini",
                input=prompt,
                max_output_tokens=9000,
            )

            result = response.output_text

            st.session_state.generation_count += 1
            st.session_state.generated_result = result

            st.success("글 생성 완료!")

        except Exception as e:
            st.error(
                f"글 생성 중 오류가 발생했습니다: "
                f"{type(e).__name__}: {e}"
            )


# =========================================================
# 결과
# =========================================================

if st.session_state.generated_result:
    st.divider()
    st.subheader("📝 생성 결과")

    st.text_area(
        "복사해서 사용할 수 있는 결과",
        st.session_state.generated_result,
        height=1800,
    )

    st.caption(
        f"이번 세션 사용 횟수: "
        f"{st.session_state.generation_count}/{MAX_GENERATIONS}"
    )

    st.download_button(
        "📄 결과 TXT 저장",
        data=st.session_state.generated_result,
        file_name="emmother_travel_ai_result.txt",
        mime="text/plain",
        use_container_width=True,
    )
