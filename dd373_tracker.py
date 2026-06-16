"""
冒险岛世界 · 亚服阿尔泰 · 游戏币比例监控 (DD373)
数据来源: https://www.dd373.com/s-n95vb3-c-r9tnsn-qhgknj-1crcd9.html
"""

import json
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

URL = "https://www.dd373.com/s-n95vb3-c-r9tnsn-qhgknj-1crcd9.html"


def fetch_dd373():
    """抓取 DD373 冒险岛世界亚服阿尔泰游戏币"""
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=30)
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

        rates = [l.get("rate_wan_per_yuan", 0) for l in listings if l.get("rate_wan_per_yuan")]
        avg_rate = round(sum(rates) / len(rates), 4) if rates else 0
        best_rate = max(rates) if rates else 0
        worst_rate = min(rates) if rates else 0
        best = next((l for l in listings if l.get("rate_wan_per_yuan") == best_rate), None)
        worst = next((l for l in listings if l.get("rate_wan_per_yuan") == worst_rate), None)

        return {
            "platform": "DD373",
            "game": "冒险岛世界 (MapleStory Worlds)",
            "server": "亚服 - 阿尔泰 (Artale)",
            "url": URL,
            "timestamp": datetime.now(TZ).isoformat(),
            "currency": "CNY",
            "total_listings": len(listings),
            "avg_rate_wan_per_yuan": avg_rate,
            "best_rate": {
                "rate_wan_per_yuan": best_rate,
                "mesos_wan": best["mesos_wan"] if best else 0,
                "price_cny": best["price_cny"] if best else 0
            } if best else None,
            "worst_rate": {
                "rate_wan_per_yuan": worst_rate,
                "mesos_wan": worst["mesos_wan"] if worst else 0,
                "price_cny": worst["price_cny"] if worst else 0
            } if worst else None,
            "listings": listings
        }

    except Exception as e:
        return {"platform": "DD373", "error": str(e), "timestamp": datetime.now(TZ).isoformat()}


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


