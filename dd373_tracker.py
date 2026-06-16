"""
冒险岛世界 · 亚服阿尔泰 · 游戏币比例多平台监控系统
平台:
  - DD373: https://www.dd373.com/s-n95vb3-c-r9tnsn-qhgknj-1crcd9.html (人民币)
  - 8591:  https://www.8591.com.tw/v3/mall/list/61990?searchGame=61990&searchServer=64071&searchType=0 (台币→人民币)
汇率: 1 TWD ≈ 0.242 CNY (实时汇率波动，报告中使用此固定参考值)
"""

import json
import time
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).parent / "data"
REPORT_DIR = Path(__file__).parent / "reports"
HISTORY_FILE = DATA_DIR / "dd373_history.json"
TZ = timezone(timedelta(hours=8))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 台币→人民币汇率 (参考值，非实时)
TWD_TO_CNY = 0.242

URL_DD373 = "https://www.dd373.com/s-n95vb3-c-r9tnsn-qhgknj-1crcd9.html"
URL_8591 = "https://www.8591.com.tw/v3/mall/list/61990"
URL_8591_PARAMS = {"searchGame": "61990", "searchServer": "64071", "searchType": "0"}


# ======================== DD373 抓取 ========================

def fetch_dd373():
    """抓取 DD373 冒险岛世界亚服阿尔泰游戏币 (人民币)"""
    try:
        resp = requests.get(URL_DD373, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text()

        listings = []
        pattern = re.findall(
            r'(\d+)万\s*=\s*([\d.]+)元.*?1元=([\d.]+)万.*?1万=([\d.]+)元',
            text, re.DOTALL
        )

        for mesos, price, rate_wpy, rate_ypw in pattern:
            listings.append({
                "mesos_wan": int(mesos),
                "price_cny": float(price),
                "rate_wan_per_yuan": float(rate_wpy),
                "rate_yuan_per_wan": float(rate_ypw),
            })

        if not listings:
            titles = re.findall(r'(\d+)万\s*=\s*([\d.]+)元', text)
            rates_wpy = re.findall(r'1元=([\d.]+)万', text)
            rates_ypw = re.findall(r'1万=([\d.]+)元', text)
            for i, (mesos, price) in enumerate(titles):
                listing = {"mesos_wan": int(mesos), "price_cny": float(price)}
                if i < len(rates_wpy):
                    listing["rate_wan_per_yuan"] = float(rates_wpy[i])
                if i < len(rates_ypw):
                    listing["rate_yuan_per_wan"] = float(rates_ypw[i])
                listings.append(listing)

        if not listings:
            return {"platform": "DD373", "error": "未解析到商品", "timestamp": datetime.now(TZ).isoformat()}

        return _build_result("DD373", "亚服 - 阿尔泰 (Artale)", "CNY", listings, URL_DD373)

    except Exception as e:
        return {"platform": "DD373", "error": str(e), "timestamp": datetime.now(TZ).isoformat()}


# ======================== 8591 抓取 ========================

def parse_8591_html(html_text):
    """从8591 HTML文本中解析枫币商品列表 (纯解析，不请求网络)"""
    listings = []
    soup = BeautifulSoup(html_text, "html.parser")
    cards = soup.select("a[href*='/v3/mall/detail/']")

    for card in cards:
        title = card.get("title", "").strip()
        if not title or "楓幣" not in title:
            continue

        # 解析标题: 【100元=XXX萬楓幣】...
        m1 = re.search(r'【?\s*(\d+)\s*元\s*=\s*(\d+)\s*萬楓幣\s*】?', title)
        if not m1:
            continue

        wan_per_100twd = int(m1.group(2))

        # 找价格
        parent = card.find_parent("tr") or card.find_parent("div")
        price_twd = None
        stock = 0

        if parent and parent.name == "tr":
            tds = parent.find_all("td")
            for td in tds:
                text = td.get_text(strip=True)
                pm = re.search(r'([\d,]+)元', text)
                if pm:
                    price_twd = int(pm.group(1).replace(",", ""))
                    break
            for td in tds:
                text = td.get_text(strip=True)
                sm = re.match(r'^(\d+)$', text)
                if sm and 1 <= int(sm.group(1)) <= 9999:
                    stock = int(sm.group(1))
                    break

        if not price_twd:
            continue
        if wan_per_100twd > 2000:
            continue

        # TWD → CNY
        rate_wan_per_cny = round(wan_per_100twd / 100 / TWD_TO_CNY, 4)
        rate_cny_per_wan = round(1 / rate_wan_per_cny, 4) if rate_wan_per_cny else 0
        price_cny = round(price_twd * TWD_TO_CNY, 2)

        listings.append({
            "mesos_wan": 10000,
            "price_cny": price_cny,
            "price_twd": price_twd,
            "rate_wan_per_yuan": rate_wan_per_cny,
            "rate_yuan_per_wan": rate_cny_per_wan,
            "wan_per_100twd": wan_per_100twd,
            "stock": stock,
            "title": title[:80],
        })

    return listings


def _fetch_8591_playwright():
    """用 Playwright (headless Chromium) 抓取 8591，绕过 Cloudflare 反爬"""
    from playwright.sync_api import sync_playwright
    all_listings = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            locale="zh-TW"
        )
        page = ctx.new_page()

        for pg in range(4):
            params = {**URL_8591_PARAMS, "firstRow": pg * 10}
            url = URL_8591 + "?" + "&".join(f"{k}={v}" for k, v in params.items())
            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
                html = page.content()
                page_listings = parse_8591_html(html)
                all_listings.extend(page_listings)
                if not page_listings:
                    break
            except Exception as e:
                if pg == 0:
                    return {"platform": "8591", "error": f"Playwright抓取失败: {e}",
                            "timestamp": datetime.now(TZ).isoformat()}
                break

        browser.close()

    if not all_listings:
        return {"platform": "8591", "error": "Playwright未解析到枫币商品",
                "timestamp": datetime.now(TZ).isoformat()}

    return _build_result("8591", "繁中服 - Artale (阿尔泰)",
                         f"CNY (1 TWD = {TWD_TO_CNY} CNY)", all_listings, URL_8591)


