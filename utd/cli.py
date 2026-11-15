"""utd.cli - Một entry point cho toàn bộ 8 stage.

Exit code chuẩn hoá:
  0  pass
  1  gate block
  2  input invalid (cấu trúc)
  3  insufficient info (thiếu trường không suy được)
  4  tamper (chữ ký/nguồn gốc không hợp lệ)
  5  hash mismatch (artifact bị sửa ngoài luồng)

Giai đoạn 1: chỉ dựng khung CLI. Các stage in "not implemented" và trả exit 1.
"""

from __future__ import annotations

import argparse
import sys

from .io import reconfigure_stdout

EXIT_PASS = 0
EXIT_GATE = 1
EXIT_INVALID_INPUT = 2
EXIT_INSUFFICIENT_INFO = 3
EXIT_TAMPER = 4
EXIT_HASH_MISMATCH = 5

STAGES = (
    "ingest",
    "inventory",
    "interview",
    "lock",
    "generate",
    "audit",
    "emit",
    "reconcile",
)


def _not_implemented(stage: str) -> int:
    print(f"[!] stage '{stage}' not implemented", file=sys.stderr)
    return EXIT_GATE


def _resolve(workspace: str | Path, path: str | Path) -> Path:
    """Đường dẫn tương đối được hiểu theo `workspace`, không theo cwd."""
    from pathlib import Path as _Path

    candidate = _Path(path)
    if candidate.is_absolute():
        return candidate
    return _Path(workspace) / candidate


def _print_expanded_warnings(previous_checklist, checklist, limit: int = 10) -> None:
    """In cảnh báo khi câu đã trả lời có thêm rule mới.

    Hệ quả của id ổn định: câu không mất, nhưng phạm vi mở rộng. Người dùng cần
    biết câu trả lời cũ giờ áp dụng cho cả rule chưa thấy.
    """
    from .match.reconcile_checklist import expanded_answered_questions

    expanded = expanded_answered_questions(previous_checklist, checklist)
    if not expanded:
        return

    print(f"[!] {len(expanded)} câu đã trả lời giờ bao gồm thêm rule mới:")
    for question_id, added in expanded[:limit]:
        print(f"    - {question_id}: +{len(added)} rule ({', '.join(added[:3])}"
              f"{', …' if len(added) > 3 else ''})")
    if len(expanded) > limit:
        print(f"    … và {len(expanded) - limit} câu khác")
    print("    Câu trả lời hiện có được áp dụng cho cả rule mới — "
          "trả lời lại nếu cần khác.")


def _restore_flags(spec, previous_checklist) -> int:
    """Áp cờ đã xác nhận từ checklist cũ vào spec trước khi đánh giá rule.

    Cần thiết vì `spec.json` do ingest sinh ra, không biết câu trả lời cờ. Nếu
    không khôi phục, mỗi lần chạy lại `inventory` sẽ quay về cờ mặc định và
    rule phụ thuộc cờ lại biến mất khỏi checklist.

    Trả số cờ đã khôi phục.
    """
    if not previous_checklist:
        return 0
    # `spec.modules` là dataclass Module, không phải dict.
    modules = {str(getattr(m, "id", "") or ""): m for m in spec.modules}
    restored = 0
    for entry in previous_checklist.get("modules", []):
        if not isinstance(entry, dict):
            continue
        module = modules.get(str(entry.get("id") or ""))
        if module is None:
            continue
        flags = entry.get("flags") or {}
        values = flags.get("values") or {}
        sources = flags.get("sources") or {}
        for name, source in sources.items():
            if source != "user" or name not in values:
                continue
            module.flags.set(name, bool(values[name]), source="user")
            restored += 1
    return restored


