"""
Unit tests for the Swagger Test Case Generator.
"""

import pytest
import json


class TestJSONParsing:
    """Tests for JSON parsing strategies in generator.py"""
    
    def test_direct_parse_valid_json(self):
        """Test direct JSON parsing with valid input."""
        from swagger_test_case_generator.generator import LLMTestCaseGenerator
        from swagger_test_case_generator.parser import SwaggerParser
        from swagger_test_case_generator.config import Config
        from unittest.mock import MagicMock
        
        # Create mock parser
        mock_parser = MagicMock(spec=SwaggerParser)
        mock_parser.spec = {}
        
        config = Config()
        generator = LLMTestCaseGenerator(mock_parser, config)
        
        valid_json = '{"test_cases": [{"title": "Test", "test_steps": [{"action": "do", "expected_result": "done"}], "test_type": "Positive", "api_path": "/test", "http_method": "GET"}]}'
        result = generator._try_direct_parse(valid_json)
        
        assert result is not None
        assert "test_cases" in result
        assert len(result["test_cases"]) == 1
    
    def test_direct_parse_invalid_json(self):
        """Test direct JSON parsing with invalid input."""
        from swagger_test_case_generator.generator import LLMTestCaseGenerator
        from swagger_test_case_generator.parser import SwaggerParser
        from swagger_test_case_generator.config import Config
        from unittest.mock import MagicMock
        
        mock_parser = MagicMock(spec=SwaggerParser)
        mock_parser.spec = {}
        
        config = Config()
        generator = LLMTestCaseGenerator(mock_parser, config)
        
        invalid_json = '{"test_cases": ['
        result = generator._try_direct_parse(invalid_json)
        
        assert result is None
    
    def test_extract_code_block(self):
        """Test extraction of JSON from markdown code blocks."""
        from swagger_test_case_generator.generator import LLMTestCaseGenerator
        from swagger_test_case_generator.parser import SwaggerParser
        from swagger_test_case_generator.config import Config
        from unittest.mock import MagicMock
        
        mock_parser = MagicMock(spec=SwaggerParser)
        mock_parser.spec = {}
        
        config = Config()
        generator = LLMTestCaseGenerator(mock_parser, config)
        
        markdown_json = '''Here is the response:
```json
{"test_cases": [{"title": "Test"}]}
```
'''
        result = generator._try_extract_code_block(markdown_json)
        
        assert result is not None
        assert "test_cases" in result
    
    def test_extract_array(self):
        """Test extraction of JSON array from response."""
        from swagger_test_case_generator.generator import LLMTestCaseGenerator
        from swagger_test_case_generator.parser import SwaggerParser
        from swagger_test_case_generator.config import Config
        from unittest.mock import MagicMock
        
        mock_parser = MagicMock(spec=SwaggerParser)
        mock_parser.spec = {}
        
        config = Config()
        generator = LLMTestCaseGenerator(mock_parser, config)
        
        array_response = 'Here are test cases: [{"title": "Test 1"}, {"title": "Test 2"}]'
        result = generator._try_extract_array(array_response)
        
        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 2
    
    def test_is_test_case_like(self):
        """Test detection of test case-like objects."""
        from swagger_test_case_generator.generator import LLMTestCaseGenerator
        from swagger_test_case_generator.parser import SwaggerParser
        from swagger_test_case_generator.config import Config
        from unittest.mock import MagicMock
        
        mock_parser = MagicMock(spec=SwaggerParser)
        mock_parser.spec = {}
        
        config = Config()
        generator = LLMTestCaseGenerator(mock_parser, config)
        
        # Valid test case structure
        valid_case = {
            "title": "Test",
            "test_steps": [{"action": "do"}],
            "test_type": "Positive",
            "api_path": "/test",
            "http_method": "GET"
        }
        assert generator._is_test_case_like(valid_case) is True
        
        # Invalid structure - missing required keys
        invalid_case = {"name": "something", "value": 123}
        assert generator._is_test_case_like(invalid_case) is False


class TestParserRefResolution:
    """Tests for $ref resolution in parser.py"""
    
    def test_resolve_local_ref(self):
        """Test resolution of local $ref pointers."""
        from swagger_test_case_generator.parser import SwaggerParser
        from unittest.mock import patch, MagicMock
        
        # Mock the file loading
        mock_spec = {
            "swagger": "2.0",
            "info": {"title": "Test API", "version": "1.0"},
            "paths": {},
            "definitions": {
                "User": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string"}
                    }
                }
            }
        }
        
        # Patch __init__ to avoid file loading
        with patch.object(SwaggerParser, '__init__', lambda self, x: None):
            parser = SwaggerParser("dummy.json")
            parser.spec = mock_spec
            parser.spec_path = "dummy.json"
            parser.spec_version = "swagger2"
        
        # Resolve the User definition
        result = parser.resolve_ref("#/definitions/User")
        
        assert result is not None
        assert result["type"] == "object"
        assert "id" in result["properties"]
        assert "name" in result["properties"]
    
    def test_resolve_nested_ref(self):
        """Test resolution of nested $ref pointers."""
        from swagger_test_case_generator.parser import SwaggerParser
        from unittest.mock import patch
        
        mock_spec = {
            "swagger": "2.0",
            "info": {"title": "Test API", "version": "1.0"},
            "paths": {},
            "definitions": {
                "Order": {
                    "type": "object",
                    "properties": {
                        "user": {"$ref": "#/definitions/User"}
                    }
                },
                "User": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"}
                    }
                }
            }
        }
        
        # Patch __init__ to avoid file loading
        with patch.object(SwaggerParser, '__init__', lambda self, x: None):
            parser = SwaggerParser("dummy.json")
            parser.spec = mock_spec
            parser.spec_path = "dummy.json"
            parser.spec_version = "swagger2"
        
        # Resolve with recursive resolution
        order_def = parser.resolve_ref("#/definitions/Order")
        resolved = parser.resolve_refs_recursive(order_def)
        
        assert resolved is not None
        assert "properties" in resolved
        # User ref should be resolved
        user_prop = resolved["properties"]["user"]
        assert "properties" in user_prop
        assert "name" in user_prop["properties"]


