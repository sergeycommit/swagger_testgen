"""
Swagger Test Case Generator - Modular edition.
Automated generation of API test cases from Swagger/OpenAPI specifications.
"""

__version__ = "1.0.0"
__author__ = "Test Case Generator"

from .parser import SwaggerParser
from .generator import LLMTestCaseGenerator
from .exporter import CSVExporter, JSONExporter
from .config import Config
from .models import TestCase
from .utils import setup_logging, validate_test_case

__all__ = [
    "SwaggerParser",
    "LLMTestCaseGenerator",
    "CSVExporter",
    "JSONExporter",
    "Config",
    "TestCase",
    "setup_logging",
    "validate_test_case"
]

