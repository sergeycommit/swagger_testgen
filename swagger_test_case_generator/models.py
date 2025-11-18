"""
Data models used across the test case generator.
"""

from typing import Dict, List, Any
from datetime import datetime


class TestCase:
    """Represents a single generated test case."""

    def __init__(self, data: Dict[str, Any]):
        self.title = data.get("title", "Untitled Test Case")
        self.description = data.get("description", "")
        self.preconditions = data.get("preconditions", "")
        self.test_steps = data.get("test_steps", [])
        self.test_type = data.get("test_type", "Unknown")
        self.design_technique = data.get("design_technique", "Unknown")
        self.api_path = data.get("api_path", "")
        self.http_method = data.get("http_method", "")
        self.priority = data.get("priority", "Medium")
        self.created_date = datetime.now().isoformat()

    def to_csv_rows(self) -> List[Dict[str, str]]:
        """Convert the test case into CSV rows compatible with TestIT/TestOps."""
        rows = []
        for idx, step in enumerate(self.test_steps, 1):
            row = {
                "Title": self.title if idx == 1 else "",
                "Description": self.description if idx == 1 else "",
                "Preconditions": self.preconditions if idx == 1 else "",
                "Test Step #": str(idx),
                "Test Step Action": step.get("action", ""),
                "Test Step Expected Result": step.get("expected_result", ""),
                "Test Type": self.test_type,
                "Design Technique": self.design_technique,
                "API Path": self.api_path,
                "HTTP Method": self.http_method,
                "Priority": self.priority,
                "Created Date": self.created_date if idx == 1 else ""
            }
            rows.append(row)
        return rows

    def get_unique_key(self) -> str:
        """Return a unique key used for deduplication."""
        # Use the first step for uniqueness, when available
        first_step_action = ""
        first_step_result = ""
        if self.test_steps and len(self.test_steps) > 0:
            first_step = self.test_steps[0]
            first_step_action = first_step.get("action", "")[:100]  # First 100 chars
            first_step_result = first_step.get("expected_result", "")[:100]  # First 100 chars
        
        key_parts = [
            self.api_path,
            self.http_method,
            self.test_type,
            self.design_technique,
            self.title[:100].strip(),
            first_step_action.strip(),
            first_step_result.strip()
        ]
        return "|".join(key_parts)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dict ready for JSON export."""
        return {
            "title": self.title,
            "description": self.description,
            "preconditions": self.preconditions,
            "test_steps": self.test_steps,
            "test_type": self.test_type,
            "design_technique": self.design_technique,
            "api_path": self.api_path,
            "http_method": self.http_method,
            "priority": self.priority,
            "created_date": self.created_date
        }

