"""
build.py
GitHub Actions에서 실행:
1. 구글 시트 CSV 다운로드
2. JSON 변환
3. dashboard_template.html에 주입 → dist/index.html
"""
import csv, json, os, re, urllib.request, io

SHEET_ID = '1Xz4t6uCRICov3UpQCdYUZQngo5O4YaOrwMMy6t7dNY4'
SHEETS = {
    'raw':      '791828760',
    'online':   '1839246190',
    'sample':   '1618875694',
    'purchase': '283543126',
    'other':    '48901752',
    'cls':      '679105482',
    'stock':    '1773357628',
}

def fetch_csv(gid):
    url = f'https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return list(csv.reader(io.StringIO(r.read().decode('utf-8'))))

def n(v):
    if not v or str(v).strip() in ['-', '']: return 0
    try: return float(str(v).replace(',', ''))
    except: return 0

def parse_config(prod):
    import re as _re
    m = _re.findall(r'[가-힣a-zA-Z]+(\d+)', str(prod))
    if m: return sum(int(x) for x in m) or 1
    l = _re.search(r'(\d+)\s*$', str(prod))
    return int(l.group(1)) if l else 1

def build():
    print('📥 구글 시트 CSV 다운로드 중...')

    # 상품분류 맵
    cls_rows = fetch_csv(SHEETS['cls'])
    prod_map = {}
    cat_tree = {}
    for row in cls_rows[1:]:
        if len(row) < 3 or not row[0]: continue
        cat, sub, prod = row[0].strip(), row[1].strip(), row[2].strip()
        prod_map[prod] = {'cat': cat, 'sub': sub}
        if cat not in cat_tree: cat_tree[cat] = []
        if sub and sub not in cat_tree[cat]: cat_tree[cat].append(sub)

    # RAW
    raw_rows = fetch_csv(SHEETS['raw'])
    raw = []
    for row in raw_rows[1:]:
        if len(row) < 12 or not row[0]: continue
        cat = row[11].strip() if len(row) > 11 else ''
        if not cat: continue
        prod = row[3].strip()
        info = prod_map.get(prod, {'cat': cat, 'sub': cat})
        r = {'w': row[0].strip(), 'm': row[1].strip(), 'b': row[2].strip(),
             'p': prod, 's': info['sub'], 'v': n(row[4]), 'c': parse_config(prod), 't': cat}
        if n(row[5]): r['q'] = n(row[5])
        if len(row) > 7 and n(row[7]): r['a'] = n(row[7])
        if len(row) > 8 and n(row[8]): r['l'] = n(row[8])
        raw.append(r)
    print(f'  RAW: {len(raw)}건')

    # 온라인광고비
    online_rows = fetch_csv(SHEETS['online'])
    online = []
    for row in online_rows[1:]:
        if len(row) < 6 or not row[0]: continue
        cat = row[7].strip() if len(row) > 7 else ''
        if not cat: continue
        online.append({'w': row[0].strip(), 'h': row[2].strip() if len(row) > 2 else '',
                       'y': row[3].strip() if len(row) > 3 else '',
                       'p': row[4].strip() if len(row) > 4 else '',
                       'v': n(row[5]), 't': cat})
    print(f'  온라인광고비: {len(online)}건')

    # 샘플
    sample_rows = fetch_csv(SHEETS['sample'])
    sample = []
    for row in sample_rows[1:]:
        if len(row) < 7 or not row[0]: continue
        cat = row[6].strip()
        if cat not in ['파라다이스', '아세로라']: continue
        qty, cost = n(row[3]), n(row[4])
        amt = n(row[5]) if n(row[5]) > 0 else qty * cost
        sample.append({'w': row[0].strip(), 'prod': row[2].strip(), 'qty': qty, 'cost': cost, 'amt': amt, 'cat': cat})

    # 원부자재
    pur_rows = fetch_csv(SHEETS['purchase'])
    purchase = []
    for row in pur_rows[1:]:
        if len(row) < 9 or not row[1]: continue
        cat = row[8].strip()
        if cat not in ['파라다이스', '아세로라']: continue
        purchase.append({'w': row[1].strip(), 'biz': row[2].strip(), 'prod': row[3].strip(),
                         'note': row[4].strip(), 'price': n(row[5]), 'qty': n(row[6]), 'amt': n(row[7]), 'cat': cat})

    # 기타비용
    other_rows = fetch_csv(SHEETS['other'])
    other = []
    for row in other_rows[1:]:
        if len(row) < 7 or not row[0]: continue
        cat = row[6].strip()
        if cat not in ['파라다이스', '아세로라']: continue
        other.append({'w': row[0].strip(), 'acct': row[1].strip(), 'biz': row[3].strip() if len(row) > 3 else '',
                      'amt': n(row[4]), 'note': row[5].strip() if len(row) > 5 else '', 'cat': cat})

    # 재고현황
    stock_rows = fetch_csv(SHEETS['stock'])
    stock_monthly = {}
    for row in stock_rows[1:]:
        if len(row) < 6 or not row[0]: continue
        mon, cat = row[0].strip(), row[5].strip()
        amt = n(row[2]) * n(row[3])
        if not stock_monthly.get(mon): stock_monthly[mon] = {}
        stock_monthly[mon][cat] = stock_monthly[mon].get(cat, 0) + amt

    data = {
        'raw': raw, 'online': online, 'sample': sample,
        'purchase': purchase, 'other': other,
        'cat_tree': cat_tree, 'stock_monthly': stock_monthly,
        'updated_at': __import__('datetime').datetime.now().isoformat()
    }

    # 템플릿에 주입
    with open('dashboard_template.html', 'r', encoding='utf-8') as f:
        template = f.read()

    data_json = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    html = template.replace('__DASHBOARD_DATA__', data_json)

    os.makedirs('dist', exist_ok=True)
    with open('dist/index.html', 'w', encoding='utf-8') as f:
        f.write(html)

    print(f'✅ 빌드 완료: dist/index.html ({len(html):,} bytes)')
    print(f'   업데이트 시각: {data["updated_at"]}')

if __name__ == '__main__':
    build()
