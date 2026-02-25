"""
올리브영 랭킹 수집기 — 스킨케어 진단 버전
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

VIEWER_PRODUCTS = [
    {
        "name": "[화잘먹] 구달 맑은 어성초 진정 수분 선크림 50ml 1+1 기획 (+25ml 미니어처)",
        "url":  "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000219553",
    },
    {
        "name": "[규진마켓/진정커버] 구달 어성초 진정 블레미쉬 커버 선비비 뉴트럴 베이지 50ml 기획 (+25ml)",
        "url":  "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000248065",
    },
]

TOP_N = 100


def fetch_viewer_count(product: dict, context) -> dict:
    page = context.new_page()
    try:
        page.goto(product["url"], wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_selector("[class*='viewer-count'] em, [class*='viewerCount'] em", timeout=10000)
        except Exception:
            time.sleep(3)
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        name_el = (
            soup.select_one("[data-qa-name='text-product-title']") or
            soup.select_one("[class*='title-area'] p") or
            soup.select_one("[class*='GoodsDetail'] h2")
        )
        product_name = name_el.get_text(strip=True) if name_el else product["name"]
        viewer_el = (
            soup.select_one("[class*='viewer-count'] em") or
            soup.select_one("[class*='viewerCount'] em") or
            soup.select_one("[class*='viewer_count'] em")
        )
        viewer_count = int(viewer_el.get_text(strip=True).replace(",", "")) if viewer_el else 0
        print(f"  [{product['name'][:20]}...] 뷰어: {viewer_count}명")
        return {"productName": product_name, "url": product["url"], "viewerCount": viewer_count}
    except Exception as e:
        print(f"  뷰어 수집 실패: {e}")
        return {"productName": product["name"], "url": product["url"], "viewerCount": 0}
    finally:
        page.close()


def parse_ranking_html(html: str) -> list:
    soup      = BeautifulSoup(html, "html.parser")
    prd_infos = soup.select(".prd_info")
    print(f"  .prd_info {len(prd_infos)}개 발견")
    items = []
    for info in prd_infos[:TOP_N]:
        try:
            rank_el   = info.select_one(".thumb_flag")
            rank      = int(rank_el.get_text(strip=True)) if rank_el else len(items) + 1
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
            scope = str(info)
            items.append({
                "rank": rank, "brand": brand, "name": name,
                "curPrice": cur_price, "orgPrice": org_price, "discount": discount,
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

    all_rows    = []
    viewer_rows = []

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

        # 메인 페이지 선방문
        warmup = context.new_page()
        try:
            warmup.goto("https://www.oliveyoung.co.kr/store/main/main.do",
                        wait_until="domcontentloaded", timeout=20000)
            time.sleep(1)
        except Exception as e:
            print(f"  메인 방문 실패: {e}")
        finally:
            warmup.close()

        # 전체TOP100 수집
        print("  [전체TOP100] 수집 중...")
        page1 = context.new_page()
        try:
            page1.goto(
                "https://www.oliveyoung.co.kr/store/main/getBestList.do?dispCatNo=900000100100001&fltDispCatNo=&pageIdx=0&rowsPerPage=0",
                wait_until="domcontentloaded", timeout=30000
            )
            page1.wait_for_selector(".prd_info", timeout=15000)
            items = parse_ranking_html(page1.content())
            print(f"  [전체TOP100] ✅ {len(items)}건")
            for item in items:
                all_rows.append({"dateStr": date_str, "timeStr": time_str, "category": "전체TOP100", **item})
        except Exception as e:
            print(f"  [전체TOP100] 실패: {e}")
        finally:
            page1.close()

        time.sleep(3)

        # 스킨케어: 전체TOP100 먼저 방문 후 카테고리 클릭 방식으로 우회
        print("  [스킨케어] 수집 중... (랭킹 페이지 → 카테고리 필터 방식)")
        page2 = context.new_page()
        try:
            # 1. 전체 랭킹 페이지 먼저 로드
            page2.goto(
                "https://www.oliveyoung.co.kr/store/main/getBestList.do?dispCatNo=900000100100001&fltDispCatNo=&pageIdx=0&rowsPerPage=0",
                wait_until="domcontentloaded", timeout=30000
            )
            page2.wait_for_selector(".prd_info", timeout=15000)
            print("  전체 랭킹 로드 완료, 스킨케어 URL로 이동...")
            time.sleep(2)

            # 2. 스킨케어 URL로 이동
            page2.goto(
                "https://www.oliveyoung.co.kr/store/main/getBestList.do?dispCatNo=900000100100002&fltDispCatNo=&pageIdx=0&rowsPerPage=0",
                wait_until="domcontentloaded", timeout=30000
            )

            # 3. .prd_info 대기
            try:
                page2.wait_for_selector(".prd_info", timeout=15000)
            except Exception:
                print("  대기 초과 — 5초 더 기다린 후 파싱")
                time.sleep(5)

            html = page2.content()
            soup = BeautifulSoup(html, "html.parser")

            # 진단 출력
            print(f"  페이지 타이틀: {page2.title()}")
            print(f"  HTML 길이: {len(html)}자")
            for sel in [".prd_info", ".cate_prd_list", ".tx_brand"]:
                print(f"  셀렉터 [{sel}]: {len(soup.select(sel))}개")

            items = parse_ranking_html(html)
            print(f"  [스킨케어] ✅ {len(items)}건")
            for item in items:
                all_rows.append({"dateStr": date_str, "timeStr": time_str, "category": "스킨케어", **item})
        except Exception as e:
            print(f"  [스킨케어] 실패: {e}")
        finally:
            page2.close()

        # 뷰어 수 수집
        print("\n  뷰어 수 수집 시작...")
        for product in VIEWER_PRODUCTS:
            result = fetch_viewer_count(product, context)
            viewer_rows.append({
                "dateStr": date_str, "timeStr": time_str,
                "productName": result["productName"],
                "url": result["url"],
                "viewerCount": result["viewerCount"],
            })
            time.sleep(2)

        browser.close()

    if not all_rows and not viewer_rows:
        print("❌ 수집된 데이터 없음")
        sys.exit(1)

    print(f"\n  GAS 전송 중... (랭킹 {len(all_rows)}건 + 뷰어 {len(viewer_rows)}건)")
    try:
        resp = requests.post(
            GAS_WEB_APP_URL,
            json={"secret": SECRET, "dateStr": date_str, "timeStr": time_str,
                  "rows": all_rows, "viewerRows": viewer_rows},
            timeout=60,
        )
        result = resp.json()
        if result.get("ok"):
            print(f"  ✅ 저장 완료: 랭킹 {result.get('saved')}건 / 뷰어 {result.get('viewerSaved')}건")
        else:
            print(f"  ❌ GAS 오류: {result.get('error')}")
            sys.exit(1)
    except Exception as e:
        print(f"  ❌ 전송 실패: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
