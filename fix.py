import pathlib
p = pathlib.Path('python_quant/reporting.py')
content = p.read_text(encoding='utf-8')

replacement = '''def _format_list_count(summary: dict[str, object], key: str) -> str:
    values = summary.get(key)
    if not isinstance(values, list):
        return "0"
    return str(len(values))


def _coerce_float(value: object) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return 0.0


def _format_optional_number(value: float | None, *, decimals: int = 2) -> str:
    return "-" if value is None else f"{value:,.{decimals}f}"


def _format_summary_pct(summary: dict[str, object], key: str) -> str:
    value = summary.get(key)
    if not isinstance(value, int | float):
        return "-"
    return f"{value:.2%}"


def _format_summary_bps(summary: dict[str, object], key: str) -> str:
    value = summary.get(key)
    if not isinstance(value, int | float):
        return "-"
    return f"{value:.2f} bps"


def _format_summary_money(summary: dict[str, object], key: str) -> str:
    value = summary.get(key)
    if not isinstance(value, int | float):
        return "-"
    return f"{value:,.2f}"


def _format_reconciliation_status(summary: dict[str, object]) -> str:
    value = summary.get("reconciled")
    if value is True:
        return "已对齐"
    if value is False:
        return "存在差异"
    return "-"


def _build_artifact_links(artifacts: dict[str, Path]) -> str:
    return "\\n".join(
        f'<li><a href="{escape(path.name)}">{escape(_display_label(name))}</a></li>'
        for name, path in artifacts.items()
    )


def _build_batch_chart_blocks(artifacts: dict[str, Path]) -> list[str]:
    chart_blocks: list[str] = []
    for key in ("batch_chart_svg", "batch_heatmap_svg"):
        if key in artifacts:
            chart_blocks.append(
                f'<div class="card"><h2>{escape(_display_label(key))}</h2><img src="{escape(artifacts[key].name)}" alt="{escape(_display_label(key))}" /></div>'
            )
    return chart_blocks


def _build_html_table_rows(rows: list[tuple[str, str]]) -> str:
    return "\\n".join(
        f"<tr><th>{escape(label)}</th><td>{escape(value)}</td></tr>"
        for label, value in rows
    )


def _sort_rows_by_metric(rows: list[dict[str, object]], rank_by: str) -> list[dict[str, object]]:
    return sorted(
        rows,
        key=lambda row: (
            _gate_rank_value(row),
            -_float_metric(row, "gate_failures", default=0.0),
            -_float_metric(row, "critical_warnings", default=0.0),
            -_float_metric(row, "health_warnings", default=0.0),
            _float_metric(row, rank_by, default=float("-inf")),
        ),
        reverse=True,
    )


def _gate_rank_value(row: dict[str, object]) -> float:
    gate_status = str(row.get("gate_status", "")).lower()
    if gate_status == "pass":
        return 1.0
    if gate_status == "":
        return 0.5
    return 0.0


def _validate_rank_metric(rows: list[dict[str, object]], rank_by: str) -> None:
    if not rows:
        return'''

new_content = content.replace('    if not rows:\n        return', replacement)

if 'def _format_list_count' in new_content:
    p.write_text(new_content, encoding='utf-8')
    print("Success")
else:
    print("Failed to replace")
