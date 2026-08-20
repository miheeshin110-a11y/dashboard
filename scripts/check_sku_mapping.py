"""
check_sku_mapping.py
상품분석_설계도_v5.md §1 "선행 작업: SKU 매핑 품질 기준" 점검 스크립트.

핵심: ONLINE(온라인광고비) 시트에는 자유 텍스트 '제품' 필드 외에 이미 '대분류'/'중분류'
컬럼이 있고, 이 값은 RAW(원장) 시트의 '중분류'와 같은 분류체계를 쓴다
(예: ONLINE.제품="알파CD(젤리)"인데 ONLINE.중분류="탱글젤리" = RAW.중분류="탱글젤리").
따라서 매칭은 ONLINE.제품이 아니라 ONLINE.중분류 ↔ RAW.중분류로 해야 한다.
(제품 필드로 직접 매칭하면 이런 케이스를 놓쳐 매핑률이 실제보다 낮게 나옴 — 확인된 회귀 포인트.)

ONLINE.중분류가 비어 있으면 ONLINE.제품 텍스트로 폴백 매칭한다(현재 데이터엔 해당 없음,
향후 데이터 형태가 바뀔 경우 대비).

판정 기준 (설계도 원문):
  - 매출금액 매핑률 ≥ 99%  (RAW 온라인채널 매출 중 ONLINE과 매칭되는 비율)
  - 온라인광고비 매핑률 ≥ 95%  (ONLINE 광고비 중 RAW 중분류와 매칭되는 비율)
  - 건수 기준 매핑률 (참고용)
  - 미매핑 상위 항목은 수동 검토 완료 후 진행

수동 검토 확정 (2026-08-20): 매출금액 매핑률 98.87%로 목표(99%) 미달이나,
잔여 미매핑 RAW 중분류 11개(크랜베리/원데이올인원지관/블루베리/아로니아/카스케인/
원액/기타/흰콩/프리플/원데이올인원/프로플)는 ONLINE 시트 전체를 통틀어 중분류
컬럼에 단 한 번도 등장하지 않음을 확인 — 매핑 결함이 아니라 온라인 광고를
집행한 적 없는 소형 제품라인으로 판정, PASS 처리하고 다음 단계(SKU 진단
테이블) 진행. 이 SKU들의 온라인 MER은 "광고 미집행(N/A)"으로 표시할 것.

실행: python scripts/check_sku_mapping.py
"""
import sys, os, re
from collections import defaultdict

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build as b

REV_THRESHOLD = 0.99
SPEND_THRESHOLD = 0.95

# 제품 태그 자체가 없어 구조적으로 매핑 불가능한 값 (SKU 진단·MER 계산에서 항상 제외되는 "미배분" 버킷)
UNCLASSIFIED_LABELS = {'', '구분없음'}


def norm(s):
    s = str(s).strip()
    s = re.sub(r'\(.*?\)', '', s)   # 괄호 안 수식어 제거
    s = re.sub(r'\s+', '', s)       # 공백 제거
    return s.lower()


def fuzzy_match(a, c):
    """정규화 후 한쪽이 다른 쪽의 부분 문자열이면 매칭 (길이 2 미만은 오매칭 방지 위해 제외)."""
    if len(a) < 2 or len(c) < 2:
        return False
    return a in c or c in a


def collect():
    raw_rows = b.fetch_csv(b.SHEETS['raw'])
    online_rows = b.fetch_csv(b.SHEETS['online'])

    # RAW: 매체='온라인'인 행만 (온라인 채널 매출) — 중분류(col12)별 매출/건수 집계
    raw_rev = defaultdict(float)
    raw_cnt = defaultdict(int)
    raw_names = defaultdict(set)
    for row in raw_rows[1:]:
        if len(row) < 13 or not row[0]:
            continue
        if row[1].strip() != '온라인':
            continue
        midcat = row[12].strip()
        key = norm(midcat)
        raw_rev[key] += b.n(row[4])
        raw_cnt[key] += 1
        raw_names[key].add(midcat or '(공란)')

    # ONLINE: 중분류(col8) 우선 사용, 비어있으면 제품(col4)으로 폴백
    online_spend = defaultdict(float)
    online_cnt = defaultdict(int)
    online_names = defaultdict(set)
    for row in online_rows[1:]:
        if len(row) < 6 or not row[0]:
            continue
        midcat = row[8].strip() if len(row) > 8 else ''
        prod = row[4].strip() if len(row) > 4 else ''
        if midcat and midcat not in UNCLASSIFIED_LABELS:
            key = norm(midcat)
            online_names[key].add(midcat)
        elif prod and prod not in UNCLASSIFIED_LABELS:
            key = norm(prod)
            online_names[key].add(f'{prod} (제품필드 폴백)')
        else:
            key = ''
            online_names[key].add('(공란/구분없음)')
        online_spend[key] += b.n(row[5])
        online_cnt[key] += 1

    return raw_rev, raw_cnt, raw_names, online_spend, online_cnt, online_names