def fetch_8591():
    """抓取 8591 台湾交易平台枫币 (台币→人民币换算)
    8591 有 Cloudflare 反爬，requests 返回 503。
    优先尝试 Playwright (headless Chromium)，失败则 fallback 到 requests。
    """
    # 优先: Playwright (能绕 Cloudflare)
    try:
        from playwright.sync_api import sync_playwright
        print("    → 使用 Playwright 抓取 8591...")
        return _fetch_8591_playwright()
    except ImportError:
        print("    → Playwright 未安装，fallback 到 requests...")
    except Exception as e:
        print(f"    → Playwright 失败: {e}, fallback 到 requests...")

    # 备用: requests (可能被反爬拦截)
    all_listings = []
    for page in range(4):
        params = {**URL_8591_PARAMS, "firstRow": page * 10}
        try:
            resp = requests.get(URL_8591, headers=HEADERS, params=params, timeout=30)
            resp.raise_for_status()
            page_listings = parse_8591_html(resp.text)
            all_listings.extend(page_listings)
            if not page_listings:
                break
        except Exception as e:
            if page == 0:
                return {"platform": "8591", "error": f"请求失败(8591反爬): {e}",
                        "timestamp": datetime.now(TZ).isoformat(),
                        "note": "需要安装 Playwright: pip install playwright && playwright install chromium"}
            break

    if not all_listings:
        return {"platform": "8591", "error": "未解析到枫币商品", "timestamp": datetime.now(TZ).isoformat()}

    return _build_result("8591", "繁中服 - Artale (阿尔泰)",
                         f"CNY (1 TWD = {TWD_TO_CNY} CNY)", all_listings, URL_8591)


