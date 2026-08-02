from __future__ import annotations

import json
import unittest
from html.parser import HTMLParser
from pathlib import Path

from scripts.validate_data import validate_repository


ROOT = Path(__file__).resolve().parents[1]


class DocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.scripts: list[str] = []
        self.stylesheets: list[str] = []
        self.lang: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "html":
            self.lang = attributes.get("lang")
        if attributes.get("id"):
            self.ids.add(attributes["id"] or "")
        if tag == "script" and attributes.get("src"):
            self.scripts.append(attributes["src"] or "")
        if tag == "link" and attributes.get("rel") == "stylesheet":
            self.stylesheets.append(attributes.get("href") or "")


class DataContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads((ROOT / "forecasts.json").read_text(encoding="utf-8"))
        cls.manifest = json.loads(
            (ROOT / "data" / "source_manifest.json").read_text(encoding="utf-8")
        )

    def test_repository_contract_and_source_hashes(self) -> None:
        self.assertEqual(validate_repository(ROOT, verify_pdf=False), [])

    def test_latest_release_is_internally_consistent(self) -> None:
        meta = self.data["meta"]
        latest = meta["latestVintage"]
        source = next(item for item in self.manifest["sources"] if item["vintage"] == latest)
        self.assertEqual(latest, "Abr-2026")
        self.assertEqual(meta["latestReport"], source["report"])
        self.assertTrue(meta["updatedAt"].startswith(source["publicationDate"]))
        self.assertEqual(self.data["actual"]["Real GDP (%)"]["2025"], 3.7)
        self.assertEqual(self.data["vintages"][latest]["data"]["Real GDP (%)"]["2026"], 2.5)

    def test_eight_variables_and_seven_vintages(self) -> None:
        self.assertEqual(len(self.data["actual"]), 8)
        self.assertEqual(len(self.data["vintages"]), 7)

    def test_current_report_table_matches_canonical_data(self) -> None:
        self.assertEqual(validate_repository(ROOT, verify_pdf=True), [])


class StaticApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        cls.parser = DocumentParser()
        cls.parser.feed(cls.html)

    def test_frontend_assets_and_chart_plugins_are_loaded(self) -> None:
        self.assertEqual(self.parser.lang, "es")
        self.assertIn("styles.css", self.parser.stylesheets)
        self.assertIn("app.js", self.parser.scripts)
        self.assertTrue(any("Chart.js/4.4.1" in src for src in self.parser.scripts))
        self.assertTrue(any("chartjs-plugin-annotation/3.1.0" in src for src in self.parser.scripts))

    def test_every_cached_dom_id_exists(self) -> None:
        required = {
            "releaseReport", "releaseDate", "varSelect", "vintageToggles", "btnAll",
            "btnNone", "btnReset", "btnCsv", "btnDownload", "btnShare", "mainChart",
            "chartSubtitle", "accuracyTableContainer", "dataTableContainer",
            "methodologyText", "sourceList", "kpiActual", "kpiActualNote",
            "kpiLatestForecast", "kpiLatestForecastNote", "kpiRevision",
            "kpiRevisionNote", "kpiMae", "kpiMaeNote", "toast", "main",
        }
        self.assertEqual(required - self.parser.ids, set())

    def test_javascript_loads_both_canonical_files(self) -> None:
        self.assertIn('fetch("forecasts.json"', self.javascript)
        self.assertIn('fetch("data/source_manifest.json"', self.javascript)
        self.assertNotIn("canÃ", self.javascript)
        self.assertNotIn("histÃ", self.javascript)


if __name__ == "__main__":
    unittest.main()