def _run_inventory(args: argparse.Namespace) -> int:
    """Đọc canonical/spec.json, đánh giá 150 rule, ghi checklist."""
    import json as _json
    from pathlib import Path

    from .canonical import parse
    from .io import atomic_write
    from .match.engine import build_checklist, load_rules, match_spec
    from .state import (
        load_state,
        mark_stage,
        record_artifact,
        record_gate,
        save_state,
    )

    spec_path = _resolve(args.workspace, args.spec)
    if not spec_path.exists():
        print(f"[!] Không tìm thấy spec: {spec_path}", file=sys.stderr)
        print("    Chạy 'utd ingest' trước.", file=sys.stderr)
        return EXIT_INVALID_INPUT

    try:
        spec = parse(_json.loads(spec_path.read_text(encoding="utf-8")))
    except Exception as exc:
        print(f"[!] Không đọc được spec: {exc}", file=sys.stderr)
        return EXIT_INVALID_INPUT

    ruleset = load_rules()
    if ruleset.parse_errors:
        print(f"[!] {len(ruleset.parse_errors)} rule có trigger_condition ngoài ngôn ngữ:",
              file=sys.stderr)
        for rule_id, message in ruleset.parse_errors[:10]:
            print(f"    - {rule_id}: {message}", file=sys.stderr)
        return EXIT_GATE

    out = _resolve(args.workspace, args.out)

    # Nạp checklist cũ TRƯỚC khi đánh giá rule để cờ đã xác nhận được áp dụng.
    from .io import read_text
    from .match.reconcile_checklist import (
        added_question_ids,
        has_answered,
        reconcile_checklist,
    )

    previous_checklist = None
    if out.exists():
        try:
            previous_checklist = _json.loads(read_text(out))
        except Exception:
            previous_checklist = None

    restored = _restore_flags(spec, previous_checklist)

    report = match_spec(spec, ruleset)
    checklist = build_checklist(report, spec)

    reason = "cờ nghiệp vụ thay đổi làm rule không còn áp dụng"
    checklist = reconcile_checklist(previous_checklist, checklist, removed_reason=reason)

    atomic_write(out, _json.dumps(checklist, ensure_ascii=False, indent=2) + "\n")

    coverage = report.summary()
    print(f"[+] inventory: {coverage['total_rules']} rule -> "
          f"{coverage['matched']} áp dụng, {coverage['skipped']} bỏ qua có lý do")
    print(f"    {len(checklist['questions'])} câu hỏi "
          f"({coverage['critical']} CRITICAL / {coverage['standard']} STANDARD)")
    print(f"    reachability: {'150/150 OK' if report.coverage_ok else 'KHÔNG ĐẠT'}")

    new_ids = added_question_ids(previous_checklist, checklist)
    if new_ids and has_answered(previous_checklist):
        print(f"[!] {len(new_ids)} câu hỏi MỚI đã được thêm do cờ thay đổi.")
        print("    Xuất lại interview.html để thấy câu mới "
              "(câu đã trả lời giữ nguyên, không cần ký lại).")

    _print_expanded_warnings(previous_checklist, checklist)

    if not report.coverage_ok:
        print("[!] Reachability không đạt: có rule không được đánh giá", file=sys.stderr)
        return EXIT_GATE

    workspace = Path(args.workspace)
    state = load_state(workspace)
    record_artifact(workspace, state, "spec", spec_path)
    record_artifact(workspace, state, "checklist", out)
    record_gate(state, "reachability", True, [])
    mark_stage(workspace, state, "inventory")
    save_state(workspace, state)
    return EXIT_PASS


def _run_install_skill(args: argparse.Namespace) -> int:
    """Cài tài liệu skill vào thư mục cấu hình Claude Code."""
    from .install_skill import InstallError, install_skill

    try:
        result = install_skill(
            target=args.target,
            force=args.force,
            dry_run=args.dry_run,
        )
    except InstallError as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return exc.exit_code

    if result.dry_run:
        print(f"[*] install-skill (dry-run): sẽ ghi {len(result.written)} file vào "
              f"{result.target}")
        for rel in result.written:
            print(f"    {rel}")
        return EXIT_PASS

    print(f"[+] install-skill: đã cài {len(result.written)} file vào {result.target}")
    print("    Mở phiên Claude Code mới để nạp skill.")
    print(f"    Gỡ: rm -rf {result.target}")
    return EXIT_PASS


