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

检查环境：

```powershell
python --version
node --version
npm --version
```

启动脚本会优先使用 `pnpm`；如果电脑没有安装 `pnpm`，会自动使用 Node.js 自带的 `npm`，无需额外安装。

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

## 启动与暂停本地网站

### 启动

先进入下载或克隆后的项目根目录，也就是能看到 `start.cmd` 和 `stop.cmd` 的文件夹。

最简单的方法是在文件资源管理器中打开该文件夹，在地址栏输入 `powershell` 后按回车，然后运行：

```powershell
.\start.cmd
```

也可以先用 `cd` 进入你实际保存项目的位置，例如：

```powershell
cd "D:\你实际保存项目的位置\ai-fund-assistant"
.\start.cmd
```

`start.cmd` 会自动用正确的 PowerShell 参数调用 `start.ps1`，无需修改电脑的执行策略。

首次运行会自动创建 Python 虚拟环境并安装前后端依赖。启动完成后：

- Web 页面：<http://127.0.0.1:4173>
- API 文档：<http://127.0.0.1:8010/docs>

### 暂停

需要关闭本地网站时，在同一个项目根目录运行：

```powershell
.\stop.cmd
```

看到下面的提示表示停止命令已经执行：

```text
AI Fund Assistant stopped.
```

刷新 <http://127.0.0.1:4173> 后应显示无法访问。如果浏览器仍保留旧画面，按 `Ctrl + F5` 强制刷新；浏览器可能暂时显示已经加载到内存中的页面，但本地服务实际上已经停止。

停止脚本会同时关闭：

- 前端端口 `4173`
- 后端端口 `8010`

> `stop.cmd` 只会暂停当前电脑上的本地网站，不会关闭 GitHub Pages 在线演示版。在线演示仍可通过 <https://ljf52.github.io/ai-fund-assistant/> 访问。

### 重新启动

暂停后需要再次使用时，在项目根目录重新运行：

```powershell
.\start.cmd
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
npm install
npm run dev -- --host 127.0.0.1 --port 4173
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
npm run build
```

## 常见问题

### 页面打不开

确认 `start.cmd` 已显示启动成功，然后检查 `logs/backend-error.log` 和 `logs/frontend-error.log`。本项目使用后端端口 `8010` 和前端端口 `4173`。

### `pnpm` 无法识别

无需安装 `pnpm`。更新到最新版代码后运行 `.\start.cmd`，启动脚本会自动改用 Node.js 自带的 `npm`。

### 盘中估值与其他平台不完全一致

不同平台可能使用不同指数源、ETF 行情、现金仓位和费用估算模型。正式收益应以基金管理人最终公布的净值为准。

### 行情同步失败

公开数据源可能限流或短暂不可用。系统会保留最近一次成功数据，可以稍后点击“同步真实数据”重试。

## 隐私与安全

- `.env`、SQLite 数据库、日志、依赖目录和本地测试截图均已加入 `.gitignore`。
- 持仓份额和成本只保存在本机 SQLite 数据库，不会随源码上传。
- 如果 API Key 曾经出现在聊天记录或其他公开位置，请先在服务商控制台轮换密钥。
