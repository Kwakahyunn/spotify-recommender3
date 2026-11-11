import sqlite3
import pandas as pd
import os

# CSV 파일 이름 확인 (경로에 맞게 수정)
csv_file_name = 'spotify_songs_final.csv' 

if not os.path.exists(csv_file_name):
    print(f"오류: 현재 폴더에 '{csv_file_name}' 파일이 없습니다. 확인해주세요!")
else:
    # 1. CSV 데이터 읽어오기
    print("CSV 파일을 읽어오는 중입니다...")
    df = pd.read_csv(csv_file_name)

    # 2. SQLite DB 연결 (파일이 없으면 새로 생성됨)
    print("데이터베이스에 연결하는 중입니다...")
    conn = sqlite3.connect('spotify.db')

    # 3. 데이터프레임을 DB의 'TRACK' 테이블로 저장 (기존에 있으면 덮어쓰기)
    print("'TRACK' 테이블을 생성하고 데이터를 넣는 중입니다...")
    df.to_sql('TRACK', conn, if_exists='replace', index=False)

    conn.close()
    print("✅ 성공! 'spotify.db' 파일이 성공적으로 생성되었습니다.")