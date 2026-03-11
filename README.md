# 港股 ETF + 期权自动报告系统

免费版自动化系统：采集港股 ETF 行情与 Yahoo 期权链，生成策略报告，并通过 `openclaw` 推送到 Telegram。

## 目录位置（重要）

请把项目放在非受保护目录，例如：

```bash
~/hongkong_trade
```

不建议放在以下目录（macOS 上 cron 可能无权限访问，导致“定时触发但不发消息”）：
- `~/Documents`
- `~/Desktop`
- `~/Downloads`

如果你当前在 `Documents`，可迁移到 `~/hongkong_trade`：

```bash
mkdir -p ~/hongkong_trade
rsync -a --delete ~/Documents/hongkong_trade/ ~/hongkong_trade/
cd ~/hongkong_trade
.venv/bin/python -m hk_trade.install_cron --install
```

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

建议在 `.env` 显式设置 `OPENCLAW_BIN` 为绝对路径（避免 cron 的 PATH 找不到命令）：

```bash
OPENCLAW_BIN=/opt/homebrew/bin/openclaw
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

macOS 自带的 vixie cron 对 `CRON_TZ` 支持有限，因此项目采用“调度器”方案：
- `crontab` 每分钟触发一次 `hk_trade.cron_dispatch`（调度器内部判断是否该发送）
- 调度器内部按时区判断是否真正执行发送：
  - 港股交易时段（`Asia/Hong_Kong`）
  - 美股常规交易时段（`America/New_York`，适用于 FXI/YINN/KWEB/CWEB）
  - 港股 22:00 日报

预览将写入的 crontab：

```bash
python3 -m hk_trade.install_cron --print
```

安装/更新 crontab：

```bash
python3 -m hk_trade.install_cron --install
```

重新安装/覆盖（推荐在项目虚拟环境执行）：

```bash
cd ~/hongkong_trade
.venv/bin/python -m hk_trade.install_cron --install
```

移除本系统 cron 块：

```bash
python3 -m hk_trade.install_cron --remove
```

日常检查：

```bash
# 查看 cron 是否存在
crontab -l

# 查看任务运行日志
tail -f ~/hongkong_trade/logs/cron.log

# 查看最新报告文件
ls -t ~/hongkong_trade/reports/*/*.md | head -1

# 检查/重启 OpenClaw gateway
openclaw gateway health
openclaw gateway restart
```

说明：调度器会持续写 `[dispatch] tick no-task ...` 心跳日志，表示 cron 正常触发但当前不在发报时间窗。

## 测试

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

## 免责声明

本系统仅提供研究信息与风险提示，不构成投资建议，不执行自动下单。