class TestTestCaseModel:
    """Tests for TestCase model in models.py"""
    
    def test_get_unique_key(self):
        """Test unique key generation for deduplication."""
        from swagger_test_case_generator.models import TestCase
        
        case1_data = {
            "title": "Test Case 1",
            "description": "Description",
            "test_type": "Positive",
            "api_path": "/users",
            "http_method": "GET",
            "test_steps": [{"action": "Call API", "expected_result": "200 OK"}],
            "design_technique": "EP"
        }
        
        case2_data = {
            "title": "Test Case 1",  # Same title
            "description": "Different description",
            "test_type": "Positive",
            "api_path": "/users",
            "http_method": "GET",
            "test_steps": [{"action": "Call API", "expected_result": "200 OK"}],  # Same steps
            "design_technique": "EP"
        }
        
        case3_data = {
            "title": "Test Case 1",
            "description": "Description",
            "test_type": "Negative",  # Different type
            "api_path": "/users",
            "http_method": "GET",
            "test_steps": [{"action": "Call API", "expected_result": "400 Error"}],  # Different result
            "design_technique": "EP"
        }
        
        case1 = TestCase(case1_data)
        case2 = TestCase(case2_data)
        case3 = TestCase(case3_data)
        
        # case1 and case2 should have same key (duplicates)
        assert case1.get_unique_key() == case2.get_unique_key()
        
        # case3 should have different key
        assert case1.get_unique_key() != case3.get_unique_key()
    
    def test_to_csv_rows(self):
        """Test CSV row generation."""
        from swagger_test_case_generator.models import TestCase
        
        case_data = {
            "title": "Multi-step Test",
            "description": "Test with multiple steps",
            "preconditions": "User logged in",
            "test_type": "Positive",
            "api_path": "/orders",
            "http_method": "POST",
            "priority": "High",
            "design_technique": "EP",
            "test_steps": [
                {"action": "Create order", "expected_result": "Order created"},
                {"action": "Verify order", "expected_result": "Order exists"}
            ]
        }
        
        case = TestCase(case_data)
        rows = case.to_csv_rows()
        
        # Should have 2 rows (one per step)
        assert len(rows) == 2
        
        # First row should have title
        assert rows[0]["Title"] == "Multi-step Test"
        assert rows[0]["Test Step #"] == "1"
        assert rows[0]["Test Step Action"] == "Create order"
        
        # Second row should have empty title (only shown once)
        assert rows[1]["Title"] == ""
        assert rows[1]["Test Step #"] == "2"
        assert rows[1]["Test Step Action"] == "Verify order"
    
    def test_normalize_test_steps(self):
        """Test normalization of various step formats."""
        from swagger_test_case_generator.models import TestCase
        
        # Test with dict steps
        case_data = {
            "title": "Test",
            "test_type": "Positive",
            "api_path": "/test",
            "http_method": "GET",
            "test_steps": [
                {"action": "Step 1", "expected_result": "Result 1"},
                {"action": "Step 2"}  # Missing expected_result
            ]
        }
        
        case = TestCase(case_data)
        
        assert len(case.test_steps) == 2
        assert case.test_steps[0]["action"] == "Step 1"
        assert case.test_steps[0]["expected_result"] == "Result 1"
        assert case.test_steps[1]["action"] == "Step 2"
        assert case.test_steps[1]["expected_result"] == ""  # Should default to empty


class TestConfigLoading:
    """Tests for configuration loading."""
    
    def test_default_config(self):
        """Test that defaults are loaded correctly."""
        from swagger_test_case_generator.config import Config
        
        config = Config()
        
        assert config.llm_model == "openai/gpt-4o-mini"
        assert config.llm_temperature == 0.7
        assert config.llm_max_tokens == 16000
        assert config.request_timeout == 60
        assert config.enable_deduplication is True
        assert config.use_streaming is True
    
    def test_structured_output_models_in_config(self):
        """Test that structured output models are accessible."""
        from swagger_test_case_generator.config import Config
        
        config = Config()
        models = config.structured_output_models
        
        assert isinstance(models, list)
        assert "gpt-4o" in models
        assert "openai/gpt-4o-mini" in models
    
    def test_get_nested_config(self):
        """Test getting nested config values."""
        from swagger_test_case_generator.config import Config
        
        config = Config()
        
        # Test dot-path access
        assert config.get("llm.model") == "openai/gpt-4o-mini"
        assert config.get("generation.enable_deduplication") is True
        assert config.get("nonexistent.path", "default") == "default"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