def _run_reconcile(args: argparse.Namespace) -> int:
    """Đối chiếu SSOT với findings do người đọc code điền."""
    from pathlib import Path

    from .reconcile import ReconcileError, reconcile_from_files
    from .state import load_state, mark_stage, record_artifact, save_state

    workspace = Path(args.workspace)
    ssot_path = _resolve(workspace, args.ssot)
    findings_path = _resolve(workspace, args.findings)

    if not ssot_path.exists():
        print(f"[!] Không tìm thấy SSOT: {ssot_path}", file=sys.stderr)
        return EXIT_INVALID_INPUT
    if not findings_path.exists():
        print(f"[!] Không tìm thấy findings: {findings_path}", file=sys.stderr)
        print("    Stage này cần người/LLM đọc mã nguồn rồi ghi findings.json.",
              file=sys.stderr)
        return EXIT_INVALID_INPUT

    try:
        target, summary = reconcile_from_files(
            ssot_path, findings_path, _resolve(workspace, args.out_dir)
        )
    except ReconcileError as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return exc.exit_code

    print(f"[+] reconcile: {summary['total_findings']} finding -> {target}")
    for category, count in summary["by_category"].items():
        print(f"    {category:16s} {count}")
    if summary["unclassified"]:
        print(f"    [!] {summary['unclassified']} rule chưa đối chiếu")

    state = load_state(workspace)
    record_artifact(workspace, state, "gap_report", target)
    mark_stage(workspace, state, "reconcile", source_access="read")
    save_state(workspace, state)
    return EXIT_PASS


def _flag_snapshot(checklist_path) -> str:
    """Chuỗi đại diện giá trị 6 cờ của mọi module — để phát hiện cờ đã đổi."""
    import json as _json

    from .io import read_text

    if not checklist_path.exists():
        return ""
    try:
        checklist = _json.loads(read_text(checklist_path))
    except Exception:
        return ""
    parts = []
    for module in checklist.get("modules", []):
        flags = (module.get("flags") or {}).get("values") or {}
        parts.append(
            f"{module.get('id')}:" + ",".join(
                f"{k}={int(bool(v))}" for k, v in sorted(flags.items())
            )
        )
    return "|".join(parts)


def _regenerate_after_flags(workspace, checklist_path) -> None:
    """Chạy lại đánh giá rule sau khi cờ thay đổi.

    Giữ nguyên checklist hiện có (append-merge), chỉ thêm câu mới cho rule vừa
    áp dụng. In cảnh báo nhắc xuất lại giao diện.
    """
    import json as _json

    from .canonical import parse
    from .io import atomic_write, read_text
    from .match.engine import build_checklist, load_rules, match_spec
    from .match.reconcile_checklist import (
        added_question_ids,
        reconcile_checklist,
    )

    spec_path = _resolve(workspace, ".unittest-design/canonical/spec.json")
    if not spec_path.exists():
        return

    from pathlib import Path

    spec = parse(_json.loads(read_text(spec_path)))
    previous = _json.loads(read_text(checklist_path))
    _restore_flags(spec, previous)

    report = match_spec(spec, load_rules())
    fresh = build_checklist(report, spec)
    merged = reconcile_checklist(
        previous, fresh, removed_reason="cờ nghiệp vụ thay đổi làm rule không còn áp dụng"
    )
    atomic_write(checklist_path, _json.dumps(merged, ensure_ascii=False, indent=2) + "\n")

    new_ids = added_question_ids(previous, merged)
    removed = merged.get("removed_questions") or []
    if new_ids or removed:
        print(f"[+] interview: sinh lại checklist — +{len(new_ids)} câu mới, "
              f"-{len(removed)} câu không còn áp dụng")
        if new_ids:
            print("    Xuất lại interview.html để thấy câu mới "
                  "(câu đã trả lời giữ nguyên, không cần ký lại).")

    _print_expanded_warnings(previous, merged)


