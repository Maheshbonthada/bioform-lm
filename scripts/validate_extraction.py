#!/usr/bin/env python3
"""
Validate extracted formulations before merging into BioFormBench.
Checks for unit consistency, plausible ranges, and data quality.
"""

import csv
import json
import sys
from pathlib import Path
from typing import List, Dict, Tuple


class ValidationError:
    def __init__(self, row_num: int, column: str, value, message: str):
        self.row_num = row_num
        self.column = column
        self.value = value
        self.message = message

    def __str__(self):
        return f"Row {self.row_num} ({self.column}): {self.message} [got: {self.value}]"


def validate_bioformbench_row(row: Dict, row_num: int) -> List[ValidationError]:
    """
    Validate a single BioFormBench row against expected ranges and constraints.
    Returns list of errors (empty = valid).
    """
    errors = []

    # ========================================================================
    # PROTEIN FIELDS
    # ========================================================================
    try:
        mw = float(row.get("protein_mw_kda", 0))
        if mw <= 0 or mw > 300:
            errors.append(ValidationError(
                row_num, "protein_mw_kda", mw,
                f"Out of range [1-300 kDa]. Got {mw}"
            ))
    except (ValueError, TypeError):
        errors.append(ValidationError(
            row_num, "protein_mw_kda", row.get("protein_mw_kda"),
            "Not a number"
        ))

    if row.get("protein_pi"):
        try:
            pi = float(row["protein_pi"])
            if pi < 3.0 or pi > 10.0:
                errors.append(ValidationError(
                    row_num, "protein_pi", pi,
                    f"Out of range [3.0-10.0 pI]. Got {pi}"
                ))
        except ValueError:
            errors.append(ValidationError(
                row_num, "protein_pi", row["protein_pi"],
                "Not a number"
            ))

    if row.get("protein_tm_baseline_c"):
        try:
            tm = float(row["protein_tm_baseline_c"])
            if tm < 30 or tm > 90:
                errors.append(ValidationError(
                    row_num, "protein_tm_baseline_c", tm,
                    f"Out of range [30-90 °C]. Got {tm}"
                ))
        except ValueError:
            errors.append(ValidationError(
                row_num, "protein_tm_baseline_c", row["protein_tm_baseline_c"],
                "Not a number"
            ))

    # ========================================================================
    # FORMULATION FIELDS
    # ========================================================================
    try:
        ph = float(row.get("ph", 0))
        if ph < 2.5 or ph > 9.0:
            errors.append(ValidationError(
                row_num, "ph", ph,
                f"Out of range [2.5-9.0]. Got {ph}"
            ))
    except (ValueError, TypeError):
        errors.append(ValidationError(
            row_num, "ph", row.get("ph"),
            "Not a number"
        ))

    try:
        ion_str = float(row.get("ionic_strength_mm", 0))
        if ion_str < 0 or ion_str > 500:
            errors.append(ValidationError(
                row_num, "ionic_strength_mm", ion_str,
                f"Out of range [0-500 mM]. Got {ion_str}"
            ))
    except (ValueError, TypeError):
        errors.append(ValidationError(
            row_num, "ionic_strength_mm", row.get("ionic_strength_mm"),
            "Not a number"
        ))

    try:
        buffer_conc = float(row.get("buffer_conc_mm", 0))
        if buffer_conc < 0 or buffer_conc > 200:
            errors.append(ValidationError(
                row_num, "buffer_conc_mm", buffer_conc,
                f"Out of range [0-200 mM]. Got {buffer_conc}"
            ))
    except (ValueError, TypeError):
        errors.append(ValidationError(
            row_num, "buffer_conc_mm", row.get("buffer_conc_mm"),
            "Not a number"
        ))

    # ========================================================================
    # STABILIZERS (JSON)
    # ========================================================================
    stab_json = row.get("stabilizers_json", "{}")
    try:
        if isinstance(stab_json, str):
            stabilizers = json.loads(stab_json)
        else:
            stabilizers = stab_json

        if not isinstance(stabilizers, dict):
            errors.append(ValidationError(
                row_num, "stabilizers_json", stab_json,
                "Not a dictionary"
            ))
        else:
            # Check individual stabilizer concentrations
            for stab_name, stab_conc in stabilizers.items():
                try:
                    conc = float(stab_conc)
                    # Heuristic check: most biologics stabilizers 1-1000 mM
                    if conc < 0 or conc > 2000:
                        errors.append(ValidationError(
                            row_num, f"stabilizers_json[{stab_name}]", conc,
                            f"Out of plausible range [0-2000 mM]. Got {conc}"
                        ))
                except (ValueError, TypeError):
                    errors.append(ValidationError(
                        row_num, f"stabilizers_json[{stab_name}]", stab_conc,
                        "Concentration not a number"
                    ))
    except json.JSONDecodeError as e:
        errors.append(ValidationError(
            row_num, "stabilizers_json", stab_json,
            f"Invalid JSON: {e}"
        ))

    # ========================================================================
    # TEMPERATURE
    # ========================================================================
    try:
        temp = float(row.get("temperature_c", 0))
        if temp < -20 or temp > 50:
            errors.append(ValidationError(
                row_num, "temperature_c", temp,
                f"Out of range [-20 to 50 °C]. Got {temp}"
            ))
    except (ValueError, TypeError):
        errors.append(ValidationError(
            row_num, "temperature_c", row.get("temperature_c"),
            "Not a number"
        ))

    # ========================================================================
    # OUTCOME FIELDS
    # ========================================================================
    if row.get("measured_aggregation_percent"):
        try:
            agg = float(row["measured_aggregation_percent"])
            if agg < 0 or agg > 100:
                errors.append(ValidationError(
                    row_num, "measured_aggregation_percent", agg,
                    f"Out of range [0-100%]. Got {agg}"
                ))
        except (ValueError, TypeError):
            errors.append(ValidationError(
                row_num, "measured_aggregation_percent",
                row["measured_aggregation_percent"],
                "Not a number"
            ))

    if row.get("measured_tm_shift_c"):
        try:
            tm_shift = float(row["measured_tm_shift_c"])
            if tm_shift < -10 or tm_shift > 30:
                errors.append(ValidationError(
                    row_num, "measured_tm_shift_c", tm_shift,
                    f"Out of range [-10 to +30 °C]. Got {tm_shift}"
                ))
        except (ValueError, TypeError):
            errors.append(ValidationError(
                row_num, "measured_tm_shift_c", row["measured_tm_shift_c"],
                "Not a number"
            ))

    if row.get("stability_score"):
        try:
            score = float(row["stability_score"])
            if score < 0 or score > 1:
                errors.append(ValidationError(
                    row_num, "stability_score", score,
                    f"Out of range [0-1]. Got {score}"
                ))
        except (ValueError, TypeError):
            errors.append(ValidationError(
                row_num, "stability_score", row["stability_score"],
                "Not a number"
            ))

    return errors