def generate_html_report():
    history = load_history()
    records = history.get("records", [])
    if not records:
        return None

    now_str = datetime.now(TZ).strftime('%Y-%m-%d %H:%M')

    # 提取 DD373 数据
    dd_records = []
    for rec in records:
        for p in rec.get("platforms", []):
            if p.get("platform") == "DD373" and "error" not in p:
                dd_records.append(p)

    if not dd_records:
        return None

    latest = dd_records[-1]

    # 走势数据
    timestamps, avg_rates, best_rates, worst_rates = [], [], [], []
    for r in dd_records[-50:]:
        timestamps.append(r.get("timestamp", "")[:16])
        avg_rates.append(r.get("avg_rate_wan_per_yuan"))
        br = r.get("best_rate", {})
        wr = r.get("worst_rate", {})
        best_rates.append(br.get("rate_wan_per_yuan") if br else None)
        worst_rates.append(wr.get("rate_wan_per_yuan") if wr else None)

    # 商品列表 (按比例排序)
    listings = sorted(latest.get("listings", []), key=lambda x: x.get("rate_wan_per_yuan", 0), reverse=True)
    listing_rows = ""
    for i, l in enumerate(listings[:20]):
        rate = l.get("rate_wan_per_yuan", 0)
        badge = ""
        if rate == latest.get("best_rate", {}).get("rate_wan_per_yuan"):
            badge = '<span style="color:#4caf50;">🥇 最优</span>'
        elif rate == latest.get("worst_rate", {}).get("rate_wan_per_yuan"):
            badge = '<span style="color:#f44336;">👎 最差</span>'
        listing_rows += f"""<tr>
            <td>{i+1}</td>
            <td>{l['mesos_wan']}万</td>
            <td>¥{l['price_cny']}</td>
            <td><b>1元={rate}万</b></td>
            <td>1万=¥{l.get('rate_yuan_per_wan', 'N/A')}</td>
            <td>{badge}</td>
        </tr>"""

    # 摘要
    avg = latest.get("avg_rate_wan_per_yuan", 0)
    best = latest.get("best_rate", {})
    worst = latest.get("worst_rate", {})
    spread_pct = (best.get("rate_wan_per_yuan", 1) / worst.get("rate_wan_per_yuan", 1) - 1) * 100 if worst.get("rate_wan_per_yuan") else 0
    yi_per_yuan = round(10000 / avg, 2) if avg else 0

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>冒险岛世界 · DD373金价监控</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f1923; color: #e0e0e0; padding: 20px; }}
.header {{ text-align: center; margin-bottom: 25px; }}
.header h1 {{ color: #ff6b35; font-size: 2em; }}
.header .subtitle {{ color: #888; font-size: 0.9em; margin-top: 5px; }}
.summary-bar {{ display: flex; justify-content: center; flex-wrap: wrap; gap: 15px; margin-bottom: 25px; }}
.summary-item {{ background: #1a2733; border-radius: 10px; padding: 15px 25px; text-align: center; border: 1px solid #2a3a4a; min-width: 130px; }}
.summary-item .label {{ color: #888; font-size: 0.8em; }}
.summary-item .value {{ font-size: 1.5em; font-weight: bold; color: #ff6b35; }}
.summary-item .sub {{ font-size: 0.8em; color: #666; }}
.dashboard {{ max-width: 900px; margin: 0 auto; }}
.card {{ background: #1a2733; border-radius: 12px; padding: 20px; border: 1px solid #2a3a4a; margin-bottom: 20px; }}
.card h3 {{ color: #ff6b35; margin-bottom: 15px; font-size: 1.1em; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.9em; }}
th {{ text-align: left; padding: 8px 10px; border-bottom: 2px solid #2a3a4a; color: #888; font-weight: normal; }}
td {{ padding: 8px 10px; border-bottom: 1px solid #1e2a35; }}
tr:hover td {{ background: #1e2a35; }}
canvas {{ max-height: 350px; }}
.footer {{ text-align: center; color: #555; margin-top: 30px; font-size: 0.8em; }}
</style>
</head>
<body>
<div class="header">
    <h1>🎮 冒险岛世界 · 亚服阿尔泰 · 游戏币比例</h1>
    <p class="subtitle">数据来源: DD373 · {now_str} 北京时间 · 每30分钟自动更新</p>
</div>

<div class="summary-bar">
    <div class="summary-item">
        <div class="label">📦 在线商品</div>
        <div class="value">{latest.get('total_listings', 0)}</div>
    </div>
    <div class="summary-item">
        <div class="label">💰 均价</div>
        <div class="value">1元 = {avg}万</div>
        <div class="sub">1亿 ≈ ¥{yi_per_yuan}</div>
    </div>
    <div class="summary-item">
        <div class="label">🥇 最优比例</div>
        <div class="value">1元 = {best.get('rate_wan_per_yuan', 0)}万</div>
        <div class="sub">¥{best.get('price_cny', 0)}/{best.get('mesos_wan', 0)}万</div>
    </div>
    <div class="summary-item">
        <div class="label">📊 买卖价差</div>
        <div class="value">{spread_pct:.1f}%</div>
    </div>
</div>

<div class="dashboard">
    <div class="card">
        <h3>📈 游戏币比例走势 (1元=？万 · 越高越划算)</h3>
        <canvas id="rateChart"></canvas>
    </div>

    <div class="card">
        <h3>📋 当前在售商品 (按比例从优到差)</h3>
        <div style="overflow-x: auto;">
            <table>
                <thead><tr><th>#</th><th>数量</th><th>价格</th><th>比例</th><th>单价</th><th>标注</th></tr></thead>
                <tbody>{listing_rows}</tbody>
            </table>
        </div>
    </div>
</div>

<div class="footer">
    <p>📊 数据来源: DD373 (dd373.com) · 冒险岛世界 亚服 阿尔泰</p>
    <p>⚡ GitHub Actions 自动监控 · 历史数据保留90天</p>
</div>

<script>
new Chart(document.getElementById('rateChart').getContext('2d'), {{
    type: 'line',
    data: {{
        labels: {json.dumps(timestamps[-30:])},
        datasets: [
            {{
                label: '最优比例 (1元=X万)',
                data: {json.dumps([x for x in best_rates[-30:] if x])},
                borderColor: '#4caf50', backgroundColor: '#4caf5033',
                tension: 0.3, fill: false, pointRadius: 2,
            }},
            {{
                label: '均价 (1元=X万)',
                data: {json.dumps([x for x in avg_rates[-30:] if x])},
                borderColor: '#ff6b35', backgroundColor: '#ff6b3533',
                tension: 0.3, fill: false, pointRadius: 2, borderWidth: 2,
            }},
            {{
                label: '最差比例 (1元=X万)',
                data: {json.dumps([x for x in worst_rates[-30:] if x])},
                borderColor: '#f44336', backgroundColor: '#f4433633',
                tension: 0.3, fill: false, pointRadius: 2,
            }},
        ]
    }},
    options: {{
        responsive: true, maintainAspectRatio: true,
        interaction: {{ intersect: false, mode: 'index' }},
        plugins: {{ legend: {{ labels: {{ color: '#aaa', usePointStyle: true, padding: 15 }} }} }},
        scales: {{
            x: {{ ticks: {{ color: '#666', maxTicksLimit: 10 }} }},
            y: {{ ticks: {{ color: '#666', callback: v => '1元=' + v + '万' }} }}
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


def run_once():
    ts = datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{ts}] 抓取 DD373 冒险岛世界金价...")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    result = fetch_dd373()
    record = {"timestamp": datetime.now(TZ).isoformat(), "platforms": [result]}
    save_record(record)

    report = generate_html_report()

    if "error" in result:
        print(f"  ❌ {result['error']}")
    else:
        br = result.get("best_rate", {})
        wr = result.get("worst_rate", {})
        sp = (br.get("rate_wan_per_yuan", 1) / wr.get("rate_wan_per_yuan", 1) - 1) * 100 if wr.get("rate_wan_per_yuan") else 0
        print(f"  ✅ {result['total_listings']}商品 | 均价 1元={result['avg_rate_wan_per_yuan']}万 | 价差 {sp:.1f}%")

    if report:
        print(f"  📊 {report}")

    return record


if __name__ == "__main__":
    run_once()