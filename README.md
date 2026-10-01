# ProjectLens AI

ProjectLens AI 是一个将科研实验数据和软件测试日志转换为结构化事实，并利用 LLM 生成阶段报告的轻量级 AI 工程工具。

## Why

CSV / JSON / LOG → 人工查看 → 计算指标 → 整理结果 → 写阶段报告，是科研和软件项目中重复出现的流程。ProjectLens 将格式明确的解析、指标计算和事实展示交给 Python，再让 LLM 根据已验证事实撰写报告。

## Core Idea

Raw Files → File Loader → Parser → Structured Facts → Calculator → Prompt Builder → LLM → Response Validator → Markdown / HTML Renderer

Python 负责解析、归一化、计算与验证；LLM 负责语义分析、总结、风险与下一步建议。数值表由 Python 生成，不由模型重新计算。用户说明是补充信息，不能覆盖解析事实。

## Features

- CSV / JSON 实验解析；Baseline / Current 对比 Precision、Recall、F1、mAP 等指标。
- Flutter test、Flutter analyze、Godot test groups 和明确格式的测试总结解析；保留 test 与 test_group 口径，以及 passed、skipped、failed 的区别。
- 科研报告、工程报告和约 100～300 中文字的简短总结；项目阶段总结可合并实验和软件事实。
- OpenAI-compatible Chat Completions API；页面配置 API Key、Base URL、Model、Timeout，支持连接测试。
- Streamlit 单页面 UI；Markdown 和独立 HTML 导出；Windows onedir 可执行包。

## Quick Start

### Windows 用户

获取 `ProjectLensAI-v1.0.0-windows-x64.zip` 发布包，完整解压后双击 `ProjectLensAI/ProjectLensAI.exe`。默认浏览器会打开本机页面。在侧边栏填写自己的 API 配置并保存，然后上传文件使用。程序只绑定 `127.0.0.1`；首次运行的发布包不含 `.env`，也不含开发者 API Key。

### 开发者

需要 Python 3.11 或更新版本。

```powershell
git clone https://github.com/liuliuliu681/ProjectLens-AI.git
cd ProjectLens-AI
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

开发依赖：`pip install -r requirements-dev.txt`。Windows 打包：`pyinstaller --noconfirm --clean ProjectLensAI.spec`。

## API Configuration

侧边栏支持 API Key、Base URL、Model 和 Timeout。点击“保存配置”后，开发模式保存在项目根目录 `.env`；EXE 模式保存在 EXE 同目录 `.env`。已有 Key 只显示“已配置”，密码框不会回填明文。`.env` 在 `.gitignore` 中，不要手动提交。仅支持 OpenAI-compatible Chat Completions 风格接口，不保证兼容各 provider 的私有特性。

## Supported Inputs

| 用途 | 后缀 | 说明 |
| --- | --- | --- |
| 实验 | `.csv`、`.json` | 明确字段的实验记录 |
| 软件测试 | `.txt`、`.log`、`.md` | Flutter、Godot 和明确 summary |

MVP 使用确定性格式解析。无法可靠识别时显示 `unrecognized`，不会让 AI 猜任意文件结构。单文件上限 10 MB，一次最多 10 个文件；上传文件仅在当前页面会话中处理。

实验解析支持标准记录、明确字段的 YOLO segmentation summary、多随机种子原始 summary，以及模型 × 阈值的 sweep 表。总体 mask、box 和类别 mask 指标分口径保存；sweep 只有 Precision / Recall / F1，不补造 mAP。实例诊断 summary 会被识别，但其诊断 recall 不会冒充标准模型指标。

## Testing

```powershell
pip install -r requirements-dev.txt
pytest -ra
```

当前运行 `pytest -ra`：160 passed、0 failed、0 skipped、0 warnings。测试覆盖 File Loader、Experiment Parser、Metric Normalizer、Calculator、Software Parser、Flutter、Godot、LLM Client mock 与 retry、Prompt Builder、Response Validator、Markdown / HTML Renderer、Config、UI helper、路径和真实 fixtures。真实 API 可用 `python -m scripts.smoke_test_llm` 单独检查；普通 pytest 不调用真实 API。

## Real-world Validation

- 科研：`B0_rgb_baseline` 对 `C1_rgbd_dual_p3p4`，test / seed=42：Recall +17.09 pp，F1 +1.99 pp，mAP50 +5.98 pp。这是单 seed 结果，不能据此声称稳定提升。
- Flutter：257 total，242 passed，15 skipped，0 failed；analyze 0 errors、0 warnings、7 infos。
- Godot：51 test groups，51 passed，0 failed。统计单位是测试组。

真实日志位于 `tests/fixtures/`。日志中的本机临时路径已脱敏。

## Screenshots

`docs/images/` 已预留截图目录，计划从真实运行页面采集 `01_home.png`、`02_experiment.png`、`03_software_test.png`、`04_ai_report.png`、`05_api_config.png`。当前尚未保存这些截图；不会用模拟图代替。

## Project Structure

```text
app.py                    Streamlit 页面
launcher.py               Windows EXE 启动器
ProjectLensAI.spec        PyInstaller onedir 构建配置
core/                     解析、计算、配置、LLM、验证和渲染
models/schemas.py         Pydantic 数据模型
prompts/                  三种报告模板
examples/                 可公开的示例输入
tests/                    自动化测试及真实脱敏 fixtures
docs/images/              真实页面截图
scripts/smoke_test_llm.py 真实 API 链路检查
requirements.txt          运行依赖
requirements-dev.txt      测试和打包依赖
```

## Design Decisions

ProjectLens deliberately separates deterministic computation from semantic analysis. 实验指标变化、测试计数与统计单位由 Python 形成事实层；LLM 只处理解释和表述。最终 Markdown 和 HTML 共用同一次验证后的报告，不重复请求模型。

## Limitations

- 只支持明确格式；不支持 PDF / DOCX，不扫描完整代码仓库，无历史数据库或多人系统。
- 使用 Chat Completions 风格接口，不支持所有 OpenAI provider 私有能力。
- 当前 Windows 测试环境中，Flutter analyze 在中文路径下可能导致 Analysis Server 崩溃；同一仓库经英文路径 Junction 可正常 analyze。这是 Flutter / 当前开发环境限制，不是 ProjectLens Parser 错误。

## Future Work

Git history analysis、实验趋势可视化、Prompt 版本比较、批量实验目录分析。以上均未在 v1.0.0 实现。