def _run_interview(args: argparse.Namespace) -> int:
    """Xuất giao diện / áp câu trả lời / verify."""
    import json as _json
    from pathlib import Path

    from .interview.apply import (
        TamperError,
        apply_answers,
        apply_batch_consent,
        apply_chat_answer,
    )
    from .interview.export import export_html, export_ui_payload
    from .interview.verify import verify_file
    from .io import read_text
    from .state import (
        load_state,
        mark_stage,
        record_artifact,
        record_gate,
        save_state,
    )

    workspace = Path(args.workspace)
    checklist_path = _resolve(workspace, args.checklist)

    if not checklist_path.exists():
        print(f"[!] Không tìm thấy checklist: {checklist_path}", file=sys.stderr)
        print("    Chạy 'utd inventory' trước.", file=sys.stderr)
        return EXIT_INVALID_INPUT

    checklist = _json.loads(read_text(checklist_path))
    state = load_state(workspace)
    did_something = False

    if args.export_html:
        path = export_html(checklist, _resolve(workspace, args.export_html))
        print(f"[+] interview: giao diện -> {path}")
        record_artifact(workspace, state, "interview_html", path)
        did_something = True

    if args.export_ui:
        path = export_ui_payload(checklist, _resolve(workspace, args.export_ui))
        print(f"[+] interview: ui payload -> {path}")
        record_artifact(workspace, state, "ui_payload", path)
        did_something = True

    flags_before = _flag_snapshot(checklist_path)

    try:
        if args.apply_answers:
            result = apply_answers(checklist_path, _resolve(workspace, args.apply_answers))
            print(f"[+] interview: áp {result.applied} câu trả lời đã ký")
            if result.skipped_unknown:
                print(f"    bỏ qua {len(result.skipped_unknown)} mục không còn áp dụng: "
                      f"{', '.join(result.skipped_unknown[:5])}")
            did_something = True

        if args.answer_id:
            if not args.answer_value:
                print("[!] --answer-id cần --value", file=sys.stderr)
                return EXIT_INVALID_INPUT
            apply_chat_answer(checklist_path, args.answer_id, args.answer_value,
                              evidence=args.evidence or "")
            print(f"[+] interview: ghi câu trả lời chat cho {args.answer_id}")
            did_something = True

        if args.batch_consent:
            result = apply_batch_consent(checklist_path)
            print(f"[+] interview: batch-consent áp {result.applied} câu STANDARD")
            did_something = True
    except TamperError as exc:
        print(f"[!] Tampering detected:", file=sys.stderr)
        for problem in exc.problems:
            print(f"    - {problem}", file=sys.stderr)
        return EXIT_TAMPER

    # Cờ đã đổi -> sinh lại checklist (append-merge) để rule mới áp dụng sinh câu.
    if did_something and _flag_snapshot(checklist_path) != flags_before:
        _regenerate_after_flags(workspace, checklist_path)

    if args.verify:
        report = verify_file(checklist_path)
        print(f"[+] interview --verify: "
              f"{'PASSED' if report.passed else 'BLOCKED'}")
        print(f"    tổng {report.total} | trả lời {report.answered} | "
              f"chờ {report.pending}")
        if report.by_source:
            print(f"    nguồn: {report.by_source}")
        if report.tampered:
            for problem in report.tampered[:10]:
                print(f"    [!] {problem}", file=sys.stderr)
        record_gate(state, "interview", report.passed,
                    report.tampered + [f"{p['id']} PENDING" for p in report.pending_items[:5]])
        mark_stage(workspace, state, "interview")
        save_state(workspace, state)
        return EXIT_PASS if report.passed else report.exit_code

    if not did_something:
        print("[!] interview: cần một trong --export-html, --export-ui-payload, "
              "--apply, --answer-id, --batch-consent, --verify", file=sys.stderr)
        return EXIT_INVALID_INPUT

    save_state(workspace, state)
    return EXIT_PASS


def _run_lock(args: argparse.Namespace) -> int:
    """Khoá đặc tả sau sign-off."""
    from pathlib import Path

    from .lock import LockError, lock_spec
    from .state import load_state, mark_stage, record_artifact, save_state

    workspace = Path(args.workspace)
    try:
        result = lock_spec(
            _resolve(workspace, args.spec),
            _resolve(workspace, args.checklist),
            _resolve(workspace, args.verified),
            sign=args.sign,
            out_dir=_resolve(workspace, args.out_dir),
        )
    except LockError as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return exc.exit_code
    except FileNotFoundError as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return EXIT_INVALID_INPUT

    print(f"[+] lock: đã khoá đặc tả")
    print(f"    -> {result.locked_spec}")
    print(f"    sha256: {result.sha256}")

    state = load_state(workspace)
    record_artifact(workspace, state, "locked_spec", result.locked_spec)
    mark_stage(workspace, state, "lock")
    save_state(workspace, state)
    return EXIT_PASS


