import streamlit as st
import sqlite3
import pandas as pd

# 페이지 기본 설정
st.set_page_config(page_title="Spotify 맞춤형 곡 추천 시스템", page_icon="🎵", layout="wide")

# DB 연결 함수
def get_db_connection():
    return sqlite3.connect('spotify.db')

# 모든 트랙 목록 불러오기 (캐싱하여 속도 최적화)
@st.cache_data
def load_all_tracks():
    conn = get_db_connection()
    # 장바구니 검색용으로 곡명과 아티스트를 합친 표시용 이름 생성
    query = "SELECT DISTINCT track_id, track_name, track_artist FROM TRACK"
    df = pd.read_sql_query(query, conn)
    df['display_name'] = df['track_name'] + " - " + df['track_artist']
    conn.close()
    return df

# 기존 추천 SQL 실행 함수 (생략 없이 그대로 유지)
def get_recommendations(playlist_id, option, top_n=10):
    conn = get_db_connection()
    info_query = f"SELECT DISTINCT playlist_genre, playlist_subgenre FROM TRACK WHERE playlist_id = '{playlist_id}'"
    info_df = pd.read_sql_query(info_query, conn)
    user_genre = info_df['playlist_genre'].iloc[0]
    user_subgenre = info_df['playlist_subgenre'].iloc[0]
    
    if option == "1":
        sql = f"""
        WITH user_audio_profile AS (
            SELECT 
                AVG(danceability) AS avg_dance, AVG(energy) AS avg_energy,
                AVG(valence) AS avg_valence, AVG(acousticness) AS avg_acoustic
            FROM TRACK WHERE playlist_id = '{playlist_id}'
        ),
        target_subgenre_list AS (
            SELECT DISTINCT playlist_subgenre FROM TRACK WHERE playlist_id = '{playlist_id}'
        )
        SELECT DISTINCT
            '🎯 취향 저격' AS [추천 방식],
            t.track_name AS [곡명], t.track_artist AS [아티스트],
            t.playlist_genre AS [상위장르], t.playlist_subgenre AS [하위장르],
            t.track_popularity AS [인기도],
            ROUND(SQRT(POWER(t.danceability - p.avg_dance, 2) + POWER(t.energy - p.avg_energy, 2) + 
                       POWER(t.valence - p.avg_valence, 2) + POWER(t.acousticness - p.avg_acoustic, 2)), 4) AS [오디오 거리]
        FROM TRACK t CROSS JOIN user_audio_profile p
        WHERE t.playlist_subgenre IN (SELECT playlist_subgenre FROM target_subgenre_list)
          AND t.track_id NOT IN (SELECT track_id FROM TRACK WHERE playlist_id = '{playlist_id}')
        ORDER BY [오디오 거리] ASC, t.track_popularity DESC LIMIT {top_n};
        """
    result_df = pd.read_sql_query(sql, conn)
    conn.close()
    return result_df

# [NEW] 가상 플레이리스트 맞춤형 추천 함수 (팀원 피드백 해결 알고리즘)
def get_virtual_recommendations(selected_track_ids, top_n_per_track=4):
    conn = get_db_connection()
    
    # 1. 장바구니에 담은 곡들의 4가지 특성 가져오기
    placeholders = ','.join(['?'] * len(selected_track_ids))
    query = f"""
        SELECT track_id, track_name, track_artist, danceability, energy, valence, acousticness 
        FROM TRACK WHERE track_id IN ({placeholders})
    """
    cart_df = pd.read_sql_query(query, conn, params=selected_track_ids)
    
    # 2. [문제 해결법 3: Min-Max 울타리 필터링]
    # 장바구니 곡들의 최소~최대값을 구해 엉뚱한 수치의 곡이 섞이는 것을 원천 차단합니다.
    # (너무 조건이 빡빡해지는 것을 막기 위해 위아래로 10%(0.1)의 여유 버퍼를 둡니다.)
    buffer = 0.1
    min_d, max_d = max(0, cart_df['danceability'].min() - buffer), min(1, cart_df['danceability'].max() + buffer)
    min_e, max_e = max(0, cart_df['energy'].min() - buffer), min(1, cart_df['energy'].max() + buffer)
    min_v, max_v = max(0, cart_df['valence'].min() - buffer), min(1, cart_df['valence'].max() + buffer)
    min_a, max_a = max(0, cart_df['acousticness'].min() - buffer), min(1, cart_df['acousticness'].max() + buffer)

    recommended_list = []
    
    # 3. [문제 해결법 2: 개별 곡 기준 타겟팅]
    # 뭉뚱그려 전체 평균을 내지 않고, 장바구니에 담긴 '각각의 곡'을 기준으로 가장 가까운 곡을 개별적으로 찾습니다.
    for _, row in cart_df.iterrows():
        t_dance, t_energy, t_val, t_acous = row['danceability'], row['energy'], row['valence'], row['acousticness']
        
        sql = f"""
        SELECT DISTINCT
            '✨ 가상 취향저격' AS [추천 방식],
            track_name AS [곡명], track_artist AS [아티스트],
            track_popularity AS [인기도],
            ROUND(SQRT(POWER(danceability - {t_dance}, 2) + POWER(energy - {t_energy}, 2) + 
                       POWER(valence - {t_val}, 2) + POWER(acousticness - {t_acous}, 2)), 4) AS [오디오 거리]
        FROM TRACK 
        WHERE track_id NOT IN ({placeholders})
          -- Min-Max 울타리 필터링 적용 (평균의 함정 방어)
          AND danceability BETWEEN {min_d} AND {max_d}
          AND energy BETWEEN {min_e} AND {max_e}
          AND valence BETWEEN {min_v} AND {max_v}
          AND acousticness BETWEEN {min_a} AND {max_a}
        ORDER BY [오디오 거리] ASC, track_popularity DESC
        LIMIT {top_n_per_track};
        """
        res_df = pd.read_sql_query(sql, conn, params=selected_track_ids)
        recommended_list.append(res_df)
        
    conn.close()
    
    # 4. 개별적으로 찾아온 곡들을 하나로 합치고, 중복 제거 후 최종 10곡만 추려냅니다.
    if recommended_list:
        final_df = pd.concat(recommended_list, ignore_index=True)
        final_df = final_df.drop_duplicates(subset=['곡명', '아티스트']).sort_values('오디오 거리')
        return final_df.head(10)
    else:
        return pd.DataFrame()


