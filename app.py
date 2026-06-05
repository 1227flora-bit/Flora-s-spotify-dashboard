import os
import threading
import time
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
import uvicorn
import html

API_BASE_URL = "http://127.0.0.1:8000/api"


# 自動背景啟動後端 Pipeline
def run_fastapi():
    uvicorn.run("main:app", host="127.0.0.1", port=8000, log_level="warning")


if "fastapi_started" not in st.session_state:
    with st.spinner("正在初始化後端 Data Pipeline..."):
        t = threading.Thread(target=run_fastapi, daemon=True)
        t.start()
        st.session_state["fastapi_started"] = True
        time.sleep(2)

st.set_page_config(
    page_title="Spotify BI Personal Dashboard", layout="wide"
)
st.title("Flora's Spotify 聆聽數據儀表板 (2020-2026)")
st.markdown("使用 FastAPI 作為後端 Pipeline，Streamlit 為前端呈現平台，提供深入的個人聆聽行為分析與視覺化儀表板。")


def fetch_data(endpoint):
    try:
        response = requests.get(f"{API_BASE_URL}/{endpoint}")
        if response.status_code == 200:
            return response.json()
        return None
    except requests.exceptions.ConnectionError:
        return None


# 載入所有端點數據
stats = fetch_data("stats")
artist_data = fetch_data("chart/artists")
monthly_data = fetch_data("chart/monthly_trend")
hourly_data = fetch_data("chart/hourly_distribution")
artist_song_count_data = fetch_data("chart/artist_top_song_count")
top100_data = fetch_data("chart/top100")
yearly_champions = fetch_data("chart/yearly_champions")