def _run_emit(args: argparse.Namespace) -> int:
    """Xuất .xlsx và .md từ SSOT; chặn nếu audit chưa pass hoặc SSOT đã đổi."""
    import json as _json
    from pathlib import Path

    from .emit.markdown import write_markdown
    from .emit.xlsx import write_xlsx
    from .io import read_text, sha256_file
    from .state import (
        HashMismatchError,
        load_state,
        mark_stage,
        record_artifact,
        require_artifacts,
        save_state,
    )

    workspace = Path(args.workspace)
    ssot_path = _resolve(args.workspace, args.ssot)
    audit_json = _resolve(args.workspace, args.audit_report)

    if not ssot_path.exists():
        print(f"[!] Không tìm thấy SSOT: {ssot_path}", file=sys.stderr)
        return EXIT_INVALID_INPUT

    if not audit_json.exists():
        print("[!] Chưa có audit report. Chạy 'utd audit' trước.", file=sys.stderr)
        return EXIT_GATE

    audit_data = _json.loads(read_text(audit_json))
    if not audit_data.get("passed"):
        print("[!] Audit chưa PASSED — không được emit.", file=sys.stderr)
        print(f"    {audit_data.get('total_issues', '?')} vi phạm. "
              f"Xem {audit_json.parent / 'report.md'}", file=sys.stderr)
        return EXIT_GATE

    state = load_state(workspace)
    try:
        require_artifacts(workspace, ["ssot"], state=state)
    except HashMismatchError as exc:
        print(f"[!] {exc}", file=sys.stderr)
        print("    SSOT đã bị sửa sau khi audit. Chạy lại 'utd audit'.", file=sys.stderr)
        return EXIT_HASH_MISMATCH

    ssot = _json.loads(read_text(ssot_path))
    written: list[Path] = []

    if args.xlsx:
        written.append(write_xlsx(ssot, _resolve(args.workspace, args.xlsx)))
    if args.md_dir:
        written.extend(write_markdown(ssot, _resolve(args.workspace, args.md_dir)))

    if not written:
        print("[!] Cần ít nhất --xlsx hoặc --md-dir", file=sys.stderr)
        return EXIT_INVALID_INPUT

    covered = len(ssot.get("uncovered_rules") or [])
    zero_normal = len(ssot.get("zero_normal_sheets") or [])
    print(f"[+] emit: {len(written)} file")
    for path in written:
        print(f"    -> {path}")
    print(f"    uncovered_rules: {covered} | zero_normal_sheets: {zero_normal}")

    for path in written:
        record_artifact(workspace, state, f"emit:{Path(path).name}", path)
    mark_stage(workspace, state, "emit")
    save_state(workspace, state)
    return EXIT_PASS


def _run_generate(args: argparse.Namespace) -> int:
    """Sinh SSOT từ locked_spec (hoặc spec đã qua interview nếu chưa khoá)."""
    import json as _json
    from pathlib import Path

    from .generate.ids import assign_ids
    from .generate.matrix import GenerateError, build_ssot, merge_module
    from .io import atomic_write, read_text
    from .lock import verify_lock
    from .state import (
        load_state,
        mark_stage,
        record_artifact,
        record_gate,
        save_state,
    )

    workspace = Path(args.workspace)
    source = _resolve(args.workspace, args.source)
    out_path = _resolve(args.workspace, args.out)

    if not source.exists():
        print(f"[!] Không tìm thấy spec: {source}", file=sys.stderr)
        print("    Chạy 'utd lock' (hoặc 'utd ingest') trước.", file=sys.stderr)
        return EXIT_INVALID_INPUT

    lock_file = source.with_name("lock.sha256")
    if lock_file.exists():
        problems = verify_lock(source, lock_file)
        if problems:
            for problem in problems:
                print(f"[!] {problem}", file=sys.stderr)
            print("    Chạy lại 'utd lock' sau khi xác nhận thay đổi.", file=sys.stderr)
            return EXIT_HASH_MISMATCH

    spec_data = _json.loads(read_text(source))

    from .canonical import parse
    from .generate.data import DataProvider

    spec = parse(spec_data)
    provider = DataProvider.load()

    try:
        if args.add_endpoint and out_path.exists():
            existing = _json.loads(read_text(out_path))
            new_spec = parse(_json.loads(read_text(args.add_endpoint)))
            new_ssot = build_ssot(new_spec, provider)
            for module in new_ssot["modules"]:
                merge_module(existing, module)
            assign_ids(existing["modules"])
            atomic_write(out_path, _json.dumps(existing, ensure_ascii=False, indent=2) + "\n")
            print(f"[+] generate --add-endpoint: +{len(new_ssot['modules'])} module "
                  f"-> {out_path}")
            record_artifact(workspace, state := load_state(workspace), "ssot", out_path)
            save_state(workspace, state)
            return EXIT_PASS

        ssot = build_ssot(spec, provider)
        assign_ids(ssot["modules"])
    except GenerateError as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return exc.exit_code

    uncovered = ssot.get("uncovered_rules") or []
    if uncovered:
        print(f"[!] {len(uncovered)} rule chưa có test case:", file=sys.stderr)
        for entry in uncovered[:20]:
            print(f"    - {entry}", file=sys.stderr)
        return EXIT_GATE

    atomic_write(out_path, _json.dumps(ssot, ensure_ascii=False, indent=2) + "\n")

    meta = ssot.get("meta", {})
    print(f"[+] generate: {meta.get('generated_modules', '?')} module, "
          f"{meta.get('total_cases', '?')} test case -> {out_path}")
    print(f"    uncovered_rules: 0 | zero_normal_sheets: 0")

    state = load_state(workspace)
    record_artifact(workspace, state, "ssot", out_path)
    record_gate(state, "generate", True, [])
    mark_stage(workspace, state, "generate")
    save_state(workspace, state)
    return EXIT_PASS


