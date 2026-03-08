# 港股 ETF + 期权自动报告系统

免费版自动化系统：采集港股 ETF 行情与 Yahoo 期权链，生成策略报告，并通过 `openclaw` 推送到 Telegram。

## 功能

- ETF 数据采集（优先新浪 + 雪球，失败降级）
- 期权数据采集（Yahoo Finance，FXI/YINN/KWEB/CWEB）
- 双卖策略计算（Strangle / Iron Condor / Put Spread）
- 按规范渲染整合报告（ETF + 期权）
- SQLite 存档（快照、策略、推送日志、错误）
- Telegram 发送前网关健康检查
- `crontab` 一键安装（交易时段 + 收盘后 + 每日 22:00 HKT）

## 快速开始

1. 配置环境变量：

```bash
cp .env.example .env
```

2. 安装依赖（建议在虚拟环境）：

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

3. 先本地 dry-run：

```bash
python3 -m hk_trade.run_report --mode daily --dry-run
```

4. 真正发送：

```bash
python3 -m hk_trade.run_report --mode daily --send
```

## 定时任务

预览将写入的 crontab：

```bash
python3 -m hk_trade.install_cron --print
```

安装/更新 crontab：

```bash
python3 -m hk_trade.install_cron --install
```

移除本系统 cron 块：

```bash
python3 -m hk_trade.install_cron --remove
```

## 测试

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

## 免责声明

本系统仅提供研究信息与风险提示，不构成投资建议，不执行自动下单。
