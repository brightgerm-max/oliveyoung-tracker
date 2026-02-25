// ============================================================
// 올리브영 랭킹 트래커 — GAS Web App (수신 서버)
// 
// [설치 순서]
// 1. 이 코드를 Apps Script에 붙여넣기 후 저장
// 2. setup() 실행 → 시트 생성
// 3. 배포: 배포 > 새 배포 > 웹 앱
//    - 실행 계정: 나
//    - 액세스: 모든 사용자 (익명 포함)
// 4. 배포 URL을 복사 → Python 스크립트의 GAS_WEB_APP_URL에 붙여넣기
// ============================================================

const CONFIG = {
  CATEGORIES: ["전체TOP100", "스킨케어"],
  KEEP_DAYS:  30,
  SHEET_RAW:   "📊 원본데이터",
  SHEET_BRAND: "📦 브랜드집계",
  SHEET_LIVE:  "🔴 실시간현황",
};

// ─────────────────────────────────────────
// Web App 수신 엔드포인트 (Python → GAS)
// ─────────────────────────────────────────
function doPost(e) {
  try {
    const payload = JSON.parse(e.postData.contents);

    // 간단한 인증 토큰 확인 (Python 스크립트와 동일하게 설정)
    const SECRET = "oliveyoung_secret_2026"; // ★ 원하는 값으로 변경
    if (payload.secret !== SECRET) {
      return jsonResponse_({ ok: false, error: "Unauthorized" }, 401);
    }

    const ss      = SpreadsheetApp.getActiveSpreadsheet();
    const rows    = payload.rows;       // [{dateStr, timeStr, category, rank, ...}, ...]
    const dateStr = payload.dateStr;

    if (!rows || rows.length === 0) {
      return jsonResponse_({ ok: false, error: "No data" });
    }

    appendRawData_(ss, rows);
    refreshLiveSheet_(ss, rows, dateStr, payload.timeStr);
    refreshBrandSheet_(ss, dateStr);
    pruneOldData_(ss);

    return jsonResponse_({ ok: true, saved: rows.length });

  } catch (err) {
    Logger.log("doPost 오류: " + err.message);
    return jsonResponse_({ ok: false, error: err.message });
  }
}

// GET 요청 — 상태 확인용
function doGet(e) {
  const ss     = SpreadsheetApp.getActiveSpreadsheet();
  const rawSh  = ss.getSheetByName(CONFIG.SHEET_RAW);
  const count  = rawSh ? Math.max(0, rawSh.getLastRow() - 1) : 0;
  return jsonResponse_({ ok: true, status: "running", totalRows: count });
}

function jsonResponse_(obj, code) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

// ─────────────────────────────────────────
// 초기 설정
// ─────────────────────────────────────────
function setup() {
  initSheets_();
  SpreadsheetApp.getUi().alert(
    "✅ 시트 생성 완료!\n\n" +
    "다음 단계:\n" +
    "1. 배포 > 새 배포 > 웹 앱\n" +
    "2. 실행 계정: 나 / 액세스: 모든 사용자\n" +
    "3. 배포 URL을 Python 스크립트에 붙여넣기"
  );
}

// ─────────────────────────────────────────
// 원본 데이터 저장
// ─────────────────────────────────────────
const RAW_HEADERS = [
  "날짜","시각","카테고리","순위","브랜드","상품명",
  "현재가","정가","할인율(%)","세일","쿠폰","증정","오늘드림"
];

function appendRawData_(ss, rows) {
  const sh = ss.getSheetByName(CONFIG.SHEET_RAW);
  if (sh.getLastRow() === 0) {
    sh.appendRow(RAW_HEADERS);
    sh.getRange(1, 1, 1, RAW_HEADERS.length)
      .setBackground("#34A853").setFontColor("white").setFontWeight("bold");
    sh.setFrozenRows(1);
  }
  const data = rows.map(r => [
    r.dateStr, r.timeStr, r.category, r.rank, r.brand, r.name,
    r.curPrice || "", r.orgPrice || "", r.discount || "",
    r.hasSale || "", r.hasCoupon || "", r.hasGift || "", r.hasDelivery || ""
  ]);
  sh.getRange(sh.getLastRow() + 1, 1, data.length, RAW_HEADERS.length).setValues(data);
}