def validate_file(csv_path: str) -> Tuple[int, int, List[ValidationError]]:
    """
    Validate entire CSV file.
    Returns: (num_rows, num_errors, list_of_errors)
    """
    all_errors = []
    row_count = 0

    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row_num, row in enumerate(reader, start=2):  # start at 2 (skip header)
                row_count += 1
                errors = validate_bioformbench_row(row, row_num)
                all_errors.extend(errors)
    except FileNotFoundError:
        print(f"❌ File not found: {csv_path}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        sys.exit(1)

    return row_count, len(all_errors), all_errors


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_extraction.py <csv_file> [<csv_file2> ...]")
        print()
        print("Example:")
        print("  python validate_extraction.py data/bioformbench_expanded.csv")
        sys.exit(1)

    csv_files = sys.argv[1:]

    print("=" * 80)
    print("BioFormBench Extraction Validation")
    print("=" * 80)
    print()

    total_rows = 0
    total_errors = 0
    all_errors_by_file = {}

    for csv_file in csv_files:
        print(f"Validating: {csv_file}")
        row_count, error_count, errors = validate_file(csv_file)
        total_rows += row_count
        total_errors += error_count
        all_errors_by_file[csv_file] = (row_count, error_count, errors)

        status = "✅ PASS" if error_count == 0 else f"❌ FAIL ({error_count} errors)"
        print(f"  {status} | {row_count} rows")
        print()

    # ========================================================================
    # SUMMARY & DETAILED ERRORS
    # ========================================================================
    print("=" * 80)
    print(f"SUMMARY: {total_rows} total rows, {total_errors} total errors")
    print("=" * 80)
    print()

    if total_errors == 0:
        print("✅ All validations passed! Ready to merge into BioFormBench.")
        print()
        print("Next step:")
        print("  cat data/bioformbench_expanded.csv >> data/bioformbench_seed.csv")
        print()
        return 0

    # Print errors by file
    for csv_file, (row_count, error_count, errors) in all_errors_by_file.items():
        if error_count > 0:
            print(f"\n{csv_file}: {error_count} errors")
            print("-" * 80)
            for error in errors:
                print(f"  {error}")
            print()

    print("=" * 80)
    print(f"❌ {total_errors} validation errors found. Fix before merging.")
    print("=" * 80)
    return 1


if __name__ == "__main__":
    sys.exit(main())
