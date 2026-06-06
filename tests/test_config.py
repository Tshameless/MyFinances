from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from python_quant.config import load_config_overrides_from_toml


class ConfigTests(unittest.TestCase):
    def test_loads_toml_config_and_resolves_relative_output_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "backtest.toml"
            config_path.write_text(
                """
[backtest]
top_n = 5
price_field = "adjusted_close"
output_dir = "reports"

[backtest.factor_weights]
momentum = 0.7
low_volatility = 0.3
""".strip(),
                encoding="utf-8",
            )

            overrides = load_config_overrides_from_toml(config_path)

            self.assertEqual(5, overrides["top_n"])
            self.assertEqual("adjusted_close", overrides["price_field"])
            self.assertEqual((config_path.parent / "reports").resolve(), overrides["output_dir"])
            self.assertEqual(0.7, overrides["factor_weights"]["momentum"])


if __name__ == "__main__":
    unittest.main()
