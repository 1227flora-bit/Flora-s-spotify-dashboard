import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
import pandas as pd
import sqlite3

CSV_PATH = "spotify_listen_record.csv"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Spotify BI Pipeline API", version="3.0", lifespan=lifespan
)


def read_and_clean_data():
    if not os.path.exists(CSV_PATH):
        raise HTTPException(status_code=404, detail="Data file not found")

    try:
        df_raw = pd.read_csv(CSV_PATH, encoding="utf-8-sig")
    except UnicodeDecodeError:
        df_raw = pd.read_csv(CSV_PATH, encoding="cp950")

    df_raw.columns = df_raw.columns.str.strip()

    # ========================================================
    # 💾 SQL DATABASE MANAGEMENT (資料庫管理核心邏輯)
    # ========================================================
    # 1. 建立輕量級 SQLite 記憶體資料庫
    conn = sqlite3.connect(":memory:")
    
    # 2. 將原始 CSV 轉入 SQL 資料表 (命名為 spotify_logs)
    df_raw.to_sql("spotify_logs", conn, index=False, if_exists="replace")
    
    # 3. 展現 SQL 能力：利用標準 SQL Query 從資料庫撈取所需的數據集
    # 這裡的 SQL 語法會將資料表內所有欄位完整取出，交給後續 Pipeline 進行特徵工程
    query = "SELECT * FROM spotify_logs"
    df = pd.read_sql_query(query, conn)
    
    # 4. 關閉資料庫連線，釋放記憶體
    conn.close()
    # ========================================================

    # 1. 核心時間與分鐘數轉換
    if "ms_played" in df.columns:
        # 統一將基礎清洗欄位命名為 聆聽總分鐘數
        df["聆聽總分鐘數"] = df["ms_played"] / 60000

    if "ts" in df.columns:
        # 轉換為時間格式，並處理時區
        df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
        # 建立 年-月 欄位供折線圖使用
        df["年月"] = df["ts"].dt.to_period("M").astype(str)

    # 2. 清洗文字空格
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip()

    return df


@app.get("/api/songs")
def get_all_songs():
    df = read_and_clean_data()
    # 轉成標準網頁傳輸格式時，將日期轉回字串
    if "ts" in df.columns:
        df["ts"] = df["ts"].astype(str)
    return df.to_dict(orient="records")


@app.get("/api/stats")
def get_stats():
    df = read_and_clean_data()

    # 動態欄位偵測
    song_col = "歌曲名" if "歌曲名" in df.columns else df.columns[3]
    artist_col = "Artist" if "Artist" in df.columns else df.columns[4]
    album_col = "Album" if "Album" in df.columns else df.columns[5]

    total_hours = 0
    if "ms_played" in df.columns:
        total_hours = round(df["ms_played"].sum() / 3600000, 1)

    # 計算不重複歌曲數（結合歌名與歌手，避免同歌名不同人算同一首）
    df["unique_song_key"] = df[song_col] + " - " + df[artist_col]
    unique_songs_count = df["unique_song_key"].nunique()

    stats = {
        "total_plays": int(df.shape[0]),
        "unique_artists": int(df[artist_col].nunique()),
        "unique_albums": int(df[album_col].nunique()),
        "unique_songs": int(unique_songs_count),
        "total_hours": total_hours,
    }
    return stats


# 1. 歌手排行數據 (供樹狀圖使用)
@app.get("/api/chart/artists")
def get_artist_chart_data():
    df = read_and_clean_data()
    artist_col = "Artist" if "Artist" in df.columns else df.columns[4]

    if artist_col not in df.columns or "聆聽總分鐘數" not in df.columns:
        return []

    # 同時計算每個歌手的 點播次數 與 聆聽分鐘數總和
    artist_summary = (
        df.groupby(artist_col)
        .agg(
            Count=(artist_col, "size"),
            Total_Minutes=("聆聽總分鐘數", "sum"),
        )
        .reset_index()
    )

    # 四捨五入分鐘數到小數點後 1 位
    artist_summary["Total_Minutes"] = artist_summary["Total_Minutes"].round(1)

    # 依點播次數由大到小排序
    artist_summary = artist_summary.sort_values(
        by="Count", ascending=False
    )

    return artist_summary.to_dict(orient="records")


# 2. 每月聆聽趨勢數據 (供折線圖使用)
@app.get("/api/chart/monthly_trend")
def get_monthly_trend():
    df = read_and_clean_data()
    if "年月" not in df.columns or "聆聽總分鐘數" not in df.columns:
        return []
    # 依照年月分組，計算聆聽分鐘數總和
    trend = df.groupby("年月")["聆聽總分鐘數"].sum().reset_index()
    trend = trend.sort_values("年月")
    trend["聆聽總分鐘數"] = trend["聆聽總分鐘數"].round(1)
    return trend.to_dict(orient="records")