# ======================== 通用工具 ========================

def _build_result(platform, server, currency, listings, url):
    """构建标准化的平台结果"""
    rates = [l.get("rate_wan_per_yuan", 0) for l in listings if l.get("rate_wan_per_yuan")]
    total_mesos = sum(l.get("mesos_wan", 0) for l in listings)

    avg_rate = round(sum(rates) / len(rates), 4) if rates else 0
    best_rate = max(rates) if rates else 0
    worst_rate = min(rates) if rates else 0

    best = next((l for l in listings if l.get("rate_wan_per_yuan") == best_rate), None)
    worst = next((l for l in listings if l.get("rate_wan_per_yuan") == worst_rate), None)

    return {
        "platform": platform,
        "game": "冒险岛世界 (MapleStory Worlds)",
        "server": server,
        "url": url,
        "timestamp": datetime.now(TZ).isoformat(),
        "currency": currency,
        "total_listings": len(listings),
        "avg_rate_wan_per_yuan": avg_rate,
        "best_rate": {
            "rate_wan_per_yuan": best_rate,
            "mesos_wan": best.get("mesos_wan", 0) if best else 0,
            "price_cny": best.get("price_cny", 0) if best else 0
        } if best else None,
        "worst_rate": {
            "rate_wan_per_yuan": worst_rate,
            "mesos_wan": worst.get("mesos_wan", 0) if worst else 0,
            "price_cny": worst.get("price_cny", 0) if worst else 0
        } if worst else None,
        "listings": listings
    }


def load_history():
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return {"records": []}


def save_record(record):
    history = load_history()
    history["records"].append(record)
    cutoff = (datetime.now(TZ) - timedelta(days=90)).isoformat()
    history["records"] = [r for r in history["records"] if r.get("timestamp", "") >= cutoff]
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


# ======================== HTML 报表 ========================

def _make_summary_card(label, value, sub=""):
    return f"""<div class="summary-item">
        <div class="label">{label}</div>
        <div class="value">{value}</div>
        {f'<div class="sub">{sub}</div>' if sub else ''}
    </div>"""


def _make_listing_table(listings, best_rate, worst_rate, is_8591=False):
    listings_sorted = sorted(listings, key=lambda x: x.get("rate_wan_per_yuan", 0), reverse=True)
    rows = ""
    for i, l in enumerate(listings_sorted[:20]):
        rate = l.get("rate_wan_per_yuan", 0)
        badge = ""
        if rate == best_rate:
            badge = '<span style="color:#4caf50;">🥇 最优</span>'
        elif rate == worst_rate:
            badge = '<span style="color:#f44336;">👎 最差</span>'

        if is_8591:
            price_display = f"¥{l['price_cny']} (NT${l.get('price_twd','?')})"
            stock_display = str(l.get('stock', '?'))
        else:
            price_display = f"¥{l['price_cny']}"
            stock_display = "-"

        rows += f"""<tr>
            <td>{i+1}</td>
            <td>{l['mesos_wan']}万</td>
            <td>{price_display}</td>
            <td><b>1元={rate}万</b></td>
            <td>1万=¥{l.get('rate_yuan_per_wan', 'N/A')}</td>
            <td>{stock_display}</td>
            <td>{badge}</td>
        </tr>"""

    cols = ["#", "数量", "价格", "比例", "单价", "库存", "标注"]
    header = "".join(f"<th>{c}</th>" for c in cols)
    return f"""<table><thead><tr>{header}</tr></thead><tbody>{rows}</tbody></table>"""


