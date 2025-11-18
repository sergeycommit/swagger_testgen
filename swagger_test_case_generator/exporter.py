"""
Export helpers for serializing generated test cases.
"""

import csv
import json
import logging
from typing import List
from .models import TestCase

logger = logging.getLogger(__name__)


class CSVExporter:
    """Export test cases into a CSV file compatible with TestIT/TestOps."""

    CSV_HEADERS = [
        "Title",
        "Description",
        "Preconditions",
        "Test Step #",
        "Test Step Action",
        "Test Step Expected Result",
        "Test Type",
        "Design Technique",
        "API Path",
        "HTTP Method",
        "Priority",
        "Created Date"
    ]

    @staticmethod
    def export(test_cases: List[TestCase], output_path: str, encoding: str = "utf-8"):
        """Export the provided test cases into a CSV file."""
        all_rows = []

        for test_case in test_cases:
            rows = test_case.to_csv_rows()
            all_rows.extend(rows)

        try:
            with open(output_path, 'w', newline='', encoding=encoding) as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=CSVExporter.CSV_HEADERS)
                writer.writeheader()
                writer.writerows(all_rows)

            logger.info(f"Test cases exported to CSV: {output_path}")
            logger.info(f"  Total test cases: {len(test_cases)}")
            logger.info(f"  Total CSV rows: {len(all_rows)}")

        except Exception as e:
            logger.error(f"CSV export failed: {e}")
            raise


class JSONExporter:
    """Export test cases as JSON."""

    @staticmethod
    def export(test_cases: List[TestCase], output_path: str, encoding: str = "utf-8", indent: int = 2):
        """Export the provided test cases into a JSON file."""
        try:
            data = {
                "metadata": {
                    "total_test_cases": len(test_cases),
                    "generated_at": test_cases[0].created_date if test_cases else None
                },
                "test_cases": [tc.to_dict() for tc in test_cases]
            }

            with open(output_path, 'w', encoding=encoding) as f:
                json.dump(data, f, ensure_ascii=False, indent=indent)

            logger.info(f"Test cases exported to JSON: {output_path}")
            logger.info(f"  Total test cases: {len(test_cases)}")

        except Exception as e:
            logger.error(f"JSON export failed: {e}")
            raise