# 3. 獲取 24 小時時段的聆聽分鐘數分佈數據 (供新時段長條圖使用)
@app.get("/api/chart/hourly_distribution")
def get_hourly_distribution():
    df = read_and_clean_data()

    if "ts" not in df.columns or "聆聽總分鐘數" not in df.columns:
        return []

    # 確保 ts 是時間格式
    df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
    df = df[df["ts"].notna()]

    # 核心轉換：提取小時 (0-23)，並轉換成台灣時間 (UTC+8)
    df["小時"] = (df["ts"].dt.hour + 8) % 24

    # 依小時分組，計算總聆聽分鐘數
    hourly_data = df.groupby("小時")["聆聽總分鐘數"].sum().reset_index()

    # 補齊沒有聽歌的小時（確保 0-23 點都有柱子）
    all_hours = pd.DataFrame({"小時": list(range(24))})
    hourly_data = pd.merge(all_hours, hourly_data, on="小時", how="left").fillna(0)

    # 四捨五入並依小時順序排序
    hourly_data["聆聽總分鐘數"] = hourly_data["聆聽總分鐘數"].round(1)
    hourly_data = hourly_data.sort_values(by="小時")

    return hourly_data.to_dict(orient="records")


# 4. Top 100 歌曲排行榜數據 (供表格使用)
@app.get("/api/chart/top100")
def get_top100_songs():
    df = read_and_clean_data()
    song_col = "歌曲名" if "歌曲名" in df.columns else df.columns[3]
    artist_col = "Artist" if "Artist" in df.columns else df.columns[4]

    # 以 歌曲名 + 歌手 進行分組加總，避免同名異曲狀況
    top_songs = (
        df.groupby([song_col, artist_col])["聆聽總分鐘數"].sum().reset_index()
    )
    top_songs.columns = ["歌曲名", "Artist", "總聆聽分鐘數"]
    top_songs["總聆聽分鐘數"] = top_songs["總聆聽分鐘數"].round(1)

    # 取前 100 名
    top100 = top_songs.sort_values(by="總聆聽分鐘數", ascending=False).head(100)
    return top100.to_dict(orient="records")


# 5. 獲取每年聆聽分鐘數最高的前 3 名歌手與歌曲 (年度 Top 3 榜單)
@app.get("/api/chart/yearly_champions")
def get_yearly_champions():
    df = read_and_clean_data()
    song_col = "歌曲名" if "歌曲名" in df.columns else df.columns[3]
    artist_col = "Artist" if "Artist" in df.columns else df.columns[4]

    if (
        "ts" not in df.columns
        or artist_col not in df.columns
        or song_col not in df.columns
        or "聆聽總分鐘數" not in df.columns
    ):
        return []

    # 建立 年份 欄位
    df["年份"] = df["ts"].dt.year
    df = df[df["年份"].notna()]

    yearly_data = []
    all_years = sorted(df["年份"].unique())

    for year in all_years:
        df_year = df[df["年份"] == year]
        if df_year.empty:
            continue

        # A. 撈出該年總分鐘數前 3 名的歌手
        artist_mins = df_year.groupby(artist_col)["聆聽總分鐘數"].sum().reset_index()
        top_artists_df = artist_mins.sort_values(by="聆聽總分鐘數", ascending=False).head(3)
        top_artists_list = [
            {"name": row[artist_col], "mins": round(row["聆聽總分鐘數"], 1)}
            for _, row in top_artists_df.iterrows()
        ]

        # B. 撈出該年總分鐘數前 3 名的歌曲
        song_mins = (
            df_year.groupby([song_col, artist_col])["聆聽總分鐘數"].sum().reset_index()
        )
        top_songs_df = song_mins.sort_values(by="聆聽總分鐘數", ascending=False).head(3)
        top_songs_list = [
            {"title": row[song_col], "artist": row[artist_col], "mins": round(row["聆聽總分鐘數"], 1)}
            for _, row in top_songs_df.iterrows()
        ]

        yearly_data.append(
            {
                "Year": int(year),
                "Top_Artists": top_artists_list,
                "Top_Songs": top_songs_list,
            }
        )

    return yearly_data

# 6. 獲取聆聽 不重複歌曲數 最高的前 10 名歌手 (供新長條圖使用)
@app.get("/api/chart/artist_top_song_count")
def get_artist_top_song_count():
    df = read_and_clean_data()
    song_col = "歌曲名" if "歌曲名" in df.columns else df.columns[3]
    artist_col = "Artist" if "Artist" in df.columns else df.columns[4]

    if artist_col not in df.columns or song_col not in df.columns:
        return []

    # 核心計算：先算出每位歌手 不重複 的歌曲有哪些
    unique_songs_df = df.drop_duplicates(subset=[artist_col, song_col])

    # 計算每位歌手擁有幾首不重複的歌曲，並取前 10 名
    top_artists_by_songs = (
        unique_songs_df[artist_col].value_counts().reset_index()
    )
    top_artists_by_songs.columns = ["Artist", "Song_Count"]

    top10_artists = top_artists_by_songs.head(10)

    return top10_artists.to_dict(orient="records")