def _run_audit(args: argparse.Namespace) -> int:
    """Chạy 9 cổng trên SSOT, ghi report.json + report.md."""
    import json as _json
    from pathlib import Path

    from .audit.gates import audit_ssot
    from .audit.report import write_report
    from .io import read_text
    from .state import (
        load_state,
        mark_stage,
        record_artifact,
        record_gate,
        save_state,
    )

    ssot_path = _resolve(args.workspace, args.ssot)
    if not ssot_path.exists():
        print(f"[!] Không tìm thấy SSOT: {ssot_path}", file=sys.stderr)
        print("    Chạy 'utd generate' trước.", file=sys.stderr)
        return EXIT_INVALID_INPUT

    try:
        ssot = _json.loads(read_text(ssot_path))
    except Exception as exc:
        print(f"[!] Không đọc được SSOT: {exc}", file=sys.stderr)
        return EXIT_INVALID_INPUT

    workspace = Path(args.workspace)
    state = load_state(workspace)
    coverage = {}
    checklist_path = _resolve(args.workspace, args.checklist)
    if checklist_path.exists():
        checklist = _json.loads(read_text(checklist_path))
        coverage = checklist.get("coverage") or {}
        skipped = checklist.get("skipped_rules") or []
        unreasoned = [r for r in skipped if not str(r.get("skipped_reason") or "").strip()]
        coverage = dict(coverage)
        coverage["unaccounted"] = len(unreasoned)

    report = audit_ssot(ssot, coverage=coverage)

    out_dir = _resolve(args.workspace, args.out_dir)
    json_path, md_path = write_report(report, out_dir)

    print(f"[+] audit: {'PASSED' if report.passed else 'REJECTED'} — "
          f"{report.total_issues} vi phạm")
    for result in report.results:
        marker = "PASS" if result.passed else "FAIL"
        print(f"    {result.gate:3s} {marker}  {len(result.issues):3d} vi phạm")
    print(f"    -> {json_path}")
    print(f"    -> {md_path}")

    record_artifact(workspace, state, "ssot", ssot_path)
    record_artifact(workspace, state, "audit_report", json_path)
    record_gate(state, "audit", report.passed,
                [i.message for r in report.results for i in r.issues[:5]])
    mark_stage(workspace, state, "audit")
    save_state(workspace, state)

    return EXIT_PASS if report.passed else EXIT_GATE


