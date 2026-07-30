import re
import requests
import pandas as pd
import streamlit as st
import plotly.express as px

# 1. 페이지 기본 설정
st.set_page_config(page_title="전국 고령화 지도", layout="wide")
st.title("🗺️ 전국 고령화 지도")
st.caption("시군구별 65세 이상 인구 비율 (행정안전부 주민등록 인구)")

POP_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
GEO_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"

# 2. 데이터 불러오기 (스트림릿 캐시를 사용해 속도 향상)
@st.cache_data(show_spinner="인구 데이터를 불러오는 중입니다...")
def load_population():
    # '코드' 열은 앞자리 0이 사라지지 않게 반드시 글자(str)로 읽습니다.
    return pd.read_csv(POP_URL, dtype={"코드": str})

@st.cache_data(show_spinner="지도 경계를 불러오는 중입니다...")
def load_geojson():
    return requests.get(GEO_URL, timeout=30).json()

df = load_population()
geojson = load_geojson()

# 3. 데이터 가공하기
# 가장 최신 연도만 필터링
latest_year = int(df["연도"].max())
df = df[df["연도"] == latest_year].copy()

# '계_'로 시작하는 나이 열만 찾기 (남녀를 합친 인구)
total_cols = [c for c in df.columns if c.startswith("계_")]

# 컬럼명에서 나이 숫자만 뽑아내는 함수
def age_of(col):
    m = re.match(r"계_(\d+)세", col)
    return int(m.group(1)) if m else None

# 65세 이상 열만 추려내기
elderly_cols = [c for c in total_cols if age_of(c) is not None and age_of(c) >= 65]

# 동 단위로 전체 인구와 고령 인구 합계 계산
df["전체인구"] = df[total_cols].sum(axis=1)
df["고령인구"] = df[elderly_cols].sum(axis=1)

# '코드' 앞 5자리를 잘라 시군구 코드로 사용
df["시군구코드"] = df["코드"].str[:5]

# 시군구 코드를 기준으로 묶어서 인구 합산 후 고령화율(%) 계산
grouped = df.groupby("시군구코드")[["전체인구", "고령인구"]].sum().reset_index()
grouped["고령화율"] = (grouped["고령인구"] / grouped["전체인구"] * 100).round(2)

# 마우스를 올렸을 때 지역 이름을 보여주기 위해 GeoJSON에서 속성(이름, 시도) 추출
names = pd.DataFrame([
    {
        "시군구코드": str(f["properties"]["코드"]),
        "시군구": f["properties"]["시군구"],
        "시도": f["properties"]["시도"],
    }
    for f in geojson["features"]
])

# 인구 데이터와 지역 이름 데이터 병합
merged = grouped.merge(names, on="시군구코드", how="left")

# 4. 5단계 색 구간 설정 (요청하신 실제 경계값 적용)
BINS = [0, 19, 23, 28, 38, 100]
LABELS = ["19% 미만", "19~23%", "23~28%", "28~38%", "38% 이상"]
COLORS = {
    "19% 미만": "#fee6ce", # 옅은 주황
    "19~23%": "#fdc086",
    "23~28%": "#f79646",
    "28~38%": "#e8590c",
    "38% 이상": "#a63603", # 짙은 주황
}

# 고령화율에 따라 데이터에 단계 라벨 붙이기
merged["단계"] = pd.cut(merged["고령화율"], bins=BINS, labels=LABELS, right=False)

# 5. 단계구분도 그리기
fig = px.choropleth(
    merged,
    geojson=geojson,
    locations="시군구코드",              # 데이터프레임의 시군구코드
    featureidkey="properties.코드",       # GeoJSON의 5자리 코드와 매칭
    color="단계",                       # 5단계 라벨 기준으로 색상 칠하기
    category_orders={"단계": LABELS},    # 범례 순서 고정
    color_discrete_map=COLORS,          # 미리 지정한 색상 매핑
    hover_name="시군구",                 # 마우스 오버 시 가장 크게 보일 이름
    hover_data={
        "고령화율": True,
        "시도": True,
        "시군구코드": False,            # 코드는 툴팁에서 숨김
        "단계": False                   # 단계 텍스트도 툴팁에서 숨김
    },
    labels={"고령화율": "65세 이상 비율(%)"},
)

# 배경 지도 타일 끄기 및 지도 여백 설정
fig.update_geos(fitbounds="locations", visible=False)
fig.update_layout(
    margin=dict(l=0, r=0, t=10, b=0),
    height=700,
    legend_title_text=f"65세 이상 비율 ({latest_year}년)",
)

# 스트림릿에 지도 출력 (화면 폭에 맞춤)
st.plotly_chart(fig, width="stretch")

# 6. 지도 아래에 순위 표 두 개를 나란히 배치
c1, c2 = st.columns(2)
cols = ["시도", "시군구", "고령화율"]

with c1:
    st.subheader("🔴 고령화율 높은 곳 10")
    # 가장 높은 10개를 뽑고 인덱스 깔끔하게 정리
    st.dataframe(merged.nlargest(10, "고령화율")[cols].reset_index(drop=True))

with c2:
    st.subheader("🟢 고령화율 낮은 곳 10")
    # 가장 낮은 10개를 뽑고 인덱스 깔끔하게 정리
    st.dataframe(merged.nsmallest(10, "고령화율")[cols].reset_index(drop=True))
