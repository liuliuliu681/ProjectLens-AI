"""Convert the final Markdown report to a portable, self-contained HTML file."""

import html
import re
from datetime import datetime

import markdown


_WINDOWS_PATH = re.compile(r"(?i)(?<!\w)[a-z]:[\\/](?:[^\s<>|\"']+[\\/])*[^\s<>|\"']+")
_AUTH = re.compile(r"(?im)\bAuthorization\s*[:=]\s*[^\s<]+(?:\s+[^\s<]+)?")
_ENV_KEY = re.compile(r"(?im)\bLLM_API_KEY\s*=\s*[^\s<]+")


def render_html(markdown_text: str, report_type: str, *, generated_at: datetime | None = None,
                secrets: tuple[str, ...] = ()) -> str:
    """Escape source HTML and redact credentials and local paths before conversion."""
    if report_type not in {"research", "engineering", "short"}:
        raise ValueError("不支持的报告类型")
    safe = markdown_text
    for secret in secrets:
        if secret:
            safe = safe.replace(secret, "[已隐藏]")
    safe = _AUTH.sub("[已隐藏]", safe)
    safe = _ENV_KEY.sub("[已隐藏]", safe)
    safe = _WINDOWS_PATH.sub("[本机路径已隐藏]", safe)
    # Markdown's raw HTML passthrough is disabled by escaping the source first.
    body = markdown.markdown(html.escape(safe), extensions=["tables", "sane_lists"])
    label = {"research": "科研阶段报告", "engineering": "工程阶段报告", "short": "简短总结"}[report_type]
    stamp = (generated_at or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ProjectLens AI · {label}</title>
<style>
body{{margin:0;background:#f5f7fa;color:#202b36;font:16px/1.7 system-ui,"Microsoft YaHei",sans-serif}}
main{{max-width:900px;margin:32px auto;padding:48px;background:#fff;box-shadow:0 2px 20px #172a3a12}}
.brand{{color:#37536b;font-weight:700;letter-spacing:.04em}}.meta{{color:#657583;font-size:.9rem}}
h1{{font-size:2rem;margin:.8em 0}}h2{{border-bottom:1px solid #d9e2e8;padding-bottom:.3em;margin-top:1.6em}}
h3{{margin-top:1.4em}}table{{width:100%;border-collapse:collapse;margin:1em 0}}th,td{{border:1px solid #d9e2e8;padding:.55em .7em;text-align:left}}th{{background:#eef3f6}}tr:nth-child(even){{background:#fafcfd}}
li{{margin:.35em 0}}@media print{{body{{background:#fff}}main{{box-shadow:none;margin:0;padding:0;max-width:none}}}}
@media(max-width:700px){{main{{margin:0;padding:22px}}table{{font-size:.85rem}}}}
</style></head><body><main><div class="brand">ProjectLens AI</div>
<div class="meta">报告类型：{label} · 生成时间：{stamp}</div>
{body}
</main></body></html>'''
