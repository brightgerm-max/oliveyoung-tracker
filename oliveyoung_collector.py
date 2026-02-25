"""
올리브영 랭킹 수집기 — HTML 저장 진단 버전
실제 받은 HTML을 파일로 저장해서 구조 확인
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
KST             = timezone(timedelta(hours=9))


def main():
    print("HTML 구조 진단 시작")

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

        # 메인 방문
        page.goto("https://www.oliveyoung.co.kr/store/main/main.do",
                  wait_until="domcontentloaded", timeout=20000)
        time.sleep(2)

        # 랭킹 페이지
        url = "https://www.oliveyoung.co.kr/store/main/getBestList.do?dispCatNo=900000100100001&fltDispCatNo=&pageIdx=0&rowsPerPage=0"
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")

        print(f"HTML 길이: {len(html)}자")
        print(f"페이지 타이틀: {page.title()}")

        # 주요 셀렉터 전수 조사
        print("\n=== 셀렉터 전수 조사 ===")
        candidates = [
            ".cate_prd_list",
            ".prd_info",
            ".prd_list",
            ".product_list",
            ".ranking_list",
            "li.flag",
            "li.prd_item",
            "li[class*='prd']",
            "li[class*='rank']",
            "li[class*='item']",
            "li[class*='product']",
            ".tx_brand",
            ".tx_name",
            ".tx_num",
            "[class*='goodsName']",
            "[class*='brand']",
            "[class*='goods']",
        ]
        for sel in candidates:
            cnt = len(soup.select(sel))
            mark = "✅" if cnt > 0 else "❌"
            print(f"  {mark} {sel}: {cnt}개")

        # prd_info 있으면 첫 번째 내용 출력
        prd_infos = soup.select(".prd_info")
        if prd_infos:
            print(f"\n=== .prd_info 첫 번째 내용 ===")
            print(prd_infos[0].prettify()[:600])
        else:
            print("\n.prd_info 없음 — 다른 구조 탐색")

            # 텍스트에 가격 패턴이 있는 모든 div/ul/li 클래스 출력
            print("\n=== 가격 패턴 포함 태그 (상위 10개) ===")
            count = 0
            for tag in soup.find_all(["li", "div", "ul"], limit=2000):
                text = tag.get_text(strip=True)
                cls  = ".".join(tag.get("class", []))
                if cls and "," in text and any(c.isdigit() for c in text) and len(text) < 300:
                    print(f"  <{tag.name}.{cls[:50]}>: {text[:100]}")
                    count += 1
                    if count >= 10:
                        break

        browser.close()

    print("\n진단 완료!")


if __name__ == "__main__":
    main()