# --- 메인 화면 UI 시작 ---
st.title("🎧 Spotify 맞춤형 곡 추천 시스템")
st.markdown("데이터베이스 분석 및 가상 장바구니를 활용한 맞춤형 추천 알고리즘을 제공합니다.")

# 모드 선택 라디오 버튼
mode = st.radio("🛠️ 작동 모드를 선택하세요:", 
                ["1. 기존 데이터베이스 플레이리스트 분석", "2. 내 맘대로 가상 플레이리스트 만들기 (장바구니 담기)"])

st.markdown("---")

if mode == "1. 기존 데이터베이스 플레이리스트 분석":
    conn = get_db_connection()
    playlist_df = pd.read_sql_query("SELECT DISTINCT playlist_id, playlist_name, playlist_genre FROM TRACK", conn)
    
    st.subheader("⚙️ 기존 플레이리스트 선택")
    selected_playlist_name = st.selectbox("DB에 있는 플레이리스트를 고르세요:", playlist_df['playlist_name'].unique())
    target_playlist_id = playlist_df[playlist_df['playlist_name'] == selected_playlist_name].iloc[0]['playlist_id']
    
    if st.button("🎯 DB 기준 취향 저격 추천받기"):
        df_res1 = get_recommendations(target_playlist_id, option="1")
        st.dataframe(df_res1, use_container_width=True)
    conn.close()

else:
    # [NEW] 가상 플레이리스트 모드 UI
    st.subheader("🛒 내 취향 장바구니 담기")
    st.info("DB에 있는 28,000여 곡 중 취향에 맞는 곡을 검색해서 장바구니에 담아보세요!")
    
    track_db = load_all_tracks()
    
    # 멀티셀렉트(다중 선택) 위젯으로 장바구니 기능 구현
    selected_display_names = st.multiselect(
        "곡명이나 아티스트명을 검색하여 선택하세요:",
        options=track_db['display_name'],
        placeholder="여기를 클릭해 곡을 검색하고 선택하세요..."
    )
    
    if selected_display_names:
        # 선택한 표시용 이름들을 바탕으로 실제 track_id 추출
        selected_track_ids = track_db[track_db['display_name'].isin(selected_display_names)]['track_id'].tolist()
        
        st.success(f"총 {len(selected_track_ids)}곡이 장바구니에 담겼습니다! (평균을 내지 않고 개별 타겟팅 및 Min-Max 울타리 기술이 적용됩니다.)")
        
        if st.button("✨ 가상 장바구니 기반 추천받기"):
            with st.spinner('장바구니 곡들의 4가지 특성을 분석하여 알고리즘을 돌리고 있습니다...'):
                virtual_res_df = get_virtual_recommendations(selected_track_ids)
                
                if not virtual_res_df.empty:
                    st.dataframe(virtual_res_df, use_container_width=True)
                else:
                    st.warning("선택하신 곡들의 성향 차이가 너무 커서 Min-Max 울타리를 통과한 곡이 없습니다. 비슷한 분위기의 곡으로 다시 선택해 보세요!")
