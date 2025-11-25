"""
Data models used across the test case generator.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


# =============================================================================
# Pydantic models for OpenAI Structured Outputs
# =============================================================================

class TestType(str, Enum):
    """Test case type enum."""
    POSITIVE = "Positive"
    NEGATIVE = "Negative"


class Priority(str, Enum):
    """Test case priority enum."""
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class DesignTechnique(str, Enum):
    """Test design technique enum."""
    EP = "EP"
    BVA = "BVA"
    ERROR_GUESSING = "Error Guessing"
    DECISION_TABLE = "Decision Table Testing"
    PAIRWISE = "Pairwise Testing"
    STATE_TRANSITION = "State Transition Testing"


class TestStepSchema(BaseModel):
    """Schema for a single test step."""
    action: str = Field(
        ...,
        description="The action to perform in this test step (e.g., 'Send GET request to /api/users with valid token')"
    )
    expected_result: str = Field(
        ...,
        description="The expected outcome of this action (e.g., 'Response status 200, body contains user list')"
    )


class TestCaseSchema(BaseModel):
    """Schema for a single test case - used for structured output validation."""
    title: str = Field(
        ...,
        description="Short descriptive name for the test case (include method, path, type, technique)"
    )
    description: str = Field(
        default="",
        description="Detailed explanation of what this test verifies"
    )
    preconditions: str = Field(
        default="",
        description="Setup required before executing this test"
    )
    test_type: TestType = Field(
        ...,
        description="Whether this is a Positive or Negative test case"
    )
    design_technique: DesignTechnique = Field(
        ...,
        description="The test design technique used"
    )
    api_path: str = Field(
        ...,
        description="The API resource path being tested"
    )
    http_method: str = Field(
        ...,
        description="HTTP method: GET, POST, PUT, PATCH, or DELETE"
    )
    priority: Priority = Field(
        default=Priority.MEDIUM,
        description="Test priority: High (critical path), Medium (important), Low (edge cases)"
    )
    test_steps: List[TestStepSchema] = Field(
        ...,
        min_length=1,
        description="List of test steps with actions and expected results"
    )


class TestCasesResponse(BaseModel):
    """Root schema for structured output - contains list of test cases."""
    test_cases: List[TestCaseSchema] = Field(
        ...,
        description="List of generated test cases"
    )


# =============================================================================
# Runtime TestCase class (for internal use and export)
# =============================================================================

class TestCase:
    """Represents a single generated test case."""

    def __init__(self, data: Dict[str, Any]):
        self.title = data.get("title", "Untitled Test Case")
        self.description = data.get("description", "")
        self.preconditions = data.get("preconditions", "")
        self.test_steps = self._normalize_test_steps(data.get("test_steps", []))
        self.test_type = self._normalize_enum(data.get("test_type", "Unknown"))
        self.design_technique = self._normalize_enum(data.get("design_technique", "Unknown"))
        self.api_path = data.get("api_path", "")
        self.http_method = data.get("http_method", "").upper()
        self.priority = self._normalize_enum(data.get("priority", "Medium"))
        self.created_date = datetime.now().isoformat()

    @staticmethod
    def _normalize_enum(value: Any) -> str:
        """Convert enum to string if needed."""
        if hasattr(value, 'value'):
            return value.value
        return str(value) if value else "Unknown"

    @staticmethod
    def _normalize_test_steps(steps: Any) -> List[Dict[str, str]]:
        """Normalize test steps from various formats."""
        if not steps:
            return []
        
        normalized = []
        for step in steps:
            if isinstance(step, dict):
                normalized.append({
                    "action": step.get("action", ""),
                    "expected_result": step.get("expected_result", "")
                })
            elif hasattr(step, 'action'):  # Pydantic model
                normalized.append({
                    "action": step.action,
                    "expected_result": step.expected_result
                })
        return normalized

    @classmethod
    def from_schema(cls, schema: TestCaseSchema) -> 'TestCase':
        """Create TestCase from Pydantic schema."""
        return cls(schema.model_dump())

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

