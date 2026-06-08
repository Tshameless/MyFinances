from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SMOKE_OUTPUT_DIR = PROJECT_ROOT / "output" / "dev_check_smoke"
SMOKE_ARTIFACTS = (
    "run_manifest.json",
    "config_effective.json",
    "config_sources.json",
    "report.html",
    "equity_curve.csv",
    "rolling_risk.csv",
    "rolling_risk.json",
    "factor_ic.csv",
    "factor_ic.json",
    "factor_group_returns.csv",
    "factor_group_returns.json",
    "factor_decay.csv",
    "factor_decay.json",
    "factor_correlation.csv",
    "factor_correlation.json",
    "suspension_analysis.csv",
    "suspension_daily.csv",
    "suspension_analysis.json",
    "turnover_analysis.csv",
    "holding_periods.csv",
    "turnover_analysis.json",
    "strategy_health.csv",
    "strategy_health_gates.csv",
    "strategy_health.json",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local quality gates for MyFinances.")
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip the demo CLI smoke run and artifact checks.",
    )
    parser.add_argument(
        "--skip-static",
        action="store_true",
        help="Skip ruff and mypy checks when dev dependencies are not installed.",
    )
    args = parser.parse_args(argv)

    commands = [
        ("unit tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests"]),
    ]
    if not args.skip_static:
        commands = [
            ("ruff", [sys.executable, "-m", "ruff", "check", "."]),
            ("mypy", [sys.executable, "-m", "mypy", "python_quant"]),
            *commands,
        ]
    for label, command in commands:
        _run(label, command)

    if not args.skip_smoke:
        _run_smoke()

    print("All development checks passed.")
    return 0


def _run(label: str, command: list[str]) -> None:
    print(f"==> {label}")
    completed = subprocess.run(command, cwd=PROJECT_ROOT)
    if completed.returncode == 0:
        return
    if label in {"ruff", "mypy"}:
        raise RuntimeError(
            f"{label} failed or is not installed. Install dev dependencies with "
            f"'{sys.executable} -m pip install -e .[dev]' or rerun with --skip-static."
        )
    raise subprocess.CalledProcessError(completed.returncode, command)


def _run_smoke() -> None:
    if SMOKE_OUTPUT_DIR.exists():
        shutil.rmtree(SMOKE_OUTPUT_DIR)
    _run(
        "demo smoke",
        [
            sys.executable,
            "-m",
            "python_quant.main",
            "--demo",
            "--output-dir",
            str(SMOKE_OUTPUT_DIR),
            "--top-n",
            "3",
            "--lookback-momentum",
            "3",
            "--lookback-mean-reversion",
            "2",
            "--lookback-volatility",
            "3",
            "--rolling-risk-window",
            "5",
            "--rebalance-days",
            "2",
        ],
    )
    missing = [name for name in SMOKE_ARTIFACTS if not (SMOKE_OUTPUT_DIR / name).exists()]
    if missing:
        missing_text = ", ".join(missing)
        raise RuntimeError(f"Smoke run did not write expected artifact(s): {missing_text}")
    manifest = json.loads((SMOKE_OUTPUT_DIR / "run_manifest.json").read_text(encoding="utf-8"))
    _check_manifest_artifacts(manifest)
    if manifest["config"]["rolling_risk_window"] != 5:
        raise RuntimeError("Smoke manifest did not preserve rolling_risk_window=5.")
    required_manifest_artifacts = (
        "rolling_risk_csv",
        "factor_ic_csv",
        "factor_ic_json",
        "factor_group_returns_csv",
        "factor_group_returns_json",
        "factor_decay_csv",
        "factor_decay_json",
        "factor_correlation_csv",
        "factor_correlation_json",
        "strategy_health_csv",
        "strategy_health_gates_csv",
        "config_effective_json",
        "config_sources_json",
        "suspension_analysis_csv",
        "suspension_daily_csv",
        "turnover_analysis_csv",
        "holding_periods_csv",
    )
    for artifact_key in required_manifest_artifacts:
        if artifact_key not in manifest["artifacts"]:
            raise RuntimeError(f"Smoke manifest is missing {artifact_key}.")


def _check_manifest_artifacts(manifest: dict[str, object]) -> None:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise RuntimeError("Smoke manifest has no artifact paths.")
    artifact_files = manifest.get("artifact_files")
    if not isinstance(artifact_files, dict):
        raise RuntimeError("Smoke manifest has no artifact file metadata.")

    missing_paths: list[str] = []
    missing_metadata: list[str] = []
    empty_files: list[str] = []
    for artifact_key, artifact_path in artifacts.items():
        path = Path(str(artifact_path))
        if not path.exists():
            missing_paths.append(str(artifact_key))
            continue
        if artifact_key not in artifact_files:
            missing_metadata.append(str(artifact_key))
        if path.is_file() and path.stat().st_size <= 0:
            empty_files.append(str(artifact_key))
    if missing_paths:
        raise RuntimeError(f"Smoke manifest points to missing artifact(s): {', '.join(missing_paths)}")
    if missing_metadata:
        raise RuntimeError(f"Smoke manifest is missing file metadata for: {', '.join(missing_metadata)}")
    if empty_files:
        raise RuntimeError(f"Smoke manifest points to empty artifact(s): {', '.join(empty_files)}")


if __name__ == "__main__":
    raise SystemExit(main())