// ─────────────────────────────────────────
// 실시간 현황 시트
// ─────────────────────────────────────────
function refreshLiveSheet_(ss, rows, dateStr, timeStr) {
  const sh = ss.getSheetByName(CONFIG.SHEET_LIVE);
  sh.clearContents(); sh.clearFormats();
  let r = 1;

  sh.getRange(r, 1).setValue("🔴 올리브영 실시간 랭킹");
  sh.getRange(r, 1, 1, 9).merge()
    .setBackground("#D93025").setFontColor("white")
    .setFontWeight("bold").setFontSize(14).setHorizontalAlignment("center");
  r++;
  sh.getRange(r, 1).setValue(`수집 시각: ${dateStr} ${timeStr} KST`);
  sh.getRange(r, 1, 1, 9).merge()
    .setFontColor("#555").setHorizontalAlignment("center").setFontSize(10);
  r += 2;

  const cats = [...new Set(rows.map(x => x.category))];
  for (const cat of cats) {
    const catRows = rows.filter(x => x.category === cat);
    if (!catRows.length) continue;

    sh.getRange(r, 1).setValue(`▶ ${cat}  (${catRows.length}개)`);
    sh.getRange(r, 1, 1, 9).merge()
      .setBackground("#1A73E8").setFontColor("white").setFontWeight("bold").setFontSize(12);
    r++;

    sh.getRange(r, 1, 1, 9).setValues([["순위","브랜드","상품명","현재가","할인율","세일","쿠폰","증정","오늘드림"]])
      .setBackground("#E8F0FE").setFontWeight("bold");
    r++;

    catRows.forEach(item => {
      sh.getRange(r, 1, 1, 9).setValues([[
        item.rank, item.brand, item.name,
        item.curPrice ? `₩${Number(item.curPrice).toLocaleString()}` : "-",
        item.discount ? `${item.discount}%` : "-",
        item.hasSale     === "Y" ? "✅" : "",
        item.hasCoupon   === "Y" ? "✅" : "",
        item.hasGift     === "Y" ? "✅" : "",
        item.hasDelivery === "Y" ? "✅" : "",
      ]]);
      if      (item.rank === 1) sh.getRange(r, 1, 1, 9).setBackground("#FFF9C4");
      else if (item.rank === 2) sh.getRange(r, 1, 1, 9).setBackground("#F5F5F5");
      else if (item.rank === 3) sh.getRange(r, 1, 1, 9).setBackground("#FFF3E0");
      r++;
    });
    r += 2;
  }
  sh.autoResizeColumns(1, 9);
}

// ─────────────────────────────────────────
// 브랜드 집계 시트
// ─────────────────────────────────────────
function refreshBrandSheet_(ss, targetDate) {
  const rawSh   = ss.getSheetByName(CONFIG.SHEET_RAW);
  const brandSh = ss.getSheetByName(CONFIG.SHEET_BRAND);
  brandSh.clearContents(); brandSh.clearFormats();

  const allData   = rawSh.getDataRange().getValues();
  if (allData.length < 2) return;

  const I = { date:0,time:1,cat:2,rank:3,brand:4,name:5,
              cur:6,org:7,disc:8,sale:9,coupon:10,gift:11,delivery:12 };
  const todayRows = allData.slice(1).filter(r => r[I.date] === targetDate);
  if (!todayRows.length) return;

  let r = 1;

  // 섹션 1: 카테고리별 브랜드 집계
  for (const catName of CONFIG.CATEGORIES) {
    const catRows = todayRows.filter(row => row[I.cat] === catName);
    if (!catRows.length) continue;

    const brandMap = {};
    catRows.forEach(row => {
      const b = row[I.brand] || "미상";
      if (!brandMap[b]) brandMap[b] = { count:0,rankSum:0,topRank:999,
                                         saleCount:0,couponCount:0,priceSum:0,priceCount:0 };
      const d = brandMap[b];
      d.count++;
      d.rankSum  += Number(row[I.rank]);
      d.topRank   = Math.min(d.topRank, Number(row[I.rank]));
      if (row[I.sale]   === "Y") d.saleCount++;
      if (row[I.coupon] === "Y") d.couponCount++;
      if (row[I.cur] > 0) { d.priceSum += Number(row[I.cur]); d.priceCount++; }
    });

    const timeSlots = [...new Set(catRows.map(row => row[I.time]))];

    brandSh.getRange(r, 1).setValue(`📦 ${catName} — 브랜드별 집계 (${targetDate})`);
    brandSh.getRange(r, 1, 1, 8).merge()
      .setBackground("#1A73E8").setFontColor("white")
      .setFontWeight("bold").setFontSize(13).setHorizontalAlignment("center");
    r++;
    brandSh.getRange(r, 1).setValue(`오늘 수집 ${timeSlots.length}회 / 총 ${catRows.length}건`);
    brandSh.getRange(r, 1, 1, 8).merge()
      .setFontColor("#555").setFontSize(10).setHorizontalAlignment("center");
    r++;

    const hdrs = ["브랜드","등장 횟수","평균 순위","최고 순위","랭킹 점수","세일 횟수","쿠폰 횟수","평균 가격(원)"];
    brandSh.getRange(r, 1, 1, 8).setValues([hdrs])
      .setBackground("#E8F0FE").setFontWeight("bold").setHorizontalAlignment("center");
    r++;

    const sorted = Object.entries(brandMap).map(([name, v]) => ({
      name, count: v.count,
      avgRank:  Math.round(v.rankSum / v.count * 10) / 10,
      topRank:  v.topRank,
      score:    Math.round(v.count * 1000 / (v.rankSum / v.count)),
      saleCount: v.saleCount, couponCount: v.couponCount,
      avgPrice: v.priceCount > 0 ? Math.round(v.priceSum / v.priceCount) : 0,
    })).sort((a, b) => b.count !== a.count ? b.count - a.count : a.avgRank - b.avgRank);

    sorted.forEach((b, i) => {
      brandSh.getRange(r, 1, 1, 8).setValues([[
        b.name, b.count, b.avgRank, `${b.topRank}위`, b.score,
        b.saleCount || "", b.couponCount || "",
        b.avgPrice > 0 ? b.avgPrice : "-",
      ]]);
      if (i < 5) {
        const colors = ["#FFF176","#F5F5F5","#FFE0B2","#E8F5E9","#E3F2FD"];
        brandSh.getRange(r, 1, 1, 8).setBackground(colors[i]);
      }
      r++;
    });
    r += 3;
  }

  // 섹션 2: 시간대별 TOP10 브랜드 추이
  const allTimes = [...new Set(todayRows.map(row => row[I.time]))].sort();
  const totalBrandCount = {};
  todayRows.forEach(row => {
    const b = row[I.brand] || "미상";
    totalBrandCount[b] = (totalBrandCount[b] || 0) + 1;
  });
  const top10 = Object.entries(totalBrandCount)
    .sort((a,b) => b[1]-a[1]).slice(0,10).map(e => e[0]);

  brandSh.getRange(r, 1).setValue("⏱ 시간대별 TOP10 브랜드 추이");
  brandSh.getRange(r, 1, 1, allTimes.length + 1).merge()
    .setBackground("#FF6D00").setFontColor("white")
    .setFontWeight("bold").setFontSize(13).setHorizontalAlignment("center");
  r++;

  brandSh.getRange(r, 1).setValue("브랜드 \\ 수집시각");
  allTimes.forEach((t, i) => brandSh.getRange(r, i + 2).setValue(t));
  brandSh.getRange(r, 1, 1, allTimes.length + 1)
    .setBackground("#FFF3E0").setFontWeight("bold").setHorizontalAlignment("center");
  r++;

  top10.forEach(brand => {
    brandSh.getRange(r, 1).setValue(brand).setFontWeight("bold");
    allTimes.forEach((t, i) => {
      const hit = todayRows.find(row => row[I.time] === t && row[I.brand] === brand);
      brandSh.getRange(r, i + 2).setValue(hit ? `${hit[I.rank]}위` : "");
    });
    r++;
  });

  brandSh.setColumnWidth(1, 160);
  brandSh.setColumnWidth(3, 250);
  brandSh.autoResizeColumns(2, 8);
}

