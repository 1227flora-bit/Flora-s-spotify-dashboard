import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
import pandas as pd

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
        df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")
    except UnicodeDecodeError:
        df = pd.read_csv(CSV_PATH, encoding="cp950")

    df.columns = df.columns.str.strip()

    # 1. 核心時間與分鐘數轉換
    if "ms_played" in df.columns:
        df["聆聽分鐘"] = df["ms_played"] / 60000

    if "ts" in df.columns:
        # 轉換為時間格式，並處理時區
        df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
        # 建立「年-月」欄位供折線圖使用
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

    # 核心新增：計算「不重複歌曲數」（結合歌名與歌手，避免同歌名不同人算同一首）
    df["unique_song_key"] = df[song_col] + " - " + df[artist_col]
    unique_songs_count = df["unique_song_key"].nunique()

    stats = {
        "total_plays": int(df.shape[0]),
        "unique_artists": int(df[artist_col].nunique()),
        "unique_albums": int(df[album_col].nunique()),
        "unique_songs": int(unique_songs_count),  # 🔥 新增不重複歌曲指標
        "total_hours": total_hours,
    }
    return stats


# 1. 歌手排行數據 (供樹狀圖使用)
@app.get("/api/chart/artists")
def get_artist_chart_data():
    df = read_and_clean_data()
    artist_col = "Artist" if "Artist" in df.columns else df.columns[4]

    if artist_col not in df.columns or "聆聽分鐘" not in df.columns:
        return []

    # 同時計算每個歌手的「點播次數」與「聆聽分鐘數總和」
    artist_summary = (
        df.groupby(artist_col)
        .agg(
            Count=(artist_col, "size"),
            Total_Minutes=("聆聽分鐘", "sum"),
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
    if "年月" not in df.columns or "聆聽分鐘" not in df.columns:
        return []
    # 依照年月分組，計算聆聽分鐘數總和
    trend = df.groupby("年月")["聆聽分鐘"].sum().reset_index()
    trend = trend.sort_values("年月")
    trend["聆聽分鐘"] = trend["聆聽分鐘"].round(1)
    return trend.to_dict(orient="records")


# 3. 獲取前 30 名歌手的「聆聽時間最長冠軍單曲」數據 (供新長條圖使用)
@app.get("/api/chart/artist_top_song")
def get_artist_top_song():
    df = read_and_clean_data()
    song_col = "歌曲名" if "歌曲名" in df.columns else df.columns[3]
    artist_col = "Artist" if "Artist" in df.columns else df.columns[4]

    if (
        artist_col not in df.columns
        or song_col not in df.columns
        or "聆聽分鐘" not in df.columns
    ):
        return []

    # 步驟 A: 先找出點播次數前 30 名的歌手清單（與樹狀圖同步）
    top_30_artists = df[artist_col].value_counts().head(30).index.tolist()

    # 篩選資料，只留下這 30 位歌手的紀錄
    df_sub = df[df[artist_col].isin(top_30_artists)]

    # 步驟 B: 計算「每位歌手、每首歌曲」的總聆聽分鐘數
    song_minutes = (
        df_sub.groupby([artist_col, song_col])["聆聽分鐘"].sum().reset_index()
    )

    # 步驟 C: 找出每位歌手聆聽分鐘數最高（Rank 1）的那首歌
    # idxmax() 可以精準抓出每組最大值的索引位置
    top_songs_idx = song_minutes.groupby(artist_col)["聆聽分鐘"].idxmax()
    final_top_songs = song_minutes.loc[top_songs_idx].copy()

    # 欄位重新命名方便前端讀取
    final_top_songs.columns = ["Artist", "Song_Name", "Minutes"]
    final_top_songs["Minutes"] = final_top_songs["Minutes"].round(1)

    # 建立一個結合「歌手 + 歌名」的標籤，讓長條圖 Y 軸一目了然
    final_top_songs["Display_Label"] = (
        final_top_songs["Artist"] + " - 《" + final_top_songs["Song_Name"] + "》"
    )

    # 依分鐘數由大到小排序
    final_top_songs = final_top_songs.sort_values(
        by="Minutes", ascending=False
    )

    return final_top_songs.to_dict(orient="records")


# 4. Top 100 歌曲排行榜數據 (供表格使用)
@app.get("/api/chart/top100")
def get_top100_songs():
    df = read_and_clean_data()
    song_col = "歌曲名" if "歌曲名" in df.columns else df.columns[3]
    artist_col = "Artist" if "Artist" in df.columns else df.columns[4]

    # 以 歌曲名 + 歌手 進行分組加總，避免同名異曲狀況
    top_songs = (
        df.groupby([song_col, artist_col])["聆聽分鐘"].sum().reset_index()
    )
    top_songs.columns = ["歌曲名", "Artist", "總聆聽分鐘數"]
    top_songs["總聆聽分鐘數"] = top_songs["總聆聽分鐘數"].round(1)

    # 取前 100 名
    top100 = top_songs.sort_values(by="總聆聽分鐘數", ascending=False).head(
        100
    )
    return top100.to_dict(orient="records")

# 5. 獲取每年聆聽分鐘數最高的歌手與歌曲 (年度冠軍王)
@app.get("/api/chart/yearly_champions")
def get_yearly_champions():
    df = read_and_clean_data()
    song_col = "歌曲名" if "歌曲名" in df.columns else df.columns[3]
    artist_col = "Artist" if "Artist" in df.columns else df.columns[4]

    if (
        "ts" not in df.columns
        or artist_col not in df.columns
        or song_col not in df.columns
        or "聆聽分鐘" not in df.columns
    ):
        return []

    # 建立「年份」欄位
    df["年份"] = df["ts"].dt.year
    # 過濾掉時間轉換失敗的無效年份
    df = df[df["年份"].notna()]

    yearly_data = []
    all_years = sorted(df["年份"].unique())

    for year in all_years:
        df_year = df[df["年份"] == year]
        if df_year.empty:
            continue

        # A. 找出該年總分鐘數最高的歌手
        artist_mins = df_year.groupby(artist_col)["聆聽分鐘"].sum()
        top_artist = artist_mins.idxmax()
        top_artist_mins = round(artist_mins.max(), 1)

        # B. 找出該年總分鐘數最高的歌曲
        song_mins = (
            df_year.groupby([song_col, artist_col])["聆聽分鐘"].sum().reset_index()
        )
        top_song_row = song_mins.loc[song_mins["聆聽分鐘"].idxmax()]
        top_song = top_song_row[song_col]
        top_song_artist = top_song_row[artist_col]
        top_song_mins = round(top_song_row["聆聽分鐘"], 1)

        yearly_data.append(
            {
                "Year": int(year),
                "Top_Artist": top_artist,
                "Artist_Minutes": top_artist_mins,
                "Top_Song": f"《{top_song}》({top_song_artist})",
                "Song_Minutes": top_song_mins,
            }
        )

    return yearly_data