"""
올리브영 랭킹 수집기 — GitHub Actions 실행용
- Actions에서는 1회 실행 후 종료 (schedule은 워크플로우가 담당)
- GAS_WEB_APP_URL, SECRET은 환경변수(GitHub Secrets)에서 읽음
"""

import os
import sys
import time
import requests
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# ──────────────────────────────────────────
# 설정 — GitHub Secrets에서 자동으로 읽음
# ──────────────────────────────────────────
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
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    try:
        page.wait_for_selector("li.prd_item", timeout=10000)
    except Exception:
        print("  셀렉터 대기 시간 초과 — 현재 HTML로 파싱 시도")
    return parse_html(page.content())


def parse_html(html: str) -> list:
    soup    = BeautifulSoup(html, "html.parser")
    li_list = (
        soup.select(".cate_prd_list li.prd_item") or
        soup.select("li.prd_item") or
        soup.select("li[class*='prd_item']")
    )
    items = []
    for idx, li in enumerate(li_list[:TOP_N]):
        try:
            brand_el  = li.select_one(".tx_brand") or li.select_one("[class*='tx_brand']")
            name_el   = li.select_one(".tx_name")  or li.select_one("[class*='tx_name']")
            brand     = brand_el.get_text(strip=True) if brand_el else ""
            name      = name_el.get_text(strip=True)  if name_el  else ""
            if not brand and not name:
                continue

            cur_el    = li.select_one(".tx_cur .tx_num")
            org_el    = li.select_one(".tx_org .tx_num")
            cur_price = int(cur_el.get_text(strip=True).replace(",", "")) if cur_el else 0
            org_price = int(org_el.get_text(strip=True).replace(",", "")) if org_el else cur_price
            discount  = (
                round((1 - cur_price / org_price) * 100)
                if org_price > 0 and cur_price > 0 and org_price != cur_price else 0
            )
            flags = " ".join(" ".join(c.get("class", [])) for c in li.select(".icon_flag"))

            items.append({
                "rank":        idx + 1,
                "brand":       brand,
                "name":        name,
                "curPrice":    cur_price,
                "orgPrice":    org_price,
                "discount":    discount,
                "hasSale":     "Y" if "sale"     in flags else "",
                "hasCoupon":   "Y" if "coupon"   in flags else "",
                "hasGift":     "Y" if "gift"     in flags else "",
                "hasDelivery": "Y" if "delivery" in flags else "",
            })
        except Exception as e:
            print(f"  파싱 오류 (idx={idx}): {e}")
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
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
            viewport={"width": 1280, "height": 900},
            extra_http_headers={"Accept-Language": "ko-KR,ko;q=0.9"},
        )
        context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )
        page = context.new_page()

        # 메인 페이지 선방문 (쿠키/세션 확보)
        print("  올리브영 메인 페이지 방문 중...")
        try:
            page.goto(
                "https://www.oliveyoung.co.kr/store/main/main.do",
                wait_until="domcontentloaded", timeout=20000,
            )
            time.sleep(2)
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
            json={"secret": SECRET, "dateStr": date_str, "timeStr": time_str, "rows": all_rows},
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