// ─────────────────────────────────────────
// 오래된 데이터 삭제
// ─────────────────────────────────────────
function pruneOldData_(ss) {
  const sh     = ss.getSheetByName(CONFIG.SHEET_RAW);
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - CONFIG.KEEP_DAYS);
  const cutStr = Utilities.formatDate(cutoff, "Asia/Seoul", "yyyy-MM-dd");
  const data   = sh.getDataRange().getValues();
  let del = 0;
  for (let i = data.length - 1; i >= 1; i--) {
    if (data[i][0] && data[i][0] < cutStr) { sh.deleteRow(i + 1); del++; }
  }
  if (del > 0) Logger.log(`🗑 ${del}행 삭제`);
}

// ─────────────────────────────────────────
// 헬퍼
// ─────────────────────────────────────────
function initSheets_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  [CONFIG.SHEET_RAW, CONFIG.SHEET_LIVE, CONFIG.SHEET_BRAND].forEach(n => {
    if (!ss.getSheetByName(n)) ss.insertSheet(n);
  });
  ["Sheet1","시트1"].forEach(n => {
    const sh = ss.getSheetByName(n);
    if (sh && ss.getSheets().length > 3) try { ss.deleteSheet(sh); } catch(_) {}
  });
}

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("🌿 올리브영")
    .addItem("📦 브랜드 집계 새로고침", "refreshBrandSheetManual")
    .addSeparator()
    .addItem("⚙️ 초기 설정 (최초 1회)", "setup")
    .addToUi();
}

function refreshBrandSheetManual() {
  const ss    = SpreadsheetApp.getActiveSpreadsheet();
  const rawSh = ss.getSheetByName(CONFIG.SHEET_RAW);
  const data  = rawSh.getDataRange().getValues();
  const dates = data.slice(1).map(r => r[0]).filter(Boolean);
  if (!dates.length) { SpreadsheetApp.getUi().alert("수집된 데이터가 없습니다."); return; }
  const latest = dates.reduce((a, b) => a > b ? a : b);
  refreshBrandSheet_(ss, latest);
  SpreadsheetApp.getUi().alert(`✅ ${latest} 기준 브랜드 집계 완료`);
}