def generate_html_report():
    history = load_history()
    records = history.get("records", [])
    if not records:
        return None

    now_str = datetime.now(TZ).strftime('%Y-%m-%d %H:%M')

    # 分别提取两个平台的数据
    def get_platform_data(platform_name):
        data = []
        for rec in records:
            for p in rec.get("platforms", []):
                if p.get("platform") == platform_name and "error" not in p:
                    data.append(p)
        return data

    dd_data = get_platform_data("DD373")
    t8_data = get_platform_data("8591")

    # 准备走势数据
    def extract_series(data_list):
        ts, avg, best, worst = [], [], [], []
        for r in data_list[-50:]:
            ts.append(r.get("timestamp", "")[:16])
            avg.append(r.get("avg_rate_wan_per_yuan"))
            br = r.get("best_rate", {})
            wr = r.get("worst_rate", {})
            best.append(br.get("rate_wan_per_yuan") if br else None)
            worst.append(wr.get("rate_wan_per_yuan") if wr else None)
        return ts, avg, best, worst

    dd_ts, dd_avg, dd_best, dd_worst = extract_series(dd_data)
    t8_ts, t8_avg, t8_best, t8_worst = extract_series(t8_data)

    # DD373 摘要
    dd_html = ""
    if dd_data:
        dd_latest = dd_data[-1]
        dd_avg_val = dd_latest.get("avg_rate_wan_per_yuan", 0)
        dd_best_r = dd_latest.get("best_rate", {})
        dd_worst_r = dd_latest.get("worst_rate", {})
        dd_spread_pct = (dd_best_r.get("rate_wan_per_yuan", 1) / dd_worst_r.get("rate_wan_per_yuan", 1) - 1) * 100 if dd_worst_r.get("rate_wan_per_yuan") else 0

        dd_html = f"""
        <div class="card">
            <h3>🇨🇳 DD373 (人民币)</h3>
            <div class="summary-bar" style="justify-content:flex-start;">
                {_make_summary_card("📦 商品数", dd_latest.get('total_listings', 0))}
                {_make_summary_card("💰 均价", f"1元 = {dd_avg_val}万", f"1亿 ≈ ¥{round(10000/dd_avg_val,2) if dd_avg_val else 0}")}
                {_make_summary_card("🥇 最优", f"1元 = {dd_best_r.get('rate_wan_per_yuan',0)}万")}
                {_make_summary_card("📊 价差", f"{dd_spread_pct:.1f}%")}
            </div>
            <h4 style="color:#888;margin:15px 0 10px;">商品列表</h4>
            {_make_listing_table(dd_latest.get('listings',[]), dd_best_r.get('rate_wan_per_yuan',0), dd_worst_r.get('rate_wan_per_yuan',0))}
        </div>"""

    # 8591 摘要
    t8_html = ""
    if t8_data:
        t8_latest = t8_data[-1]
        t8_avg_val = t8_latest.get("avg_rate_wan_per_yuan", 0)
        t8_best_r = t8_latest.get("best_rate", {})
        t8_worst_r = t8_latest.get("worst_rate", {})
        t8_spread_pct = (t8_best_r.get("rate_wan_per_yuan", 1) / t8_worst_r.get("rate_wan_per_yuan", 1) - 1) * 100 if t8_worst_r.get("rate_wan_per_yuan") else 0

        t8_html = f"""
        <div class="card">
            <h3>🇹🇼 8591 (台币→人民币, 1TWD={TWD_TO_CNY}CNY)</h3>
            <div class="summary-bar" style="justify-content:flex-start;">
                {_make_summary_card("📦 商品数", t8_latest.get('total_listings', 0))}
                {_make_summary_card("💰 均价", f"1元 = {t8_avg_val}万", f"1亿 ≈ ¥{round(10000/t8_avg_val,2) if t8_avg_val else 0}")}
                {_make_summary_card("🥇 最优", f"1元 = {t8_best_r.get('rate_wan_per_yuan',0)}万")}
                {_make_summary_card("📊 价差", f"{t8_spread_pct:.1f}%", "⚠️ 大" if t8_spread_pct > 30 else "")}
            </div>
            <h4 style="color:#888;margin:15px 0 10px;">商品列表</h4>
            {_make_listing_table(t8_latest.get('listings',[]), t8_best_r.get('rate_wan_per_yuan',0), t8_worst_r.get('rate_wan_per_yuan',0), is_8591=True)}
        </div>"""

    # 双平台对比走势图
    chart_datasets = []
    if dd_ts:
        chart_datasets.append(f"""{{
            label: 'DD373 均价',
            data: {json.dumps([x for x in dd_avg[-30:] if x])},
            borderColor: '#ff6b35',
            backgroundColor: '#ff6b3533',
            tension: 0.3, fill: false, pointRadius: 2, borderWidth: 2,
        }}""")
        chart_datasets.append(f"""{{
            label: 'DD373 最优',
            data: {json.dumps([x for x in dd_best[-30:] if x])},
            borderColor: '#4caf50',
            backgroundColor: '#4caf5033',
            tension: 0.3, fill: false, pointRadius: 1, borderDash: [5,5],
        }}""")
    if t8_ts:
        chart_datasets.append(f"""{{
            label: '8591 均价 (CNY)',
            data: {json.dumps([x for x in t8_avg[-30:] if x])},
            borderColor: '#2196f3',
            backgroundColor: '#2196f333',
            tension: 0.3, fill: false, pointRadius: 2, borderWidth: 2,
        }}""")
        chart_datasets.append(f"""{{
            label: '8591 最优 (CNY)',
            data: {json.dumps([x for x in t8_best[-30:] if x])},
            borderColor: '#00bcd4',
            backgroundColor: '#00bcd433',
            tension: 0.3, fill: false, pointRadius: 1, borderDash: [5,5],
        }}""")

    # 使用 DD373 时间轴为主
    chart_labels = json.dumps(dd_ts[-30:] if dd_ts else [])

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>冒险岛世界 · 游戏币多平台监控</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f1923; color: #e0e0e0; padding: 20px; }}
.header {{ text-align: center; margin-bottom: 25px; }}
.header h1 {{ color: #ff6b35; font-size: 2em; }}
.header .subtitle {{ color: #888; font-size: 0.9em; margin-top: 5px; }}
.summary-bar {{ display: flex; justify-content: center; flex-wrap: wrap; gap: 12px; margin-bottom: 15px; }}
.summary-item {{ background: #1a2733; border-radius: 10px; padding: 12px 20px; text-align: center; border: 1px solid #2a3a4a; min-width: 110px; }}
.summary-item .label {{ color: #888; font-size: 0.75em; }}
.summary-item .value {{ font-size: 1.3em; font-weight: bold; color: #ff6b35; }}
.summary-item .sub {{ font-size: 0.75em; color: #666; }}
.dashboard {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; max-width: 1600px; margin: 0 auto; }}
@media (max-width: 1000px) {{ .dashboard {{ grid-template-columns: 1fr; }} }}
.card {{ background: #1a2733; border-radius: 12px; padding: 20px; border: 1px solid #2a3a4a; }}
.card.full {{ grid-column: 1 / -1; }}
.card h3 {{ color: #ff6b35; margin-bottom: 12px; font-size: 1.1em; }}
.card h4 {{ font-size: 0.9em; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.85em; }}
th {{ text-align: left; padding: 6px 8px; border-bottom: 2px solid #2a3a4a; color: #888; font-weight: normal; font-size: 0.8em; }}
td {{ padding: 6px 8px; border-bottom: 1px solid #1e2a35; }}
tr:hover td {{ background: #1e2a35; }}
canvas {{ max-height: 350px; }}
.footer {{ text-align: center; color: #555; margin-top: 30px; font-size: 0.8em; }}
.alert {{ background: #ff6b3522; border: 1px solid #ff6b35; border-radius: 8px; padding: 10px 15px; margin-bottom: 15px; font-size: 0.9em; }}
</style>
</head>
<body>
<div class="header">
    <h1>🎮 冒险岛世界 · 游戏币多平台监控</h1>
    <p class="subtitle">DD373 (人民币) + 8591 (台币→人民币) · {now_str} 北京时间</p>
</div>

<div class="dashboard">
    {dd_html}
    {t8_html}

    <div class="card full">
        <h3>📈 双平台比例走势对比 (1元 = ?万枫币 · 越高越划算)</h3>
        <canvas id="rateChart"></canvas>
    </div>
</div>

<div class="footer">
    <p>📊 数据来源: DD373 (dd373.com) · 8591 (8591.com.tw) · 冒险岛世界 亚服 阿尔泰</p>
    <p>💱 8591台币→人民币参考汇率: 1 TWD = {TWD_TO_CNY} CNY · ⚡ 历史数据保留90天</p>
</div>

<script>
new Chart(document.getElementById('rateChart').getContext('2d'), {{
    type: 'line',
    data: {{
        labels: {chart_labels},
        datasets: [{', '.join(chart_datasets)}]
    }},
    options: {{
        responsive: true,
        maintainAspectRatio: true,
        interaction: {{ intersect: false, mode: 'index' }},
        plugins: {{ legend: {{ labels: {{ color: '#aaa', usePointStyle: true, padding: 15, font: {{size:11}} }} }} }},
        scales: {{
            x: {{ ticks: {{ color: '#666', maxTicksLimit: 12, font: {{size:10}} }} }},
            y: {{ ticks: {{ color: '#666', callback: v => v + '万' }} }}
        }}
    }}
}});
</script>
</body>
</html>"""

    report_path = REPORT_DIR / "dd373_report.html"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)

    return report_path


# ======================== 主流程 ========================

def run_once():
    ts = datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{ts}] 抓取冒险岛世界金价...")
    print("─" * 50)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    platforms = []

    # DD373
    print("  [DD373] 抓取中...")
    dd = fetch_dd373()
    platforms.append(dd)
    if "error" in dd:
        print(f"    ❌ {dd['error']}")
    else:
        br = dd.get("best_rate", {})
        wr = dd.get("worst_rate", {})
        sp = (br.get("rate_wan_per_yuan", 1) / wr.get("rate_wan_per_yuan", 1) - 1) * 100 if wr.get("rate_wan_per_yuan") else 0
        print(f"    ✅ {dd['total_listings']}商品 | 均价 1元={dd['avg_rate_wan_per_yuan']}万 | 最优 {br.get('rate_wan_per_yuan')}万 | 价差 {sp:.1f}%")

    # 8591
    print("  [8591] 抓取中...")
    t8 = fetch_8591()
    platforms.append(t8)
    if "error" in t8:
        print(f"    ❌ {t8['error']}")
    else:
        br = t8.get("best_rate", {})
        wr = t8.get("worst_rate", {})
        sp = (br.get("rate_wan_per_yuan", 1) / wr.get("rate_wan_per_yuan", 1) - 1) * 100 if wr.get("rate_wan_per_yuan") else 0
        flag = " ⚠️ 套利!" if sp > 30 else ""
        print(f"    ✅ {t8['total_listings']}商品 | 均价 1元={t8['avg_rate_wan_per_yuan']}万(CNY) | 最优 {br.get('rate_wan_per_yuan')}万 | 价差 {sp:.1f}%{flag}")

    # 保存
    record = {
        "timestamp": datetime.now(TZ).isoformat(),
        "platforms": platforms
    }
    save_record(record)

    # 报表
    print("  → 生成报表...")
    report = generate_html_report()
    if report:
        print(f"  📊 {report}")

    print("─" * 50)

    # 简要摘要
    summary_parts = []
    for p in platforms:
        if "error" not in p:
            summary_parts.append(f"{p['platform']}: 1元={p['avg_rate_wan_per_yuan']}万 ({p['total_listings']}个)")
    print(f"📋 {' | '.join(summary_parts)}")

    return record


if __name__ == "__main__":
    run_once()
