#!/usr/bin/env python3
"""Valida estructura, proveniencia y concordancia con el CR 26/84."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path


VARIABLE_TO_PDF_ROW = {
    "Real GDP (%)": "Real GDP",
    "Inflación promedio (%)": "Consumer price index (period average)",
    "Cuenta Corriente (% PIB)": "Current account balance",
    "Balance Fiscal NFPS (% PIB)": "Overall balance",
    "Deuda Pública (% PIB)": "Public debt 6/",
    "Precio Petróleo Ecuador (USD/bbl)": "Oil price Ecuador mix (US$ per barrel)",
    "PIB Nominal (USD mn)": "Nominal GDP (US$ million)",
    "Reservas Internacionales (USD mn)": "Gross international reserves (US$ million) 3/",
}


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_numbers(line: str, row_label: str) -> list[float]:
    payload = line[len(row_label) :]
    tokens = re.findall(r"-?\d[\d,]*(?:\.\d+)?", payload)
    return [float(token.replace(",", "")) for token in tokens]


def verify_cr26(root: Path, data: dict, manifest: dict, errors: list[str]) -> None:
    try:
        import pdfplumber
    except ImportError:
        errors.append("Falta pdfplumber; instala requirements.txt para verificar el CR 26/84.")
        return

    source = next((item for item in manifest["sources"] if item["vintage"] == "Abr-2026"), None)
    if not source:
        errors.append("El manifiesto no contiene la fuente Abr-2026.")
        return

    pdf_path = root / source["file"]
    with pdfplumber.open(pdf_path) as document:
        page = document.pages[source["tablePageIndex"]]
        text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""

    lines = text.splitlines()
    for variable, row_label in VARIABLE_TO_PDF_ROW.items():
        candidates = [line for line in lines if line.startswith(row_label)]
        if not candidates:
            errors.append(f"CR 26/84: no se encontró la fila '{row_label}'.")
            continue
        values = extract_numbers(candidates[0], row_label)
        if len(values) != 11:
            errors.append(
                f"CR 26/84: la fila '{row_label}' tiene {len(values)} valores; se esperaban 11."
            )
            continue

        current_actual = {2023: values[0], 2024: values[1], 2025: values[3]}
        current_forecast = dict(zip(range(2026, 2032), values[5:11]))
        for year, expected in current_actual.items():
            observed = float(data["actual"][variable][str(year)])
            if not math.isclose(observed, expected, abs_tol=1e-9):
                errors.append(
                    f"{variable} {year}: histórico/estimado={observed}, CR 26/84 corriente={expected}."
                )
        for year, expected in current_forecast.items():
            observed = float(data["vintages"]["Abr-2026"]["data"][variable][str(year)])
            if not math.isclose(observed, expected, abs_tol=1e-9):
                errors.append(
                    f"{variable} {year}: Abr-2026={observed}, CR 26/84 corriente={expected}."
                )


def validate_repository(root: Path, verify_pdf: bool = True) -> list[str]:
    errors: list[str] = []
    data = load_json(root / "forecasts.json")
    manifest = load_json(root / "data" / "source_manifest.json")

    meta = data.get("meta", {})
    actual = data.get("actual", {})
    vintages = data.get("vintages", {})
    variable_meta = meta.get("variables", {})
    variables = set(actual)

    if meta.get("schemaVersion") != 2:
        errors.append("forecasts.json debe usar schemaVersion=2.")
    if set(variable_meta) != variables:
        errors.append("meta.variables y actual no contienen exactamente las mismas variables.")
    if meta.get("latestVintage") not in vintages:
        errors.append("meta.latestVintage no existe en vintages.")

    expected_actual_years = list(range(2014, int(meta.get("actualThrough", 0)) + 1))
    for variable, series in actual.items():
        years = sorted(int(year) for year in series)
        if years != expected_actual_years:
            errors.append(f"{variable}: años históricos discontinuos o incompletos: {years}.")
        for year, value in series.items():
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                errors.append(f"{variable} {year}: valor histórico no numérico o no finito.")

    colors: set[str] = set()
    for name, vintage in vintages.items():
        color = vintage.get("color", "")
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            errors.append(f"{name}: color inválido '{color}'.")
        if color in colors:
            errors.append(f"{name}: color duplicado '{color}'.")
        colors.add(color)

        series_by_variable = vintage.get("data", {})
        if set(series_by_variable) != variables:
            missing = sorted(variables - set(series_by_variable))
            extra = sorted(set(series_by_variable) - variables)
            errors.append(f"{name}: variables faltantes={missing}, extra={extra}.")
            continue
        expected_years: list[int] | None = None
        for variable, series in series_by_variable.items():
            years = sorted(int(year) for year in series)
            contiguous = list(range(years[0], years[-1] + 1)) if years else []
            if years != contiguous:
                errors.append(f"{name}/{variable}: años de pronóstico discontinuos.")
            if years and years[0] != int(vintage["projStart"]):
                errors.append(f"{name}/{variable}: primer año distinto de projStart.")
            if expected_years is None:
                expected_years = years
            elif years != expected_years:
                errors.append(f"{name}/{variable}: rango distinto al resto del vintage.")
            for year, value in series.items():
                if not isinstance(value, (int, float)) or not math.isfinite(value):
                    errors.append(f"{name}/{variable}/{year}: valor no numérico o no finito.")

    manifest_sources = manifest.get("sources", [])
    source_vintages = {source.get("vintage") for source in manifest_sources}
    if source_vintages != set(vintages):
        errors.append("Los vintages del manifiesto no coinciden con forecasts.json.")

    actual_years_from_sources: list[int] = []
    for source in manifest_sources:
        path = root / source["file"]
        if not path.is_file():
            errors.append(f"Falta la fuente {source['file']}.")
            continue
        observed_hash = sha256(path)
        if observed_hash != source["sha256"]:
            errors.append(f"Hash inesperado para {source['file']}.")
        actual_years_from_sources.extend(source.get("actualYears", []))

    if sorted(actual_years_from_sources) != expected_actual_years:
        errors.append("actualYears del manifiesto no cubre una vez cada año histórico.")

    if verify_pdf:
        verify_cr26(root, data, manifest, errors)

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--skip-pdf", action="store_true", help="Omite el contraste de filas del CR 26/84.")
    args = parser.parse_args()

    errors = validate_repository(args.root.resolve(), verify_pdf=not args.skip_pdf)
    if errors:
        print("VALIDACIÓN FALLIDA")
        for error in errors:
            print(f"- {error}")
        return 1

    data = load_json(args.root / "forecasts.json")
    print(
        "VALIDACIÓN OK | "
        f"variables={len(data['actual'])} | vintages={len(data['vintages'])} | "
        f"histórico=2014-{data['meta']['actualThrough']} | "
        f"último={data['meta']['latestReport']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
