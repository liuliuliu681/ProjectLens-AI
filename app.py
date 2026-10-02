"""Single-page ProjectLens AI MVP."""

import hashlib
import logging
import tempfile
from datetime import datetime
from pathlib import Path

import streamlit as st

from core.calculator import compare_experiments
from core.config import LLMConfig, load_llm_config, resolve_llm_config, save_llm_config
from core.experiment_parser import parse_file as parse_experiment_file
from core.llm_client import (
    LLMAuthenticationError, LLMClient, LLMClientError, LLMRateLimitError,
    LLMServerError, LLMTimeoutError,
)
from core.markdown_renderer import render_markdown
from core.html_renderer import render_html
from core.prompt_builder import PromptBuilder
from core.response_validator import ReportValidationError, validate_report_draft
from core.response_validator import validate_experiment_draft_numbers, validate_single_experiment_draft
from core.test_parser import parse_test_file
from core.ui_helpers import (
    EXPERIMENT_SUFFIXES, SOFTWARE_SUFFIXES, analysis_result,
    build_download_filename, comparison_rows, validate_upload,
    experiment_reportable, group_experiments, report_disabled_reason,
)
from models.schemas import ExperimentFacts, ProjectFacts


MODES = ("模型实验分析", "软件测试分析", "项目阶段总结")
STYLES = {"科研汇报": "research", "工程周报": "engineering", "简短总结": "short"}
LOGGER = logging.getLogger(__name__)


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, LLMAuthenticationError):
        return "HTTP 401：API Key 无效或已失效。"
    if isinstance(exc, LLMRateLimitError):
        return "HTTP 429：请求频率受限，请稍后重试。"
    if isinstance(exc, LLMTimeoutError):
        return "API 请求超时。"
    if isinstance(exc, LLMServerError):
        return "模型服务暂时异常。"
    if isinstance(exc, ReportValidationError):
        return "模型返回内容未通过报告格式校验。"
    return "请求失败，请检查 Base URL、模型名称及网络连接。"


def _current_config(saved: LLMConfig) -> LLMConfig:
    return resolve_llm_config(
        saved,
        api_key=st.session_state.get("api_key_input", ""),
        base_url=st.session_state["base_url_input"],
        model=st.session_state["model_input"],
        timeout=st.session_state["timeout_input"],
    )


def _config_panel() -> LLMConfig:
    saved = load_llm_config()
    if st.session_state.pop("clear_api_key_input", False):
        st.session_state["api_key_input"] = ""
    st.session_state.setdefault("base_url_input", saved.base_url)
    st.session_state.setdefault("model_input", saved.model)
    st.session_state.setdefault("timeout_input", str(saved.timeout))
    with st.sidebar:
        st.header("模型配置")
        if st.session_state.pop("config_saved", False):
            st.success("配置已保存到本机")
            st.caption("配置仅保存在本机 .env，请勿提交到 Git。")
        st.caption("API Key：已配置" if saved.api_key else "API Key：未配置")
        st.text_input("API Key", type="password", key="api_key_input", placeholder="输入新的 API Key 可覆盖已有配置")
        st.text_input("Base URL", key="base_url_input")
        st.text_input("Model", key="model_input")
        st.text_input("Timeout（秒）", key="timeout_input")
        test_col, save_col = st.columns(2)
        if test_col.button("测试连接", width="stretch"):
            try:
                config = _current_config(saved)
                LLMClient(**config.__dict__).generate("请用一句简短文字回应。", "请回答：连接正常。")
            except ValueError as exc:
                st.error(str(exc))
            except LLMClientError as exc:
                LOGGER.warning("Connection test failed: %s", type(exc).__name__)
                st.error(_safe_error(exc))
            else:
                st.success(f"API 连接成功 · Model: {config.model}")
        if save_col.button("保存配置", width="stretch"):
            try:
                config = _current_config(saved)
                save_llm_config(config)
            except ValueError as exc:
                st.error(str(exc))
            except OSError:
                st.error("配置写入失败，请检查项目目录权限。")
            else:
                st.session_state["config_saved"] = True
                st.session_state["clear_api_key_input"] = True
                st.rerun()
    return load_llm_config()


def _parse_uploaded(upload, experiment: bool):
    allowed = EXPERIMENT_SUFFIXES if experiment else SOFTWARE_SUFFIXES
    suffix = validate_upload(upload.name, upload.size, allowed)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / ("upload" + suffix)
        path.write_bytes(upload.getvalue())
        return parse_experiment_file(path) if experiment else parse_test_file(path)