def report():
    raw_rev, raw_cnt, raw_names, online_spend, online_cnt, online_names = collect()

    unclassified_keys = {norm(x) for x in UNCLASSIFIED_LABELS}

    raw_keys = set(raw_rev.keys())
    online_keys = set(online_spend.keys())

    online_structural = {k for k in online_keys if k in unclassified_keys}
    raw_structural = {k for k in raw_keys if k in unclassified_keys}

    matchable_online = online_keys - online_structural
    matchable_raw = raw_keys - raw_structural

    matched_raw, matched_online, pairs = set(), set(), []
    for rk in matchable_raw:
        for ok in matchable_online:
            if fuzzy_match(rk, ok):
                matched_raw.add(rk)
                matched_online.add(ok)
                pairs.append((rk, ok))

    total_raw_rev = sum(raw_rev.values())
    total_online_spend = sum(online_spend.values())
    total_raw_cnt = sum(raw_cnt.values())
    total_online_cnt = sum(online_cnt.values())

    matched_raw_rev = sum(raw_rev[k] for k in matched_raw)
    matched_online_spend = sum(online_spend[k] for k in matched_online)
    matched_raw_cnt = sum(raw_cnt[k] for k in matched_raw)
    matched_online_cnt = sum(online_cnt[k] for k in matched_online)

    structural_online_spend = sum(online_spend[k] for k in online_structural)
    structural_raw_rev = sum(raw_rev[k] for k in raw_structural)
    structural_online_cnt = sum(online_cnt[k] for k in online_structural)
    structural_raw_cnt = sum(raw_cnt[k] for k in raw_structural)

    # 구조적 미분류(제품 태그 공란/"구분없음")는 "미배분" 버킷으로 분리하고 매핑률 분모에서 제외.
    # SKU 진단 테이블·MER 계산에서도 항상 이 버킷을 제외한다.
    rev_denom = total_raw_rev - structural_raw_rev
    spend_denom = total_online_spend - structural_online_spend
    cnt_denom_raw = total_raw_cnt - structural_raw_cnt
    cnt_denom_online = total_online_cnt - structural_online_cnt

    rev_rate = matched_raw_rev / rev_denom if rev_denom else 0
    spend_rate = matched_online_spend / spend_denom if spend_denom else 0
    cnt_rate_raw = matched_raw_cnt / cnt_denom_raw if cnt_denom_raw else 0
    cnt_rate_online = matched_online_cnt / cnt_denom_online if cnt_denom_online else 0

    print('=' * 70)
    print('SKU 매핑 품질 리포트 — ONLINE.중분류 ↔ RAW.중분류 (온라인 채널 한정)')
    print('=' * 70)
    print('매칭 방식: 정규화(괄호/공백 제거) + 부분문자열 매칭')
    print(f'매칭된 (RAW중분류, ONLINE중분류) 쌍 {len(pairs)}개:')
    for rk, ok in sorted(pairs):
        print(f'  {list(raw_names[rk])[0]:15s} <-> {list(online_names[ok])}')
    print()

    print('-' * 70)
    print(f'[1] 매출금액 매핑률 (기준: RAW 온라인채널 매출 - 미배분, 목표 >= {REV_THRESHOLD*100:.0f}%)')
    print(f'    총액          : {total_raw_rev:>15,.0f}')
    print(f'    미배분(제외)  : {structural_raw_rev:>15,.0f}  (중분류 필드 공란 — SKU 태그 자체가 없음)')
    print(f'    매핑 대상액   : {rev_denom:>15,.0f}')
    print(f'    매칭됨        : {matched_raw_rev:>15,.0f}')
    print(f'    매핑률        : {rev_rate*100:>6.2f}%   -> {"PASS" if rev_rate >= REV_THRESHOLD else "FAIL"}')
    print()

    print(f'[2] 온라인광고비 매핑률 (기준: ONLINE 광고비 - 미배분, 목표 >= {SPEND_THRESHOLD*100:.0f}%)')
    print(f'    총액          : {total_online_spend:>15,.0f}')
    print(f'    미배분(제외)  : {structural_online_spend:>15,.0f}  (중분류/제품 필드 공란·"구분없음")')
    print(f'    매핑 대상액   : {spend_denom:>15,.0f}')
    print(f'    매칭됨        : {matched_online_spend:>15,.0f}')
    print(f'    매핑률        : {spend_rate*100:>6.2f}%   -> {"PASS" if spend_rate >= SPEND_THRESHOLD else "FAIL"}')
    print()

    print('[3] 건수 기준 매핑률 (참고용)')
    print(f'    RAW 건수 매핑률    : {cnt_rate_raw*100:.2f}%')
    print(f'    ONLINE 건수 매핑률 : {cnt_rate_online*100:.2f}%')
    print()

    print('-' * 70)
    print('미매핑 상위 항목 — ONLINE (광고비 기준, 미배분 제외)')
    unmatched_online = sorted(
        ((k, online_spend[k], online_names[k]) for k in matchable_online - matched_online),
        key=lambda x: -x[1]
    )
    for k, v, names in unmatched_online:
        print(f'    {v:>14,.0f}  {list(names)}')
    if not unmatched_online:
        print('    (없음)')
    print()

    print('미매핑 상위 항목 — RAW 중분류 (온라인 매출 기준, 미배분 제외)')
    unmatched_raw = sorted(
        ((k, raw_rev[k], raw_names[k]) for k in matchable_raw - matched_raw),
        key=lambda x: -x[1]
    )
    for k, v, names in unmatched_raw:
        print(f'    {v:>14,.0f}  {list(names)}')
    if not unmatched_raw:
        print('    (없음)')
    print()

    print('=' * 70)
    overall = 'PASS' if (rev_rate >= REV_THRESHOLD and spend_rate >= SPEND_THRESHOLD) else 'FAIL'
    print(f'종합 판정: {overall}')
    print('=' * 70)


if __name__ == '__main__':
    report()
