"""
build.py
GitHub Actions에서 실행: data/dashboard.json → dist/index.html
"""
import json, os, re

# 경로
TEMPLATE = 'dashboard_template.html'
DATA_FILE = 'data/dashboard.json'
OUT_DIR   = 'dist'
OUT_FILE  = os.path.join(OUT_DIR, 'index.html')

def build():
    # 1. 템플릿 읽기
    with open(TEMPLATE, 'r', encoding='utf-8') as f:
        template = f.read()

    # 2. 데이터 읽기
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 3. 플레이스홀더 교체
    data_json = json.dumps(data, ensure_ascii=False)
    html = template.replace('__DASHBOARD_DATA__', data_json)

    # 4. 출력
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f'✅ 빌드 완료: {OUT_FILE} ({len(html):,} bytes)')
    updated = data.get('updated_at', '알 수 없음')
    print(f'   데이터 업데이트 시각: {updated}')

if __name__ == '__main__':
    build()