def _upload_facts(mode: str):
    experiment_files = []
    software_files = []
    st.subheader("Step 1 · 上传文件")
    if mode in {MODES[0], MODES[2]}:
        experiment_files = st.file_uploader("实验数据（CSV / JSON）", type=["csv", "json"],
                                            accept_multiple_files=True, key=f"experiments_{mode}") or []
    if mode in {MODES[1], MODES[2]}:
        software_files = st.file_uploader("测试日志（TXT / LOG / MD）", type=["txt", "log", "md"],
                                          accept_multiple_files=True, key=f"software_{mode}") or []
    if len(experiment_files) + len(software_files) > 10:
        st.error("最多上传 10 个文件，请减少文件数量。")
        return [], [], False, "", [], False
    fingerprint = hashlib.sha256()
    runs = []
    analyses = []
    acceptable = True
    limitations = []
    diagnostic = False
    for upload, experiment in [(item, True) for item in experiment_files] + [(item, False) for item in software_files]:
        fingerprint.update(upload.name.encode("utf-8"))
        fingerprint.update(upload.getvalue())
        try:
            result = _parse_uploaded(upload, experiment)
        except (OSError, ValueError) as exc:
            st.error(f"{upload.name}：{exc}")
            acceptable = False
            continue
        if experiment:
            runs.extend((upload.name, run) for run in result.experiments)
            status, warnings = result.status, result.warnings + result.errors
            for info in result.infos:
                st.caption(f"{upload.name}：{info}")
            if result.profile == "instance_diagnostic":
                diagnostic = True
        else:
            analyses.append((upload.name, result))
            status, warnings = result.parse_status, result.parse_warnings
        if status == "unrecognized":
            st.error(f"{upload.name}：无法可靠解析该文件。")
            acceptable = False
        elif status == "partial":
            message = ("已识别实例诊断文件，但没有可用于标准模型对比的完整指标。"
                       if experiment and result.profile == "instance_diagnostic"
                       else "部分信息缺失或存在矛盾。")
            st.warning(f"{upload.name}：{message}")
            if not experiment or not experiment_reportable(result):
                acceptable = False
            else:
                limitations.extend(f"{upload.name}：{warning}" for warning in warnings)
        for warning in warnings:
            st.caption(f"{upload.name}：{warning}")
    return runs, analyses, acceptable, fingerprint.hexdigest(), limitations, diagnostic


def _select_comparison(runs):
    if len(runs) < 2:
        return None
    compatible_pairs = [
        (i, j) for i, (_, left) in enumerate(runs)
        for j, (_, right) in enumerate(runs) if i < j
        and left.metric_scope == right.metric_scope and left.split == right.split
        and (left.name, left.seed) != (right.name, right.seed)
    ]
    if not compatible_pairs:
        st.info("需要两组具有相同指标口径和 split 的实验才能对比。")
        return None
    labels = [f"{run.name} · {run.metric_scope} · {run.split or 'split 未提供'} · "
              f"seed={run.seed if run.seed is not None else '未提供'} · {filename} · #{index + 1}"
              for index, (filename, run) in enumerate(runs)]
    baseline_index = st.selectbox("Baseline", range(len(runs)), index=compatible_pairs[0][0],
                                  format_func=lambda i: labels[i], key="baseline")
    current_index = st.selectbox("Current", range(len(runs)), index=compatible_pairs[0][1],
                                 format_func=lambda i: labels[i], key="current")
    if baseline_index == current_index:
        st.warning("请选择两个不同的实验。")
        return None
    baseline, current = runs[baseline_index][1], runs[current_index][1]
    if baseline.metric_scope != current.metric_scope:
        st.warning("请选择相同指标口径的两组实验；box、mask、类别 mask 和阈值扫描不能混比。")
        return None
    if baseline.split != current.split:
        st.warning("两组实验的 split 不一致或未同时提供，不能直接比较。")
        return None
    comparison = compare_experiments(baseline, current)
    st.dataframe(comparison_rows(comparison), hide_index=True, width="stretch")
    return comparison


def _select_experiment(groups: list[ExperimentFacts]) -> ExperimentFacts | None:
    if not groups:
        return None
    labels = []
    for facts in groups:
        if facts.profile == "threshold_sweep":
            labels.append(f"阈值扫描 · {len(facts.experiments)} 个阈值点")
        else:
            first = facts.experiments[0]
            labels.append(f"{first.name} · split={first.split or '未提供'} · "
                          f"seed={first.seed if first.seed is not None else '未提供'}")
    index = st.selectbox("选择实验", range(len(groups)), format_func=lambda i: labels[i], key="single_experiment")
    selected = groups[index]
    if selected.profile == "single":
        st.caption("指标口径：" + "、".join(run.metric_scope for run in selected.experiments))
    return selected


def _show_analyses(analyses):
    for filename, analysis in analyses:
        st.markdown(f"**{filename}**")
        st.json(analysis_result(analysis))
        if analysis.failed_items:
            st.dataframe([item.model_dump() for item in analysis.failed_items], hide_index=True, width="stretch")
        if analysis.error_messages:
            st.write("错误信息：", analysis.error_messages)


