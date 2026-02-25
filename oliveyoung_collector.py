"""
올리브영 랭킹 수집기 — 셀렉터 진단 버전 2
실제 li 태그 클래스명을 출력해서 올바른 셀렉터 파악
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
]
TOP_N = 100
KST   = timezone(timedelta(hours=9))


def diagnose(page):
    url = "https://www.oliveyoung.co.kr/store/main/getBestList.do?dispCatNo=900000100100001&fltDispCatNo=&pageIdx=0&rowsPerPage=0"
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)

    html = page.content()
    soup = BeautifulSoup(html, "html.parser")

    print(f"\n=== 셀렉터 진단 ===")
    selectors = [
        ".cate_prd_list",
        "li.prd_item",
        "li[class*='prd_item']",
        "li[class*='item']",
        ".tx_brand",
        ".tx_name",
        "[class*='brand']",
        "[class*='name']",
        "ul.product_list",
        "ul[class*='list']",
        "ul[class*='prd']",
        ".prd_info",
        "[class*='prd_info']",
    ]
    for sel in selectors:
        cnt = len(soup.select(sel))
        if cnt > 0:
            print(f"  ✅ [{sel}]: {cnt}개 발견!")
        else:
            print(f"  ❌ [{sel}]: 0개")

    # 실제 ul 태그들의 클래스명 출력
    print(f"\n=== ul 태그 클래스 목록 ===")
    for ul in soup.find_all("ul", limit=20):
        cls = ul.get("class", [])
        if cls:
            print(f"  ul.{'.'.join(cls)}")

    # li 태그 클래스명 상위 20개 출력
    print(f"\n=== li 태그 클래스 목록 (상위 30개) ===")
    seen = set()
    for li in soup.find_all("li", limit=200):
        cls = tuple(li.get("class", []))
        if cls and cls not in seen:
            seen.add(cls)
            print(f"  li.{'.'.join(cls)}")
        if len(seen) >= 30:
            break

    # 상품처럼 보이는 구조 탐색 (브랜드+상품명 텍스트가 있는 li)
    print(f"\n=== 상품 li 후보 탐색 ===")
    for li in soup.find_all("li", limit=500):
        text = li.get_text(strip=True)
        if len(text) > 10 and len(text) < 200:
            cls = ".".join(li.get("class", []))
            # 가격 패턴이 있는 li만
            if "," in text and any(c.isdigit() for c in text):
                print(f"  li.{cls[:60]}: {text[:80]}")
                break


def main():
    now      = datetime.now(KST)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    print(f"[{date_str} {time_str} KST] 셀렉터 진단 시작")

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

        print("  메인 페이지 방문...")
        try:
            page.goto("https://www.oliveyoung.co.kr/store/main/main.do",
                      wait_until="domcontentloaded", timeout=20000)
            time.sleep(2)
        except Exception as e:
            print(f"  메인 페이지 실패: {e}")

        diagnose(page)
        browser.close()

    print("\n진단 완료 — 위 결과를 Claude에게 보내주세요!")


if __name__ == "__main__":
    main()
