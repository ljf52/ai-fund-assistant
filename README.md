# 知衡 · AI 基金助手

知衡是一套面向个人投资者的本地基金资产管理与 AI 投资辅助应用。它将官方基金净值、盘中估值、目标 ETF 穿透持仓、市场雷达和个人成本数据放在同一视图中，帮助用户区分“已披露事实”和“盘中估算”。

> 本项目仅用于信息整理和投资研究，不构成投资建议，不执行自动交易。盘中估值并非基金管理人公布的正式净值。

## 在线演示

GitHub Pages：<https://ljf52.github.io/ai-fund-assistant/>

在线版本使用虚构示例数据，仅用于体验界面；GitHub Pages 无法运行 FastAPI、SQLite 和 DeepSeek 后端。本地启动版本仍可同步真实数据。

## 主要功能

- 资产总览：总资产、累计收益、盘中预计今日收益与持仓分布。
- 持仓管理：新增、编辑和移除基金，可维护份额、成本净值和目标仓位。
- 真实基金数据：同步基金名称、净值历史、基金经理及定期报告持仓。
- ETF 穿透持仓：识别 ETF 联接基金，并展示目标 ETF 的最新前十大股票。
- 盘中估值：使用目标指数或目标 ETF 行情估算当日净值与收益，默认每 30 秒刷新。
- 市场雷达：展示主要指数和申万一级行业强弱，交易时段自动刷新。
- AI 日报：结合个人成本、仓位和市场行情生成市场总结、持仓影响、风险与观察条件。
- 数据状态：显示数据来源、官方净值日期、行情更新时间和同步结果。

## 技术栈

- 前端：Vue 3、Vite、ECharts
- 后端：FastAPI、SQLite、Pydantic
- 数据：东方财富/天天基金、新浪财经、申万宏源、AKShare
- AI：DeepSeek OpenAI 兼容 API（可选）

## 环境要求

推荐使用 Windows 10/11 和 PowerShell 5.1 或更高版本，并提前安装：

- Python 3.11+
- Node.js 20+
- pnpm 9+

检查环境：

```powershell
python --version
node --version
pnpm --version
```

如果尚未安装 pnpm：

```powershell
npm install --global pnpm
```

## 下载与安装

```powershell
git clone https://github.com/ljf52/ai-fund-assistant.git
cd ai-fund-assistant
Copy-Item backend\.env.example backend\.env
```

DeepSeek API 并非启动项目的必需条件。未配置时，AI 日报会使用本地纪律规则生成。

如需启用 DeepSeek，请编辑 `backend/.env`：

```env
DEEPSEEK_API_KEY=你的新密钥
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_BASE_URL=https://api.deepseek.com
DATABASE_PATH=data/fund_assistant.db
DATA_MODE=auto
AUTO_SYNC_ENABLED=true
SYNC_INTERVAL_MINUTES=360
```

不要把真实密钥写入 `.env.example`，也不要提交本地 `.env` 文件。

## 一键启动

在项目根目录运行：

```powershell
.\start.ps1
```

首次运行会自动创建 Python 虚拟环境并安装前后端依赖。启动完成后：

- Web 页面：<http://127.0.0.1:4173>
- API 文档：<http://127.0.0.1:8010/docs>

停止服务：

```powershell
.\stop.ps1
```

如果 PowerShell 禁止执行脚本，可以临时放行当前窗口：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\start.ps1
```

## 手动启动

后端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

另开一个 PowerShell 窗口启动前端：

```powershell
cd frontend
pnpm install
pnpm dev --host 127.0.0.1 --port 4173
```

## 数据更新机制

- 官方基金净值通常在交易日结束后公布，因此会晚于盘中行情。
- 盘中估值使用目标指数行情，失败时回退至目标 ETF 行情。
- 市场雷达在交易时段每 30 秒刷新；休市后保留最后一次成功行情。
- 后台启动后会同步一次真实数据，此后默认每 6 小时同步，也可以在页面右上角手动同步。
- 当前内置 `007818 → 515880 → 931160` 的联接基金穿透与估值映射，其他联接基金可继续扩展映射表。

## 主要接口

| 接口 | 说明 |
|---|---|
| `GET /api/dashboard` | 资产与收益总览 |
| `GET/POST /api/holdings` | 查询或新增持仓 |
| `PATCH/DELETE /api/holdings/{id}` | 编辑或移除持仓 |
| `GET /api/funds/{code}` | 基金详情、净值与穿透持仓 |
| `POST /api/funds/{code}/refresh` | 刷新单只基金数据 |
| `GET /api/search/funds?q=代码` | 搜索真实基金 |
| `GET /api/realtime/holdings` | 全部持仓盘中估值 |
| `GET /api/realtime/funds/{code}` | 单只持仓盘中估值 |
| `GET /api/market` | 实时指数与行业雷达 |
| `POST /api/data/sync` | 同步基金和市场数据 |
| `GET /api/data/status` | 查询数据来源与同步状态 |
| `POST /api/reports/generate` | 生成 AI 投资日报 |

## 测试与构建

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests -q

cd ..\frontend
pnpm build
```

## 常见问题

### 页面打不开

确认 `start.ps1` 已显示启动成功，然后检查 `logs/backend-error.log` 和 `logs/frontend-error.log`。本项目使用后端端口 `8010` 和前端端口 `4173`。

### `pnpm` 无法识别

运行 `npm install --global pnpm`，安装后重新打开 PowerShell。

### 盘中估值与其他平台不完全一致

不同平台可能使用不同指数源、ETF 行情、现金仓位和费用估算模型。正式收益应以基金管理人最终公布的净值为准。

### 行情同步失败

公开数据源可能限流或短暂不可用。系统会保留最近一次成功数据，可以稍后点击“同步真实数据”重试。

## 隐私与安全

- `.env`、SQLite 数据库、日志、依赖目录和本地测试截图均已加入 `.gitignore`。
- 持仓份额和成本只保存在本机 SQLite 数据库，不会随源码上传。
- 如果 API Key 曾经出现在聊天记录或其他公开位置，请先在服务商控制台轮换密钥。
