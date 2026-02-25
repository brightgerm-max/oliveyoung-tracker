"""
올리브영 랭킹 수집기 — 최종 버전
셀렉터: .prd_info (100개 확인)
순위: span.thumb_flag.best 텍스트
"""

import os
import sys
import time
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

GAS_WEB_APP_URL = os.environ.get("GAS_WEB_APP_URL", "")
SECRET          = os.environ.get("SECRET", "oliveyoung_secret_2026")

CATEGORIES = [
    {"name": "전체TOP100", "catNo": "900000100100001"},
    {"name": "스킨케어",   "catNo": "900000100100002"},
]
TOP_N = 100
KST   = timezone(timedelta(hours=9))


def fetch_ranking(cat_no: str, page) -> list:
    url = (
        "https://www.oliveyoung.co.kr/store/main/getBestList.do"
        f"?dispCatNo={cat_no}&fltDispCatNo=&pageIdx=0&rowsPerPage=0"
    )
    # networkidle: 모든 네트워크 요청 완료 후 파싱 (동적 렌더링 대응)
    page.goto(url, wait_until="networkidle", timeout=40000)

    # .prd_info가 나타날 때까지 최대 10초 대기
    try:
        page.wait_for_selector(".prd_info", timeout=10000)
    except Exception:
        print("  .prd_info 대기 시간 초과 — 현재 HTML로 파싱 시도")

    return parse_html(page.content())


def parse_html(html: str) -> list:
    soup      = BeautifulSoup(html, "html.parser")
    prd_infos = soup.select(".prd_info")
    print(f"  .prd_info {len(prd_infos)}개 발견")

    items = []
    for info in prd_infos[:TOP_N]:
        try:
            # 순위: span.thumb_flag 텍스트 (01, 02, ...)
            rank_el = info.select_one(".thumb_flag")
            rank    = int(rank_el.get_text(strip=True)) if rank_el else len(items) + 1

            brand_el  = info.select_one(".tx_brand")
            name_el   = info.select_one(".tx_name")
            brand     = brand_el.get_text(strip=True) if brand_el else ""
            name      = name_el.get_text(strip=True)  if name_el  else ""
            if not brand and not name:
                continue

            cur_el    = info.select_one(".tx_cur .tx_num")
            org_el    = info.select_one(".tx_org .tx_num")
            cur_price = int(cur_el.get_text(strip=True).replace(",", "")) if cur_el else 0
            org_price = int(org_el.get_text(strip=True).replace(",", "")) if org_el else cur_price
            discount  = (
                round((1 - cur_price / org_price) * 100)
                if org_price > 0 and cur_price > 0 and org_price != cur_price else 0
            )

            # 옵션 플래그 — prd_info 전체 HTML에서 탐색
            scope = str(info)
            items.append({
                "rank":        rank,
                "brand":       brand,
                "name":        name,
                "curPrice":    cur_price,
                "orgPrice":    org_price,
                "discount":    discount,
                "hasSale":     "Y" if "sale"     in scope else "",
                "hasCoupon":   "Y" if "coupon"   in scope else "",
                "hasGift":     "Y" if "gift"     in scope else "",
                "hasDelivery": "Y" if "delivery" in scope else "",
            })
        except Exception as ex:
            print(f"  파싱 오류: {ex}")

    return items


def main():
    if not GAS_WEB_APP_URL:
        print("❌ GAS_WEB_APP_URL 환경변수가 없습니다.")
        sys.exit(1)

    now      = datetime.now(KST)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    print(f"[{date_str} {time_str} KST] 수집 시작")

    all_rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
            viewport={"width": 1280, "height": 900},
            extra_http_headers={"Accept-Language": "ko-KR,ko;q=0.9"},
        )
        context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )
        page = context.new_page()

        print("  메인 페이지 방문 중...")
        try:
            page.goto("https://www.oliveyoung.co.kr/store/main/main.do",
                      wait_until="networkidle", timeout=25000)
            time.sleep(1)
        except Exception as e:
            print(f"  메인 페이지 방문 실패 (무시): {e}")

        for cat in CATEGORIES:
            print(f"  [{cat['name']}] 수집 중...")
            try:
                items = fetch_ranking(cat["catNo"], page)
                print(f"  [{cat['name']}] ✅ {len(items)}건")
                for item in items:
                    all_rows.append({
                        "dateStr":  date_str,
                        "timeStr":  time_str,
                        "category": cat["name"],
                        **item,
                    })
                time.sleep(2)
            except Exception as e:
                print(f"  [{cat['name']}] ⚠️ 실패: {e}")

        browser.close()

    if not all_rows:
        print("❌ 수집된 데이터 없음")
        sys.exit(1)

    print(f"\n  GAS 전송 중... ({len(all_rows)}건)")
    try:
        resp   = requests.post(
            GAS_WEB_APP_URL,
            json={
                "secret":  SECRET,
                "dateStr": date_str,
                "timeStr": time_str,
                "rows":    all_rows,
            },
            timeout=60,
        )
        result = resp.json()
        if result.get("ok"):
            print(f"  ✅ 저장 완료: {result.get('saved')}건")
        else:
            print(f"  ❌ GAS 오류: {result.get('error')}")
            sys.exit(1)
    except Exception as e:
        print(f"  ❌ 전송 실패: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
