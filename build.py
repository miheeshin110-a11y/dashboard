"""
build.py
GitHub Actions에서 실행:
1. 구글 시트 CSV 다운로드
2. JSON 변환
3. dashboard_template.html에 주입 → dist/index.html
"""
import csv, json, os, re, urllib.request, io

SHEET_ID = '1Jfrh61zqUb5jQsh3yZiLXh4hp_vF2n9_mo6cRE5a3gc'
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

# 원장 중분류/대분류 표기 불일치 정정 — 같은 상품인데 다른 라벨로 기록된 경우 정규화.
# (원인 파악: 올인원프리/원데이올인원, 올레/올레샷 — 올레샷은 대분류까지 잘못 들어간 행 있음)
SUB_ALIAS = {'원데이올인원': '올인원프리', '올레': '올레샷'}
CAT_ALIAS = {'올레샷': '기타'}

def build():
    print('📥 구글 시트 CSV 다운로드 중...')

    # 상품분류 맵 (대분류→중분류 트리 구조만 사용, SKU→중분류 매핑은 RAW 자체 컬럼 사용)
    cls_rows = fetch_csv(SHEETS['cls'])
    cat_tree = {}
    for row in cls_rows[1:]:
        if len(row) < 3 or not row[0]: continue
        cat, sub = row[0].strip(), row[1].strip()
        if cat not in cat_tree: cat_tree[cat] = []
        if sub and sub not in cat_tree[cat]: cat_tree[cat].append(sub)

    # RAW
    raw_rows = fetch_csv(SHEETS['raw'])
    raw = []
    for row in raw_rows[1:]:
        if len(row) < 12 or not row[0]: continue
        cat = row[11].strip() if len(row) > 11 else ''
        if not cat: continue
        cat = CAT_ALIAS.get(cat, cat)
        prod = row[3].strip()
        # 중분류는 RAW 시트 자체 컬럼(row[12])을 그대로 사용 — ONLINE.중분류와 같은 분류체계라
        # cls 시트(상품분류) 매핑보다 더 완전하고 정확함 (cls 매핑은 342개 실 SKU 중 256개만 커버).
        sub = row[12].strip() if len(row) > 12 else ''
        if not sub: sub = cat
        sub = SUB_ALIAS.get(sub, sub)
        # 단위박스(O)/단위박스(2)(P) — v6: 원장 자체 컬럼(직접 파싱해 넣어둔 값)을 그대로 사용.
        # 실 판매(qty)는 "박스"가 아니라 "세트/건수" — 총박스수 = qty × (O+P).
        # O 공란은 낱개(1)로 폴백(비-SKU 노이즈 제외하면 실매출 있는 공란은 2건뿐, 176만원 수준으로 영향 미미).
        o_raw = row[14].strip() if len(row) > 14 else ''
        p_raw = row[15].strip() if len(row) > 15 else ''
        o = n(o_raw) if o_raw else 1
        p = n(p_raw) if p_raw else 0
        r = {'w': row[0].strip(), 'm': row[1].strip(), 'b': row[2].strip(),
             'p': prod, 's': sub, 'v': n(row[4]), 'c': o + p, 'o': o, 'p2': p, 't': cat}
        if n(row[5]): r['q'] = n(row[5])
        if len(row) > 7 and n(row[7]): r['a'] = n(row[7])
        if len(row) > 8 and n(row[8]): r['l'] = n(row[8])
        if len(row) > 9 and n(row[9]): r['g'] = n(row[9])  # 개런티(정액비) — 방송 MER 계산용
        raw.append(r)
    print(f'  RAW: {len(raw)}건')

    # 온라인광고비
    online_rows = fetch_csv(SHEETS['online'])
    online = []
    for row in online_rows[1:]:
        if len(row) < 6 or not row[0]: continue
        cat = row[7].strip() if len(row) > 7 else ''
        if not cat: continue
        cat = CAT_ALIAS.get(cat, cat)
        sub = row[8].strip() if len(row) > 8 else ''
        sub = SUB_ALIAS.get(sub, sub)
        online.append({'w': row[0].strip(), 'h': row[2].strip() if len(row) > 2 else '',
                       'y': row[3].strip() if len(row) > 3 else '',
                       'p': row[4].strip() if len(row) > 4 else '',
                       'v': n(row[5]), 't': cat,
                       's': sub})
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
