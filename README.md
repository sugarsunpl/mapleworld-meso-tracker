# 冒险岛世界 MapleStory Worlds 游戏币多平台监控

自动监控 **冒险岛世界 (MapleStory Worlds) 亚服阿尔泰** 游戏币比例，每 30 分钟更新。

## 监控平台

| 平台 | 币种 | 链接 |
|------|------|------|
| DD373 | 人民币 (CNY) | [查看](https://www.dd373.com/s-n95vb3-c-r9tnsn-qhgknj-1crcd9.html) |
| 8591 | 台币→人民币 (TWD→CNY) | [查看](https://www.8591.com.tw/v3/mall/list/61990?searchGame=61990&searchServer=64071&searchType=0) |

## 查看报表

最新报表：https://htmlpreview.github.io/?https://github.com/你的用户名/mapleworld-meso-tracker/blob/main/reports/dd373_report.html

或者直接查看 [reports/dd373_report.html](reports/dd373_report.html)

## 数据说明

- `data/dd373_history.json` - 历史价格数据（保留90天）
- `reports/dd373_report.html` - 可视化报表（含走势图）
- 8591 台币汇率参考值：1 TWD = 0.242 CNY

## 本地运行

```bash
pip install requests beautifulsoup4
python dd373_tracker.py
```
