"""
전국 시군구 고령화 지도 (스트림릿 앱)
- 시군구별 65세 이상 인구 비율(고령화율)을 5단계 색으로 나눈 단계구분도(코로플레스 맵)
- 스트림릿 클라우드 배포용 main.py
"""

import re

import numpy as np
import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go

# -----------------------------------------------------------------------------
# 0. 페이지 기본 설정
# -----------------------------------------------------------------------------
st.set_page_config(page_title="전국 고령화 지도", page_icon="🗺️", layout="wide")

st.title("🗺️ 전국 시군구 고령화 지도")
st.caption("시군구별 65세 이상 인구 비율(고령화율)을 색으로 나타낸 단계구분도입니다.")

# 데이터 주소
POP_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
GEO_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"


# -----------------------------------------------------------------------------
# 1. 인구 데이터 불러오기 + 시군구별 고령화율 계산
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner="인구 데이터를 내려받는 중입니다...")
def load_population():
    # '코드' 열은 계산용 숫자가 아니라 이름표이므로 문자열(str)로 읽어야
    # 앞자리 0이 사라지지 않습니다.
    df = pd.read_csv(POP_URL, compression="gzip", dtype={"코드": str})
    df["코드"] = df["코드"].str.strip()
    return df


@st.cache_data(show_spinner="시군구 경계 데이터를 내려받는 중입니다...")
def load_geojson():
    res = requests.get(GEO_URL, timeout=30)
    res.raise_for_status()
    return res.json()


def get_age_from_col(col: str):
    """'계_0세', '계_65세', '계_100세 이상' 같은 열 이름에서 나이(정수)를 뽑아냅니다."""
    if "100세 이상" in col:
        return 100
    m = re.search(r"(\d+)세", col)
    if m:
        return int(m.group(1))
    return None


@st.cache_data(show_spinner="시군구별 고령화율을 계산하는 중입니다...")
def build_sigungu_ratio(pop_df: pd.DataFrame):
    # '계_'로 시작하는 열 = 남녀를 합친 나이별 인구 열
    total_cols = [c for c in pop_df.columns if c.startswith("계_")]

    # 65세 이상에 해당하는 열만 골라냅니다.
    elderly_cols = [c for c in total_cols if (get_age_from_col(c) or 0) >= 65]

    # 가장 최신 연도만 사용합니다.
    latest_year = pop_df["연도"].max()
    latest = pop_df[pop_df["연도"] == latest_year].copy()

    # 읍·면·동 한 줄(row)마다 총인구, 65세 이상 인구를 더합니다.
    latest["총인구"] = latest[total_cols].sum(axis=1)
    latest["고령인구"] = latest[elderly_cols].sum(axis=1)

    # '코드' 앞 5자리 = 시군구 코드
    latest["시군구코드"] = latest["코드"].str[:5]

    # 읍·면·동 단위를 시군구 단위로 합산합니다.
    agg = (
        latest.groupby("시군구코드")[["총인구", "고령인구"]]
        .sum()
        .reset_index()
    )
    agg["고령화율"] = agg["고령인구"] / agg["총인구"] * 100

    return agg, latest_year


pop_df = load_population()
geojson = load_geojson()
sigungu_ratio, latest_year = build_sigungu_ratio(pop_df)

st.markdown(f"### {latest_year}년 기준 시군구별 고령화율")

# -----------------------------------------------------------------------------
# 2. 지도 경계 데이터에서 시군구 이름 정보 뽑아 붙이기
# -----------------------------------------------------------------------------
geo_info = pd.DataFrame(
    [
        {
            "시군구코드": str(f["properties"]["코드"]).strip(),
            "시군구": f["properties"]["시군구"],
            "시도": f["properties"]["시도"],
        }
        for f in geojson["features"]
    ]
)

# 코드를 기준으로 이름(시도, 시군구)과 고령화율을 합칩니다.
# (이름으로 맞추면 '남구'처럼 여러 시도에 같은 이름이 있어 어긋나므로 코드로 맞춥니다.)
merged = geo_info.merge(sigungu_ratio, on="시군구코드", how="left")

# -----------------------------------------------------------------------------
# 3. 고령화율을 5단계 구간으로 나누기
# -----------------------------------------------------------------------------
# 문제에서 준 실제 경계값: 19% · 23% · 28% · 38%
bin_edges = [-np.inf, 19, 23, 28, 38, np.inf]
bin_labels = [
    "19% 미만",
    "19% ~ 23%",
    "23% ~ 28%",
    "28% ~ 38%",
    "38% 이상",
]
# 옅은 색 -> 진한 색 순서의 5가지 색
bin_colors = ["#fee5d9", "#fcae91", "#fb6a4a", "#de2d26", "#a50f15"]

merged["구간"] = pd.cut(
    merged["고령화율"], bins=bin_edges, labels=bin_labels, right=False
)

# -----------------------------------------------------------------------------
# 4. 지도 그리기 (plotly Choropleth, 배경 지도 타일 없음)
# -----------------------------------------------------------------------------
fig = go.Figure()

for label, color in zip(bin_labels, bin_colors):
    part = merged[merged["구간"] == label]
    if part.empty:
        continue

    fig.add_trace(
        go.Choropleth(
            geojson=geojson,
            locations=part["시군구코드"],
            z=[1] * len(part),  # 구간마다 색을 고정하기 위한 더미 값
            featureidkey="properties.코드",
            colorscale=[[0, color], [1, color]],  # 이 구간은 한 가지 색으로 고정
            showscale=False,  # 연속 컬러바 대신 아래 legend로 구간을 보여줍니다.
            marker_line_color="white",
            marker_line_width=0.5,
            name=label,
            showlegend=True,
            customdata=part[["시군구", "시도", "고령화율"]],
            hovertemplate=(
                "<b>%{customdata[0]}</b> (%{customdata[1]})<br>"
                "고령화율: %{customdata[2]:.1f}%<extra></extra>"
            ),
        )
    )

fig.update_geos(
    visible=False,          # 바다·육지 등 배경 지도(타일)를 끕니다. 경계선만 남습니다.
    fitbounds="locations",  # 우리 데이터(전국 시군구)에 맞춰 확대합니다.
)

fig.update_layout(
    margin=dict(l=0, r=0, t=10, b=0),
    height=650,
    legend=dict(
        title="고령화율 구간",
        orientation="v",
        yanchor="middle",
        y=0.5,
        xanchor="left",
        x=1.02,
    ),
)

st.plotly_chart(fig, use_container_width=True)

# -----------------------------------------------------------------------------
# 5. 고령화율 상위 10 / 하위 10 표
# -----------------------------------------------------------------------------
st.markdown("### 고령화율 상위·하위 10개 시군구")

table_df = merged.dropna(subset=["고령화율"]).copy()
table_df["고령화율"] = table_df["고령화율"].round(1)
table_df = table_df[["시도", "시군구", "고령화율"]]

top10 = table_df.sort_values("고령화율", ascending=False).head(10).reset_index(drop=True)
bottom10 = table_df.sort_values("고령화율", ascending=True).head(10).reset_index(drop=True)

col1, col2 = st.columns(2)

with col1:
    st.markdown("**고령화율 높은 지역 TOP 10**")
    st.dataframe(top10, use_container_width=True, hide_index=True)

with col2:
    st.markdown("**고령화율 낮은 지역 TOP 10**")
    st.dataframe(bottom10, use_container_width=True, hide_index=True)

st.caption(
    "자료: 인구 - population_yearly.csv.gz, 경계 - sigungu_kr.geojson "
    "(시군구 코드를 기준으로 두 데이터를 연결했습니다.)"
)
