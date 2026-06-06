from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from python_quant.config import BacktestConfig
from python_quant.models import BacktestMetrics
from python_quant.reporting import save_performance_summary_json, save_run_manifest


class ReportingTests(unittest.TestCase):
    def test_saves_run_manifest_with_config_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            config = BacktestConfig(output_dir=output_dir)
            metrics = BacktestMetrics(
                total_return=0.1,
                annualized_return=0.2,
                max_drawdown=-0.05,
                volatility=0.15,
                downside_volatility=0.1,
                sharpe=1.2,
                sortino=1.5,
                calmar=4.0,
                win_rate=0.6,
                average_turnover=0.25,
                total_cost=123.45,
                periods=20,
            )
            summary_json_path = save_performance_summary_json(metrics, output_dir)

            manifest_path = save_run_manifest(
                output_dir=output_dir,
                config=config,
                inputs={"demo": True, "csv": None, "benchmark_csv": None, "config": None},
                artifacts={"performance_summary_json": summary_json_path},
                metrics=metrics,
            )

            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(True, payload["inputs"]["demo"])
            self.assertEqual(str(summary_json_path), payload["artifacts"]["performance_summary_json"])
            self.assertEqual(0.1, payload["metrics"]["total_return"])
            self.assertEqual(str(output_dir), payload["config"]["output_dir"])


if __name__ == "__main__":
    unittest.main()
