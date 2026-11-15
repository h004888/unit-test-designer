"""utd.interview.export - Sinh `interview.html` tự chứa và `ui_payload.json`.

Ràng buộc:
  - Không CDN, không fetch, không tài nguyên ngoài: mở từ đĩa là chạy.
  - Chữ ký được tính trong trình duyệt bằng Web Crypto (SHA-256) với salt sinh
    mỗi lần xuất. Salt KHÔNG được ghi ra file ngoài HTML (nó nằm trong HTML).
  - Nút xuất tải `answers.json` gồm id, value, nonce, sig.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from ..io import atomic_write
from .signature import make_salt

PAGE_TEMPLATE = """<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Phỏng vấn đặc tả — {title}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
         margin: 0; padding: 1.25rem; background: #f7f7f8; color: #17171a; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #131316; color: #ececf1; }}
    .card {{ background: #1c1c21; border-color: #2c2c33; }}
  }}
  h1 {{ font-size: 1.25rem; margin: 0 0 .25rem; }}
  .meta {{ font-size: .85rem; opacity: .75; margin-bottom: 1rem; }}
  .card {{ background: #fff; border: 1px solid #dcdce0; border-radius: 10px;
          padding: .85rem; margin-bottom: .75rem; }}
  .tag {{ display: inline-block; font-size: .7rem; padding: .1rem .4rem;
         border-radius: 4px; margin-right: .35rem; font-weight: 600; }}
  .tag.critical {{ background: #ffe1e1; color: #a11; }}
  .tag.standard {{ background: #e2eeff; color: #115; }}
  @media (prefers-color-scheme: dark) {{
    .tag.critical {{ background: #4a1d1d; color: #ffb9b9; }}
    .tag.standard {{ background: #1d2a4a; color: #b9cbff; }}
  }}
  .qid {{ font-size: .72rem; opacity: .6; font-family: ui-monospace, monospace; }}
  .q {{ margin: .35rem 0 .5rem; }}
  ul.opts {{ list-style: none; padding: 0; margin: 0 0 .5rem; }}
  ul.opts li {{ margin: .2rem 0; }}
  textarea {{ width: 100%; min-height: 3rem; font: inherit; padding: .4rem;
             border-radius: 6px; border: 1px solid #c9c9cf; background: transparent;
             color: inherit; }}
  button {{ font: inherit; padding: .5rem .9rem; border-radius: 8px; border: 0;
           background: #2b59d6; color: #fff; cursor: pointer; }}
  button:disabled {{ opacity: .5; cursor: not-allowed; }}
  .bar {{ position: sticky; top: 0; z-index: 2; padding: .6rem 0;
         background: inherit; display: flex; gap: .6rem; align-items: center;
         flex-wrap: wrap; }}
  .count {{ font-size: .85rem; opacity: .8; }}
</style>
</head>
<body>
<h1>Phỏng vấn đặc tả — {title}</h1>
<p class="meta">{meta}</p>
<div class="bar">
  <button id="export" disabled>Xuất answers.json</button>
  <span class="count" id="count">0 / {total} đã trả lời</span>
</div>
<div id="list"></div>
<script>
const SESSION = {session_json};
const cards = document.getElementById('list');
const state = new Map();
const countEl = document.getElementById('count');
const exportBtn = document.getElementById('export');

function esc(s) {{
  return String(s).replace(/[&<>"']/g, c => ({{
    '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
  }})[c]);
}}

function updateCount() {{
  const done = state.size;
  countEl.textContent = done + ' / ' + SESSION.questions.length + ' đã trả lời';
  exportBtn.disabled = done === 0;
}}

async function sha256Hex(text) {{
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf))
    .map(b => b.toString(16).padStart(2, '0')).join('');
}}

function render() {{
  SESSION.questions.forEach((q, index) => {{
    const card = document.createElement('div');
    card.className = 'card';
    const opts = (q.alternative_options || []).length
      ? '<ul class="opts">' + [q.recommended_option].concat(q.alternative_options)
          .map(o => `<li><label><input type="radio" name="o${{index}}"
             value="${{esc(o)}}"> ${{esc(o)}}</label></li>`).join('') + '</ul>'
      : '';
    card.innerHTML = `
      <div><span class="tag ${{q.tier.toLowerCase()}}">${{esc(q.tier)}}</span>
        <span class="qid">${{esc(q.rule_id)}} · ${{esc(q.endpoint_label)}}</span></div>
      <div class="q" id="q${{index}}">${{esc(q.question)}}</div>
      ${{opts}}
      <textarea placeholder="Trả lời hoặc ghi chú cho câu này"></textarea>`;
    cards.appendChild(card);

    const area = card.querySelector('textarea');
    const radios = card.querySelectorAll('input[type=radio]');

    function record() {{
      const choice = Array.from(radios).find(r => r.checked);
      const text = area.value.trim();
      const value = text || (choice ? choice.value : '');
      if (!value) {{
        state.delete(q.id);
      }} else {{
        state.set(q.id, value);
      }}
      updateCount();
    }}

    radios.forEach(r => r.addEventListener('change', record));
    area.addEventListener('input', record);
  }});
}}

exportBtn.addEventListener('click', async () => {{
  exportBtn.disabled = true;
  exportBtn.textContent = 'Đang ký...';
  const answers = [];
  for (const q of SESSION.questions) {{
    const value = state.get(q.id);
    if (!value) continue;
    const sig = await sha256Hex(q.id + '|' + value.trim() + '|' + q.nonce + '|' + SESSION.salt);
    answers.push({{ id: q.id, value: value, nonce: q.nonce, sig: sig }});
  }}
  const payload = {{
    schema_version: 1,
    salt: SESSION.salt,
    createdAt: new Date().toISOString(),
    answers: answers
  }};
  const blob = new Blob([JSON.stringify(payload, null, 2)], {{ type: 'application/json' }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'answers.json';
  link.click();
  URL.revokeObjectURL(url);
  exportBtn.textContent = 'Xuất answers.json';
  exportBtn.disabled = false;
}});

render();
updateCount();
</script>
</body>
</html>
"""


def _render_meta(project: dict[str, Any], coverage: dict[str, Any]) -> str:
    parts = []
    if project.get("name"):
        parts.append(html.escape(str(project["name"])))
    if project.get("code"):
        parts.append(f"Mã: {html.escape(str(project['code']))}")
    parts.append(
        f"{coverage.get('questions', 0)} câu hỏi · "
        f"{coverage.get('critical', 0)} CRITICAL · "
        f"{coverage.get('standard', 0)} STANDARD · "
        f"{coverage.get('matched', 0)}/{coverage.get('total_rules', 0)} rule áp dụng"
    )
    return " — ".join(parts)


def build_ui_payload(checklist: dict[str, Any]) -> dict[str, Any]:
    """Payload dạng câu hỏi trắc nghiệm cho công cụ hỏi đáp của assistant.

    Chỉ gồm câu CRITICAL; STANDARD đi qua lô (batch consent) sau khi CRITICAL xong.
    """
    salt = make_salt()
    questions = []
    for item in checklist.get("questions", []):
        if item.get("tier") != "CRITICAL":
            continue
        options = [f"(Recommended) {item['recommended_option']}"]
        for alt in item.get("alternative_options", []):
            if alt and alt != item.get("recommended_option"):
                options.append(str(alt))
        questions.append(
            {
                "id": item["id"],
                "rule_id": item["rule_id"],
                "rule_ids": item.get("rule_ids", [item["rule_id"]]),
                "nonce": item["nonce"],
                "question": item["question"],
                "questions": item.get("questions", [item["question"]]),
                "options": options,
            }
        )
    return {"schema_version": 1, "salt": salt, "questions": questions}


def export_html(checklist: dict[str, Any], out_path: str | Path) -> Path:
    salt = make_salt()
    session = {
        "salt": salt,
        "questions": [
            {
                "id": item["id"],
                "rule_id": item["rule_id"],
                "rule_ids": item.get("rule_ids", [item["rule_id"]]),
                "tier": item["tier"],
                "endpoint_label": item["endpoint_label"],
                "param_name": item.get("param_name"),
                "question": item["question"],
                "questions": item.get("questions", [item["question"]]),
                "recommended_option": item["recommended_option"],
                "alternative_options": item.get("alternative_options", []),
                "nonce": item["nonce"],
            }
            for item in checklist.get("questions", [])
        ],
    }
    content = PAGE_TEMPLATE.format(
        title=html.escape(str(checklist.get("project", {}).get("name", "Unit Test"))),
        meta=_render_meta(checklist.get("project", {}), checklist.get("coverage", {})),
        total=len(session["questions"]),
        session_json=json.dumps(session, ensure_ascii=False),
    )
    return atomic_write(out_path, content)


def export_ui_payload(checklist: dict[str, Any], out_path: str | Path) -> Path:
    payload = build_ui_payload(checklist)
    return atomic_write(
        out_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    )
