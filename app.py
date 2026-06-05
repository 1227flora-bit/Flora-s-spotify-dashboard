import os
import threading
import time
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
import uvicorn

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
st.title("🎧 Spotify 聆聽數據進階決策儀表板 (2020-2026)")
st.markdown("基於 **FastAPI 後端高級運算 Pipeline** 驅動之多維度視覺化專案。")


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
top_song_data = fetch_data("chart/artist_top_song")
top100_data = fetch_data("chart/top100")
yearly_champions = fetch_data("chart/yearly_champions")

if stats:
    # ==========================================
    # 📊 1. 最上方資訊看板（包含不重複歌曲數）
    # ==========================================
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("總點播次次 (Plays)", f"{stats['total_plays']} 次")
    c2.metric("不重複歌曲 (Unique Songs) 🎵", f"{stats['unique_songs']} 首")
    c3.metric("點播歌手 (Artists)", f"{stats['unique_artists']} 位")
    c4.metric("涉足專輯 (Albums)", f"{stats['unique_albums']} 張")
    c5.metric("總聆聽時間 (Hours) ⏳", f"{stats['total_hours']} 小時")

    st.markdown("---")

    # ==========================================
    # 🌲 2. 最常聽歌手樹狀圖 (Treemap)
    # ==========================================
    st.subheader("👑 2020-2026 最常聽歌手權重分佈 (Top Artists Treemap)")
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
                texttemplate="<b>%{label}</b><br>🎵 %{customdata[0]} 次<br>⏳ %{customdata[1]} 分",
                textposition="middle center",
                hovertemplate="<b>歌手:</b> %{label}<br><b>點播次數:</b> %{customdata[0]} 次<br><b>總聆聽時間:</b> %{customdata[1]} 分鐘<extra></extra>",
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
                texttemplate="<b>%{label}</b><br>🎵 %{customdata[0]} 次",
                textposition="middle center",
                hovertemplate="<b>歌手:</b> %{label}<br><b>點播次數:</b> %{customdata[0]} 次<extra></extra>",
                textfont=dict(size=14),
                insidetextfont=dict(size=14),
                textinfo="label+text",
            )

        fig_tree.update_layout(margin=dict(t=10, l=10, r=10, b=10))
        st.plotly_chart(fig_tree, use_container_width=True)

    st.markdown("---")

    # ==========================================
    # 📈 3. 每月聆聽分鐘數折線圖 & 冠軍歌曲長條圖 (左右並排)
    # ==========================================
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.subheader("📈 2020-2026 每月聆聽分鐘數趨勢")
        if monthly_data:
            df_monthly = pd.DataFrame(monthly_data)
            fig_line = px.line(
                df_monthly,
                x="年月",
                y="聆聽分鐘",
                markers=True,
                labels={"聆聽分鐘": "總分鐘數", "年月": "時間範圍"},
            )
            fig_line.update_traces(line_color="#1DB954")
            st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.info("暫無時間序列數據")

    with col_chart2:
        st.subheader("🏆 樹狀圖歌手之「最高聆聽單曲」比較")
        if top_song_data:
            df_top_songs = pd.DataFrame(top_song_data)
            df_top_songs_sorted = df_top_songs.sort_values(
                by="Minutes", ascending=True
            )

            fig_bar = px.bar(
                df_top_songs_sorted,
                x="Minutes",
                y="Display_Label",
                orientation="h",
                labels={
                    "Minutes": "該曲總聆聽分鐘數",
                    "Display_Label": "歌手與冠軍單曲",
                },
                color="Minutes",
                color_continuous_scale="Viridis",
            )
            fig_bar.update_layout(
                height=500,
                margin=dict(t=10, l=10, r=10, b=10),
                showlegend=False,
            )
            fig_bar.update_yaxes(title_text="")
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("暫無歌手冠軍歌曲數據")

    st.markdown("---")

    # ==========================================
    # 📅 4. 歷年風雲榜：年度最高歌手 & 歌曲
    # ==========================================
    st.header("✨ 2020-2026 歷年終極風雲榜 (Yearly Champions)")
    if yearly_champions:
        df_yearly = pd.DataFrame(yearly_champions)

        st.write("**👑 年度稱霸者速覽**")
        cols = st.columns(len(df_yearly))
        for idx, row in df_yearly.iterrows():
            with cols[idx]:
                st.markdown(
                    f"""
                    <div style="background-color:#111; padding:15px; border-radius:10px; border-left: 5px solid #1DB954; min-height:180px;">
                        <h4 style="color:#1DB954; margin-top:0;">📅 {int(row['Year'])} 年</h4>
                        <p style="margin-bottom:5px; font-size:14px;"><b>🎤 冠軍歌手：</b><br>{row['Top_Artist']}</p>
                        <p style="color:#aaa; font-size:12px; margin-top:0;">累積 {row['Artist_Minutes']} 分鐘</p>
                        <p style="margin-bottom:5px; font-size:14px;"><b>🎵 冠軍歌曲：</b><br>{row['Top_Song']}</p>
                        <p style="color:#aaa; font-size:12px; margin-top:0;">累積 {row['Song_Minutes']} 分鐘</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        st.write("")
        st.write("")

        st.write("**📊 歷年冠軍數據量化對比 (歌手 vs 歌曲)**")
        plot_data = []
        for _, row in df_yearly.iterrows():
            plot_data.append(
                {
                    "年份": str(int(row["Year"])),
                    "項目": f"🎤 歌手: {row['Top_Artist']}",
                    "聆聽分鐘數": row["Artist_Minutes"],
                }
            )
            plot_data.append(
                {
                    "年份": str(int(row["Year"])),
                    "項目": f"🎵 歌曲: {row['Top_Song']}",
                    "聆聽分鐘數": row["Song_Minutes"],
                }
            )
        df_plot = pd.DataFrame(plot_data)

        fig_yearly = px.bar(
            df_plot,
            x="年份",
            y="聆聽分鐘數",
            color="項目",
            barmode="group",
            labels={"聆聽分鐘數": "總聆聽分鐘"},
        )
        fig_yearly.update_layout(height=400, margin=dict(t=10, b=10))
        st.plotly_chart(fig_yearly, use_container_width=True)
    else:
        st.info("暫無年度風雲榜數據")

    st.markdown("---")

    # ==========================================
    # 🏆 5. Top 100 聆聽最長歌曲排行榜表格
    # ==========================================
    st.subheader("🏆 2020-2026 聆聽時間最長歌曲排行 Top 100")
    if top100_data:
        df_top100 = pd.DataFrame(top100_data)
        df_top100.index = [f"🏅 第 {i+1} 名" for i in range(len(df_top100))]
        st.dataframe(df_top100, use_container_width=True, height=400)
    else:
        st.info("無法載入歌曲排行")

else:
    st.info(
        "💡 正在讀取數據，請確保專案目錄內有合併好的 spotify_listen_record.csv 檔案..."
    )