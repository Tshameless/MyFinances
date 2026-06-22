import re
from pathlib import Path


def split_reporting():
    base_dir = Path(r"d:\file\MyFinances\python_quant")
    reporting_path = base_dir / "reporting.py"
    html_path = base_dir / "reporting_html.py"
    json_path = base_dir / "reporting_json.py"

    content = reporting_path.read_text(encoding="utf-8-sig")

    # Functions to move to JSON
    json_funcs = {
        "save_performance_summary_json", "save_run_manifest", "save_effective_config",
        "save_config_sources", "save_batch_summary", "save_batch_rankings",
        "_build_batch_export_headers", "_attach_batch_leaderboard_diagnostics",
        "_split_delimited_text", "_failed_gate_summary", "_recommended_parameter_match",
        "_build_batch_json_summary", "_build_ranked_batch_json_summary", "_build_best_run_json_summary",
        "_build_batch_export_row", "_build_batch_display_value", "_serialize_config",
        "_build_input_file_metadata", "_build_artifact_file_metadata", "_build_environment_metadata",
        "_build_git_metadata", "_run_git_command", "_file_metadata", "_sha256_file"
    }

    # Functions to move to HTML
    html_funcs = {
        "save_single_run_report_html", "save_batch_report_html", "save_walk_forward_report_html",
        "_build_batch_conclusion", "_report_base_css", "_build_walk_forward_conclusion",
        "_build_walk_forward_optimization_conclusion", "_build_walk_forward_summary_cards",
        "_build_walk_forward_optimization_summary_cards", "_build_walk_forward_observation_rows",
        "_build_walk_forward_optimization_observation_rows", "_build_walk_forward_chart_blocks",
        "_chart_points", "_count_chart_points", "_build_analysis_preview_rows",
        "_format_analysis_cell", "_format_count_map", "_format_degraded_parameter_sets",
        "_analysis_rows", "_analysis_summary_dict", "_build_batch_summary_cards",
        "_build_batch_parameter_rows", "_build_batch_observation_rows", "_recommended_match_rows",
        "_format_recommended_match_count", "_format_recommended_match_rate",
        "_format_best_recommended_match", "_format_metric_value", "_build_performance_summary_items",
        "_format_performance_summary_value", "_has_benchmark_metrics", "_build_single_run_metric_rows",
        "_build_single_run_review_rows", "_build_trading_behavior_rows", "_build_data_quality_rows",
        "_load_artifact_summary", "_format_summary_field", "_format_date_range", "_summary_float",
        "_format_summary_number", "_format_summary_bool", "_format_nested_summary_number",
        "_format_nested_summary_pct", "_format_factor_pair", "_format_list_first", "_format_list_count",
        "_coerce_float", "_format_optional_number", "_format_summary_pct", "_format_summary_bps",
        "_format_summary_money", "_format_reconciliation_status", "_build_artifact_links",
        "_build_batch_chart_blocks", "_build_html_table_rows", "_format_count_map_top",
        "_format_best_parameter_values", "_format_parameter_recommendation_rationale",
        "_format_parameter_recommendation_summary", "_format_recommendation_reason",
        "_format_recommended_action_first", "_format_recommendation_summary_text",
        "_format_recommended_action_text", "_build_report_conclusion", "_build_benchmark_conclusion",
        "_summary_card", "_build_rebalance_summary_rows", "_build_benchmark_summary_rows",
        "_format_pct", "_format_money", "_format_optional_date", "_format_optional_rate",
        "_format_optional_int", "_build_equity_curve_benchmark_columns", "_equity_curve_note",
        "_rebalance_note", "_format_holdings"
    }

    # Regex to match top level functions
    func_pattern = re.compile(r"^def\s+([A-Za-z0-9_]+)\s*\(", re.MULTILINE)

    matches = list(func_pattern.finditer(content))

    json_code = []
    html_code = []
    core_code = []

    # Imports for JSON
    json_code.append("from __future__ import annotations\n\nimport csv\nimport hashlib\nimport json\nimport platform\nimport subprocess\nimport sys\nfrom dataclasses import asdict\nfrom datetime import datetime\nfrom pathlib import Path\n\nfrom .config import BacktestConfig\nfrom .models import BacktestMetrics\nfrom .reporting_labels import display_label\nfrom .reporting_rank import float_metric\n\n_HUMAN_READABLE_ENCODING = \"utf-8-sig\"\n")

    # Imports for HTML
    html_code.append("from __future__ import annotations\n\nimport json\nfrom datetime import datetime\nfrom html import escape\nfrom pathlib import Path\n\nfrom .config import BacktestConfig\nfrom .models import BacktestMetrics, BenchmarkPoint, EquityPoint, RebalanceRecord\nfrom .reporting_labels import chinese_label, display_label, format_symbol, metric_explanation\nfrom .reporting_rank import float_metric, sort_rows_by_metric, validate_rank_metric\nfrom .reporting_svg import build_bar_chart_svg\n\n_HUMAN_READABLE_ENCODING = \"utf-8-sig\"\n")

    for i, match in enumerate(matches):
        func_name = match.group(1)
        start_idx = match.start()
        end_idx = matches[i+1].start() if i+1 < len(matches) else len(content)

        # If it's the very first function, grab the header (imports, globals) for core
        if i == 0:
            core_code.append(content[:start_idx])

        func_body = content[start_idx:end_idx]

        if func_name in json_funcs:
            json_code.append(func_body)
        elif func_name in html_funcs:
            html_code.append(func_body)
        else:
            core_code.append(func_body)

    # Modify core code imports
    core_text = "".join(core_code)

    new_imports = """
from .reporting_json import (
    save_performance_summary_json,
    save_run_manifest,
    save_effective_config,
    save_config_sources,
    save_batch_summary,
    save_batch_rankings,
)
from .reporting_html import (
    save_single_run_report_html,
    save_batch_report_html,
    save_walk_forward_report_html,
)
"""
    # Insert new imports after from .reporting_svg import ...
    core_text = core_text.replace(
        "from .reporting_svg import (\n    build_bar_chart_svg,\n    build_heatmap_svg,\n    build_line_chart_svg,\n)",
        "from .reporting_svg import (\n    build_bar_chart_svg,\n    build_heatmap_svg,\n    build_line_chart_svg,\n)" + new_imports
    )

    html_path.write_text("".join(html_code), encoding="utf-8-sig")
    json_path.write_text("".join(json_code), encoding="utf-8-sig")
    reporting_path.write_text(core_text, encoding="utf-8-sig")
    print("Successfully extracted reporting_html.py and reporting_json.py!")

if __name__ == "__main__":
    split_reporting()