def main() -> None:
    st.set_page_config(page_title="ProjectLens AI", layout="wide")
    st.title("ProjectLens AI")
    st.caption("科研实验与软件项目记录分析助手")
    saved = _config_panel()
    mode = st.radio("分析模式", MODES, horizontal=True, key="mode")
    st.session_state["current_mode"] = mode
    runs, named_analyses, acceptable, file_signature, limitations, diagnostic = _upload_facts(mode)

    st.subheader("Step 2 · 查看 Python 解析结果")
    groups = group_experiments([run for _, run in runs], limitations)
    comparison = None
    selected_experiment = None
    comparison_mode = False
    if runs:
        st.caption(f"已读取 {len(groups)} 个逻辑实验；不同指标口径分别展示。")
        with st.expander("实验指标详情", expanded=len(runs) <= 8):
            st.dataframe([{"experiment": run.name, "scope": run.metric_scope,
                           "split": run.split, "seed": run.seed, **run.metrics.model_dump()}
                          for _, run in runs], hide_index=True, width="stretch")
        analysis_mode = (st.radio("分析方式", ("单实验分析", "Baseline / Current 对比"),
                                  horizontal=True, key="experiment_analysis_mode")
                         if len(groups) >= 2 else "单实验分析")
        comparison_mode = analysis_mode == "Baseline / Current 对比"
        if comparison_mode:
            comparison = _select_comparison(runs)
        else:
            selected_experiment = _select_experiment(groups)
    _show_analyses(named_analyses)
    analyses = [analysis for _, analysis in named_analyses]
    st.session_state["parsed_facts"] = {"experiments": [run for _, run in runs], "software": analyses}
    st.session_state["comparison"] = comparison

    st.subheader("Step 3 · 输入本轮说明")
    notes = st.text_area("本轮补充说明", key="user_notes", help="仅作为参考信息，不修改解析事实。")
    st.subheader("Step 4 · 选择报告风格")
    default_style = "科研汇报" if mode == MODES[0] else "工程周报"
    style_label = st.selectbox("报告风格", list(STYLES), index=list(STYLES).index(default_style), key=f"style_{mode}")
    report_type = STYLES[style_label]

    facts = None
    if mode == MODES[0]:
        selected_facts = comparison if comparison_mode else selected_experiment
        facts = ProjectFacts(comparison=comparison, experiments=[selected_experiment] if selected_experiment else []) if selected_facts and report_type == "engineering" else selected_facts
    elif mode == MODES[1] and analyses:
        facts = analyses
    elif mode == MODES[2] and (comparison or selected_experiment or analyses):
        facts = ProjectFacts(comparison=comparison, experiments=[selected_experiment] if selected_experiment else [], software=analyses)
    if report_type == "research" and comparison is None and selected_experiment is None:
        facts = None
    if not acceptable:
        facts = None
    if any(analysis.parse_status == "unrecognized" for analysis in analyses):
        facts = None
    signature = (mode, file_signature, comparison.model_dump_json() if comparison else None,
                 selected_experiment.model_dump_json() if selected_experiment else None,
                 notes, report_type)
    if st.session_state.get("report_signature") != signature:
        st.session_state["report"] = None

    st.subheader("Step 5 · 生成 AI 报告")
    try:
        config = _current_config(saved)
        configured = True
    except ValueError:
        configured = False
    reason = report_disabled_reason(facts, configured, has_upload=bool(runs or analyses),
                                    diagnostic=diagnostic, comparison_mode=comparison_mode)
    if reason:
        st.info(reason)
    if st.button("生成 AI 报告", disabled=reason is not None, type="primary"):
        try:
            with st.spinner("正在生成报告..."):
                system_prompt, user_prompt = PromptBuilder().build(report_type, facts, notes)
                raw = LLMClient(**config.__dict__).generate(system_prompt, user_prompt)
                draft = validate_report_draft(raw)
                if selected_experiment is not None and selected_experiment.profile == "single" and comparison is None:
                    validate_single_experiment_draft(draft)
                elif selected_experiment is not None and comparison is None:
                    validate_experiment_draft_numbers(draft)
                report = render_markdown(report_type, facts, draft)
        except (LLMClientError, ReportValidationError, ValueError) as exc:
            LOGGER.warning("Report generation failed: %s", type(exc).__name__)
            st.error("AI 报告生成失败：" + _safe_error(exc))
        else:
            st.session_state["report"] = report
            st.session_state["report_signature"] = signature
            st.session_state["download_filename"] = build_download_filename()
            st.session_state["report_type"] = report_type
            st.session_state["report_time"] = datetime.now()

    if st.session_state.get("report"):
        st.subheader("AI 分析报告")
        st.markdown(st.session_state["report"])
        st.write("Markdown 源文本（可复制）")
        st.code(st.session_state["report"], language="markdown")
        st.download_button("下载 Markdown", st.session_state["report"],
                           file_name=st.session_state["download_filename"], mime="text/markdown")
        html_report = render_html(st.session_state["report"], st.session_state["report_type"],
                                  generated_at=st.session_state["report_time"],
                                  secrets=(saved.api_key,))
        st.download_button("下载 HTML", html_report,
                           file_name=st.session_state["download_filename"].removesuffix(".md") + ".html",
                           mime="text/html")


if __name__ == "__main__":
    main()