if stats:
    # ==========================================
    # 1. 最上方資訊看板（包含不重複歌曲數）
    # ==========================================
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("總播放次數 (Plays)", f"{stats['total_plays']} 次")
    c2.metric("聽過的總歌曲數 (Unique Songs)", f"{stats['unique_songs']} 首")
    c3.metric("聽過的歌手數 (Artists)", f"{stats['unique_artists']} 位")
    c4.metric("專輯數 (Albums)", f"{stats['unique_albums']} 張")
    c5.metric("總聆聽時間 (Hours)", f"{stats['total_hours']} 小時")

    st.markdown("---")

    # ==========================================
    # 2. 最常聽歌手樹狀圖 (Treemap)
    # ==========================================
    st.subheader("2020-2026 最常聽歌手分佈 (Top Artists Treemap)")
    if artist_data:
        df_artist = pd.DataFrame(artist_data).head(30)

        if "Total_Minutes" in df_artist.columns:
            fig_tree = px.treemap(
                df_artist,
                path=["Artist"],
                values="Count",
                color="Count",
                color_continuous_scale="Greens",
                custom_data=["Count", "Total_Minutes"],
                labels={"Count": "聆聽次數"},
            )
            fig_tree.update_traces(
                texttemplate="<b>%{label}</b><br>次數: %{customdata[0]} 次<br>時間: %{customdata[1]} 分",
                textposition="middle center",
                hovertemplate="<b>歌手:</b> %{label}<br><b>播放次數:</b> %{customdata[0]} 次<br><b>總聆聽時間:</b> %{customdata[1]} 分鐘<extra></extra>",
                textfont=dict(size=14),
                insidetextfont=dict(size=14),
                textinfo="label+text",
            )
        else:
            fig_tree = px.treemap(
                df_artist,
                path=["Artist"],
                values="Count",
                color="Count",
                color_continuous_scale="Greens",
                custom_data=["Count"],
                labels={"Count": "聆聽次數"},
            )
            fig_tree.update_traces(
                texttemplate="<b>%{label}</b><br>次數: %{customdata[0]} 次",
                textposition="middle center",
                hovertemplate="<b>歌手:</b> %{label}<br><b>播放次數:</b> %{customdata[0]} 次<extra></extra>",
                textfont=dict(size=14),
                insidetextfont=dict(size=14),
                textinfo="label+text",
            )

        fig_tree.update_layout(margin=dict(t=10, l=10, r=10, b=10))
        st.plotly_chart(fig_tree, use_container_width=True)

    st.markdown("---")

    # ==========================================
    # 3. 每月聆聽分鐘數折線圖 (寬版獨立展示)
    # ==========================================
    st.subheader("2020-2026 每月聆聽分鐘數趨勢")
    if monthly_data:
        df_monthly = pd.DataFrame(monthly_data)
        fig_line = px.line(
            df_monthly,
            x="年月",
            y="聆聽總分鐘數",
            markers=True,
            labels={"聆聽總分鐘數": "總分鐘數", "年月": "時間範圍"},
        )
        fig_line.update_traces(line_color="#1DB954")
        st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.info("暫無時間序列數據")

    st.markdown("---")

    # ==========================================
    # 4. 歌手歌曲數排行 vs 24小時作息圖 (左右並排)
    # ==========================================
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.subheader("聽過最多不重複歌曲的十大歌手")
        if artist_song_count_data:
            df_count = pd.DataFrame(artist_song_count_data)
            df_count_sorted = df_count.sort_values(
                by="Song_Count", ascending=True
            )

            fig_count_bar = px.bar(
                df_count_sorted,
                x="Song_Count",
                y="Artist",
                orientation="h",
                labels={"Song_Count": "不重複歌曲數量", "Artist": "歌手名稱"},
                color="Song_Count",
                color_continuous_scale="Greens",
            )
            fig_count_bar.update_layout(
                height=400,
                margin=dict(t=10, l=10, r=10, b=10),
                showlegend=False,
            )
            fig_count_bar.update_yaxes(title_text="")
            st.plotly_chart(fig_count_bar, use_container_width=True)
        else:
            st.info("暫無歌手歌曲數量數據")

    with col_chart2:
        st.subheader("聆聽時段分佈")
        if hourly_data:
            df_hourly = pd.DataFrame(hourly_data)

            if "小時" in df_hourly.columns and "聆聽總分鐘數" in df_hourly.columns:
                fig_bar = px.bar(
                    df_hourly,
                    x="小時",
                    y="聆聽總分鐘數",
                    labels={"聆聽總分鐘數": "累積聆聽分鐘數", "小時": "時"},
                    color="聆聽總分鐘數",
                    color_continuous_scale="Greens",
                )
                fig_bar.update_layout(
                    height=400,
                    margin=dict(t=10, l=10, r=10, b=10),
                    showlegend=False,
                    xaxis=dict(
                        tickmode="linear",
                        tick0=0,
                        dtick=1,
                        tickangle=0
                    )
                )
                st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.warning("時段數據欄位不匹配，請確認後端是否重啟成功")
        else:
            st.info("暫無時段分佈數據")

    st.markdown("---")

    # ==========================================
    # ==========================================
    # 5. 歷年風雲榜：年度最高歌手 & 歌曲
    # ==========================================
    st.header("2020-2026 歷年聆聽最高前 3 名歌手與歌曲 (Yearly Top 3)")
    if yearly_champions:
        df_yearly = pd.DataFrame(yearly_champions)

    st.write("年度榜單")
    cols = st.columns(len(df_yearly))
    for idx, row in df_yearly.iterrows():

        # 1. 建立歌手的 HTML 列表項目
        artist_items = ""
        for rank, item in enumerate(row['Top_Artists'], 1):
            name = html.escape(str(item['name']))
            mins = html.escape(str(item['mins']))
            artist_items += f'<li style="margin-bottom:6px;font-size:13px;color:var(--text-color);"><b>No.{rank}</b> {name}<span style="color:var(--text-color);opacity:0.6;font-size:11px;"><br>({mins} 分)</span></li>'

        # 2. 建立歌曲的 HTML 列表項目
        song_items = ""
        for rank, item in enumerate(row['Top_Songs'], 1):
            title = html.escape(str(item['title']))
            artist = html.escape(str(item['artist']))
            mins = html.escape(str(item['mins']))
            song_items += f'<li style="margin-bottom:6px;font-size:13px;color:var(--text-color);"><b>No.{rank}</b> {title}<span style="color:var(--text-color);opacity:0.6;font-size:11px;"><br>{artist} / {mins} 分</span></li>'

        with cols[idx]:
            card_html = (
                f'<div style="background-color:var(--background-color);padding:15px;border-radius:10px;border:1px solid rgba(151,151,151,0.2);border-left:5px solid #1DB954;min-height:420px;">'
                f'<h4 style="color:#1DB954;margin-top:0;margin-bottom:12px;border-bottom:1px solid rgba(151,151,151,0.2);padding-bottom:5px;">{int(row["Year"])} 年</h4>'
                f'<p style="margin-bottom:8px;font-size:14px;color:#1DB954;font-weight:bold;">歌手 Top 3</p>'
                f'<ul style="padding-left:0;margin-top:0;margin-bottom:15px;list-style-type:none;">{artist_items}</ul>'
                f'<p style="margin-bottom:8px;font-size:14px;color:#1DB954;font-weight:bold;">歌曲 Top 3</p>'
                f'<ul style="padding-left:0;margin-top:0;margin-bottom:0;list-style-type:none;">{song_items}</ul>'
                f'</div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)

    st.write("")
    st.write("")

    # ==========================================
    # 6. Top 100 聆聽最長歌曲排行榜表格
    # ==========================================
    st.subheader("2020-2026 聆聽時間最長歌曲排行 Top 100")
    if top100_data:
        df_top100 = pd.DataFrame(top100_data)
        df_top100.index = [f"第 {i+1} 名" for i in range(len(df_top100))]
        st.dataframe(df_top100, use_container_width=True, height=400)
    else:
        st.info("無法載入歌曲排行")

else:
    st.info(
        "正在讀取數據，請確保專案目錄內有合併好的 spotify_listen_record.csv 檔案..."
    )