def _run_ingest(args: argparse.Namespace) -> int:
    """Chuẩn hoá đầu vào về Canonical IR và ghi `canonical/spec.json`."""
    import json as _json
    from pathlib import Path

    from .canonical import validate
    from .ingest import IngestError, convert
    from .io import atomic_write

    if not args.source_kind:
        print("[!] ingest cần --from {openapi|swagger|utd-v1|draft}", file=sys.stderr)
        return EXIT_INVALID_INPUT
    if not args.input_path:
        print("[!] ingest cần --in <file>", file=sys.stderr)
        return EXIT_INVALID_INPUT

    path = Path(args.input_path)
    if not path.exists():
        print(f"[!] Không tìm thấy file đầu vào: {path}", file=sys.stderr)
        return EXIT_INVALID_INPUT

    try:
        if path.suffix.lower() in (".yaml", ".yml"):
            try:
                import yaml
            except ImportError:
                print("[!] Cần PyYAML để đọc file YAML", file=sys.stderr)
                return EXIT_INVALID_INPUT
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        else:
            data = _json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # cú pháp hỏng -> không phải lỗi cấu trúc IR
        print(f"[!] Không đọc được đầu vào: {exc}", file=sys.stderr)
        return EXIT_INVALID_INPUT

    try:
        spec = convert(args.source_kind, data)
    except IngestError as exc:
        print(f"[!] {exc}", file=sys.stderr)
        for detail in exc.details:
            print(f"    - {detail}", file=sys.stderr)
        return exc.exit_code
    except ValueError as exc:
        if args.source_kind == "draft":
            print(f"[!] {exc}", file=sys.stderr)
            return EXIT_INSUFFICIENT_INFO
        print(f"[!] Đầu vào không hợp lệ: {exc}", file=sys.stderr)
        return EXIT_INVALID_INPUT
    except Exception as exc:
        print(f"[!] Lỗi chuyển đổi: {exc}", file=sys.stderr)
        return EXIT_INVALID_INPUT

    result = validate(spec)
    if result.errors:
        print("[!] Canonical IR không hợp lệ:", file=sys.stderr)
        for error in result.errors:
            print(f"    - {error}", file=sys.stderr)
        return EXIT_INVALID_INPUT

    payload = _json.dumps(spec.to_dict(), ensure_ascii=False, indent=2) + "\n"
    out_path = _resolve(getattr(args, "workspace", "."), args.output_path)
    atomic_write(out_path, payload)

    print(f"[+] ingest {args.source_kind}: {len(spec.modules)} module, "
          f"{spec.endpoint_count()} endpoint -> {out_path}")
    if result.missing_info:
        print(f"[i] {len(result.missing_info)} thông tin cần hỏi người dùng:")
        for item in result.missing_info[:10]:
            print(f"    - {item}")
    return EXIT_PASS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="utd",
        description="Unit Test Designer v2 - thiết kế unit test theo đặc tả độc lập",
    )
    parser.add_argument("--version", action="version", version="utd 2.0.0")
    sub = parser.add_subparsers(dest="stage", metavar="<stage>")

    p_ingest = sub.add_parser("ingest", help="chuẩn hoá đầu vào về Canonical IR")
    p_ingest.add_argument("--from", dest="source_kind",
                          choices=["openapi", "swagger", "utd-v1", "draft"])
    p_ingest.add_argument("--in", dest="input_path")
    p_ingest.add_argument("--out", dest="output_path",
                          default=".unittest-design/canonical/spec.json")
    p_ingest.add_argument("--workspace", dest="workspace", default=".")

    p_inventory = sub.add_parser("inventory", help="sinh checklist phỏng vấn từ spec đã ingest")
    p_inventory.add_argument("--spec", dest="spec",
                             default=".unittest-design/canonical/spec.json")
    p_inventory.add_argument("--out", dest="out",
                             default=".unittest-design/interview/checklist.json")
    p_inventory.add_argument("--workspace", dest="workspace", default=".")
    p_interview = sub.add_parser("interview",
                                 help="xuất giao diện trả lời và ghi nhận câu trả lời")
    p_interview.add_argument("--checklist", dest="checklist",
                             default=".unittest-design/interview/checklist.json")
    p_interview.add_argument("--export-html", dest="export_html", default=None)
    p_interview.add_argument("--export-ui-payload", dest="export_ui", default=None)
    p_interview.add_argument("--apply", dest="apply_answers", default=None,
                             help="file answers.json do giao diện sinh")
    p_interview.add_argument("--answer-id", dest="answer_id", default=None)
    p_interview.add_argument("--value", dest="answer_value", default=None)
    p_interview.add_argument("--evidence", dest="evidence", default=None,
                             help="nguyên văn người dùng gửi (đường USER_CHAT)")
    p_interview.add_argument("--batch-consent", dest="batch_consent",
                             action="store_true")
    p_interview.add_argument("--verify", dest="verify", action="store_true")
    p_interview.add_argument("--workspace", dest="workspace", default=".")

    p_lock = sub.add_parser("lock", help="khoá đặc tả sau sign-off của người dùng")
    p_lock.add_argument("--sign", dest="sign", default="")
    p_lock.add_argument("--spec", dest="spec",
                        default=".unittest-design/canonical/spec.json")
    p_lock.add_argument("--checklist", dest="checklist",
                        default=".unittest-design/interview/checklist.json")
    p_lock.add_argument("--verified", dest="verified",
                        default=".unittest-design/interview/verified.json")
    p_lock.add_argument("--out-dir", dest="out_dir",
                        default=".unittest-design/canonical")
    p_lock.add_argument("--workspace", dest="workspace", default=".")
    p_generate = sub.add_parser("generate", help="sinh bộ test case cho mọi module")
    p_generate.add_argument("--source", dest="source",
                            default=".unittest-design/canonical/locked_spec.json")
    p_generate.add_argument("--out", dest="out",
                            default=".unittest-design/canonical/unit_test_spec.json")
    p_generate.add_argument("--add-endpoint", dest="add_endpoint", default=None)
    p_generate.add_argument("--workspace", dest="workspace", default=".")

    p_audit = sub.add_parser("audit", help="chạy 9 cổng kiểm toán kỹ thuật")
    p_audit.add_argument("--ssot", dest="ssot",
                         default=".unittest-design/canonical/unit_test_spec.json")
    p_audit.add_argument("--checklist", dest="checklist",
                         default=".unittest-design/interview/checklist.json")
    p_audit.add_argument("--out-dir", dest="out_dir",
                         default=".unittest-design/audit")
    p_audit.add_argument("--workspace", dest="workspace", default=".")
    p_emit = sub.add_parser("emit", help="xuất .xlsx và bộ .md từ SSOT")
    p_emit.add_argument("--ssot", dest="ssot",
                        default=".unittest-design/canonical/unit_test_spec.json")
    p_emit.add_argument("--xlsx", dest="xlsx", default=None)
    p_emit.add_argument("--md-dir", dest="md_dir", default=None)
    p_emit.add_argument("--audit-report", dest="audit_report",
                        default=".unittest-design/audit/report.json")
    p_emit.add_argument("--workspace", dest="workspace", default=".")
    p_reconcile = sub.add_parser("reconcile",
                                 help="đối chiếu đặc tả với mã nguồn (khi được yêu cầu)")
    p_reconcile.add_argument("--ssot", dest="ssot",
                             default=".unittest-design/canonical/unit_test_spec.json")
    p_reconcile.add_argument("--findings", dest="findings",
                             default=".unittest-design/reconcile/findings.json")
    p_reconcile.add_argument("--out-dir", dest="out_dir",
                             default=".unittest-design/reconcile")
    p_reconcile.add_argument("--workspace", dest="workspace", default=".")

    p_install = sub.add_parser(
        "install-skill", help="cài tài liệu skill vào ~/.claude/skills/"
    )
    p_install.add_argument("--target", dest="target", default=None,
                           help="thư mục đích (mặc định ~/.claude/skills/unit-test-designer)")
    p_install.add_argument("--force", dest="force", action="store_true",
                           help="ghi đè nếu thư mục đích đã tồn tại")
    p_install.add_argument("--dry-run", dest="dry_run", action="store_true",
                           help="liệt kê file sẽ ghi, không tạo file")
    return parser


def main(argv: list[str] | None = None) -> int:
    reconfigure_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.stage:
        parser.print_help()
        return EXIT_PASS
    if args.stage == "ingest":
        return _run_ingest(args)
    if args.stage == "inventory":
        return _run_inventory(args)
    if args.stage == "interview":
        return _run_interview(args)
    if args.stage == "lock":
        return _run_lock(args)
    if args.stage == "generate":
        return _run_generate(args)
    if args.stage == "audit":
        return _run_audit(args)
    if args.stage == "emit":
        return _run_emit(args)
    if args.stage == "reconcile":
        return _run_reconcile(args)
    if args.stage == "install-skill":
        return _run_install_skill(args)
    return _not_implemented(args.stage)


if __name__ == "__main__":
    sys.exit(main())
