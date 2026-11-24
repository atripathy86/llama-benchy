import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "plot_summary.py"
SAMPLE = ROOT / "schemas" / "sample.json"


class PlotSummaryTests(unittest.TestCase):
    def run_plot(self, input_path, output_dir):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(input_path), "--output-dir", str(output_dir)],
            capture_output=True, text=True,
        )

    def test_single_report_generates_throughput_and_latency(self):
        with TemporaryDirectory() as temp:
            output = Path(temp) / "plots"
            result = self.run_plot(SAMPLE, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Generated 2 graph(s)", result.stdout)
            self.assertEqual(
                {p.name for p in output.glob("*.png")},
                {"test-throughput.png", "test-latency.png"},
            )

    def test_summary_skips_failed_models(self):
        report = json.loads(SAMPLE.read_text(encoding="utf-8"))
        with TemporaryDirectory() as temp:
            root = Path(temp)
            summary = root / "summary.json"
            summary.write_text(json.dumps({"models": [
                {"model": "successful/model", "status": "ok", "report": report},
                {"model": "failed", "status": "failed", "report": report},
            ]}), encoding="utf-8")
            output = root / "plots"
            result = self.run_plot(summary, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                {p.name for p in output.glob("*.png")},
                {"successful_model-throughput.png", "successful_model-latency.png"},
            )

    def test_utf8_report_in_path_with_spaces(self):
        report = json.loads(SAMPLE.read_text(encoding="utf-8"))
        report["model"] = "model café"
        with TemporaryDirectory() as temp:
            root = Path(temp) / "path with spaces"
            root.mkdir()
            source = root / "report.json"
            source.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
            output = root / "plots with spaces"
            result = self.run_plot(source, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output / "model_caf-throughput.png").is_file())
            self.assertTrue((output / "model_caf-latency.png").is_file())

    def test_unrecognized_json_fails(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "invalid.json"
            source.write_text('{"benchmarks": []}', encoding="utf-8")
            result = self.run_plot(source, root / "plots")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("model and benchmarks list", result.stderr)


if __name__ == "__main__":
    unittest.main()
