"""
LLM-powered test case generator (OpenRouter or local) with async parallelism.
"""

import json
import asyncio
import logging
from typing import Dict, List, Any, Set
from openai import AsyncOpenAI
from .models import TestCase
from .parser import SwaggerParser
from .config import Config
from .utils import validate_test_case

logger = logging.getLogger(__name__)


class LLMTestCaseGenerator:
    """Generate test cases with an LLM (OpenRouter or local) using parallel execution."""

    def __init__(self, swagger_parser: SwaggerParser, config: Config):
        self.parser = swagger_parser
        self.config = config
        self.client = AsyncOpenAI(
            api_key=config.llm_api_key,
            base_url=config.llm_base_url
        )
        self.test_cases: List[TestCase] = []
        self.http_methods = ["GET", "POST", "PUT", "PATCH", "DELETE"]
        self.seen_keys: Set[str] = set()  # used for deduplication
        self.lock = asyncio.Lock()  # keeps deduplication thread-safe

    async def generate_all_test_cases(self) -> List[TestCase]:
        """Generate test cases for every operation in the spec (optionally in parallel)."""
        paths = self.parser.get_paths()

        # Gather every operation to process
        operations = []
        for path, path_item in paths.items():
            # Apply path/method/tag filters
            if not self.config.should_process_path(path):
                continue

            for method in self.http_methods:
                if not self.config.should_process_method(method):
                    continue

                if method.lower() in path_item:
                    operation = self.parser.get_operation_details(path, method)
                    if operation:
                        # Filter by tags when configured
                        tags = operation.get('tags', [])
                        if not self.config.should_process_tag(tags):
                            continue

                        operations.append((path, method, operation))

        total_operations = len(operations)
        logger.info(f"Operations to process: {total_operations}")

        if total_operations == 0:
            logger.warning("No operations matched the filters")
            return []

        # Build a semaphore if concurrency should be capped
        max_concurrent = self.config.max_concurrent_requests
        if max_concurrent is None or max_concurrent == 0:
            logger.info("Parallel requests are unlimited—processing all operations at once")
            tasks = [
                self._generate_test_cases_for_operation(path, method, operation, idx + 1, total_operations)
                for idx, (path, method, operation) in enumerate(operations)
            ]
        else:
            logger.info(f"Parallel requests limited to: {max_concurrent}")
            semaphore = asyncio.Semaphore(max_concurrent)
            tasks = [
                self._generate_test_cases_for_operation_with_semaphore(
                    semaphore, path, method, operation, idx + 1, total_operations
                )
                for idx, (path, method, operation) in enumerate(operations)
            ]

        # Fire off all tasks
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(f"Total test cases generated: {len(self.test_cases)}")
        return self.test_cases

    async def _generate_test_cases_for_operation_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        path: str,
        method: str,
        operation: Dict[str, Any],
        current: int,
        total: int
    ):
        """Wrapper that respects a concurrency semaphore."""
        async with semaphore:
            await self._generate_test_cases_for_operation(path, method, operation, current, total)

    async def _generate_test_cases_for_operation(
        self,
        path: str,
        method: str,
        operation: Dict[str, Any],
        current: int = 0,
        total: int = 0
    ):
        """Generate test cases for a single operation via the LLM."""

        if current > 0:
            logger.info(f"Processing [{current}/{total}]: {method} {path}")

        # Keep only relevant schemas
        relevant_schemas = self.parser.get_relevant_schemas(operation)
        minimal_context = self.parser.get_minimal_context()

        # Compose compact payload
        operation_spec = {
            "path": path,
            "method": method,
            "operation": operation,
            "relevant_schemas": relevant_schemas,
            "api_context": minimal_context
        }

        operation_spec_json = json.dumps(operation_spec, indent=2, ensure_ascii=False)

        system_prompt = (
            "You are a senior QA engineer and test design expert. "
            "Analyze the provided API operation specification and produce the most thorough set of "
            "positive and negative test cases possible.\n\n"
            "Mission-critical requirements:\n"
            "- Cover EVERY scenario required for full validation; never limit the number of cases.\n"
            "- Apply EVERY classic test-design technique:\n"
            "  1. Equivalence Partitioning (EP) — valid vs. invalid classes per parameter\n"
            "  2. Boundary Value Analysis (BVA) — min, min+1, max-1, max, min-1, max+1\n"
            "  3. Error Guessing — common failures/security issues (SQLi, XSS, invalid tokens, missing auth)\n"
            "  4. Decision Table Testing — combinations of required/optional fields and logical rules\n"
            "  5. Pairwise Testing — ensure every pair of parameters is covered\n"
            "  6. State Transition Testing — valid/invalid transitions whenever applicable\n"
            "\n"
            "Detailed generation checklist:\n"
            "- Positive cases: baseline happy path, every enum value, boundary positives, cases with all optional fields.\n"
            "- Negative cases (FOR EVERY PARAMETER):\n"
            "  * Numeric: min-1, min, min+1, max-1, max, max+1, disallowed negatives/zeros, overflow values, floats when ints expected, wrong types.\n"
            "  * Strings: empty, null, shorter than minLength, longer than maxLength, special characters (< > & \" ' \\\\ /), SQL injection, XSS, command injection, path traversal, unicode edge cases.\n"
            "  * Enum: all valid values (positive) plus invalid/out-of-set values.\n"
            "  * Required fields missing individually and all missing at once.\n"
            "  * Wrong data types for each field.\n"
            "  * Invalid formats for email/URL/UUID/date-time/etc.\n"
            "  * Auth failures: missing token, invalid token, expired token, insufficient scopes.\n"
            "  * Resource state issues: non-existent IDs (404), deleted resources, conflicts (409), invalid transitions.\n"
            "\n"
            "Important: more cases with full coverage are preferred over fewer cases with gaps.\n"
            "\n"
            "Output format:\n"
            "Return a JSON array of objects with the following fields:\n"
            "{\n"
            '  "title": "Short name (include method, path, type, technique)",\n'
            '  "description": "Detailed explanation of what the test verifies",\n'
            '  "preconditions": "Setup required before the test",\n'
            '  "test_type": "Positive" or "Negative",\n'
            '  "design_technique": "EP" | "BVA" | "Error Guessing" | "Decision Table Testing" | "Pairwise Testing" | "State Transition Testing",\n'
            '  "api_path": "API resource path",\n'
            '  "http_method": "GET/POST/PUT/PATCH/DELETE",\n'
            '  "priority": "High" | "Medium" | "Low" with the meaning:\n'
            '    - High: baseline positives and critical negatives (auth, invalid data types)\n'
            '    - Medium: most boundary/validation/negative scenarios\n'
            '    - Low: rare combinations, edge cases, exploratory scenarios\n'
            '  "test_steps": [\n'
            '    {\n'
            '      "action": "Describe the action (e.g. send request with ...)",\n'
            '      "expected_result": "Expected HTTP status and body details"\n'
            '    }\n'
            '  ]\n'
            "}\n"
        )

        user_prompt = (
            "Generate the MOST COMPREHENSIVE set of test cases for the following API operation:\n\n"
            f"```json\n{operation_spec_json}\n```\n\n"
            "Critical rules:\n"
            "- Include every possible scenario (positive AND negative).\n"
            "- Apply every test-design technique to each parameter.\n"
            "- Do NOT limit the number of cases—coverage comes first.\n"
            "- For each parameter, create separate cases for each equivalence class.\n"
            "- For numeric parameters include every boundary value.\n"
            "- For string parameters include every invalid pattern/type.\n"
            "- Each case must be unique and focused on a single idea.\n"
            "- Avoid duplicates—each case must verify a distinct scenario.\n"
            "- Return a JSON array (starts with '[' and ends with ']').\n"
            "\n"
            "Prioritization guidance:\n"
            "- High: baseline positives, authorization/security, invalid data types.\n"
            "- Medium: most boundary, validation, and negative scenarios.\n"
            "- Low: rare combinations, edge cases, exploratory scenarios.\n"
            "Aim for approximately: High 20-30%, Medium 60-70%, Low 5-10%.\n"
            "\n"
            "Reminder: 50+ fully covered cases are better than 10 with gaps."
        )

        for attempt in range(self.config.max_retries):
            try:
                logger.debug(f"LLM request for {method} {path} (attempt {attempt + 1}/{self.config.max_retries})")
                
                response = await self.client.chat.completions.create(
                    model=self.config.llm_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=self.config.llm_temperature,
                    max_tokens=self.config.llm_max_tokens
                )

                json_string = response.choices[0].message.content
                generated_cases_data = self._parse_llm_response(json_string)

                if generated_cases_data:
                    valid_count = await self._process_generated_cases(generated_cases_data, path, method)
                    logger.info(f"Received {valid_count} valid cases for {method} {path}")
                    return
                else:
                    logger.warning(f"Failed to extract data from LLM response (attempt {attempt + 1})")
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(self.config.retry_delay * (attempt + 1))

            except Exception as e:
                logger.error(f"Error calling the LLM API for {method} {path}: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                else:
                    logger.error(f"Failed to generate test cases for {method} {path} after {self.config.max_retries} attempts")

    def _parse_llm_response(self, json_string: str) -> List[Dict[str, Any]]:
        """Parse the LLM response and extract a list of test cases."""
        try:
            raw_data = json.loads(json_string)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decoding error: {str(e)[:100]}")
            # Attempt to locate a JSON array within the response
            start_idx = json_string.find('[')
            end_idx = json_string.rfind(']') + 1
            if start_idx != -1 and end_idx > start_idx:
                try:
                    raw_data = json.loads(json_string[start_idx:end_idx])
                except:
                    logger.error("Unable to extract JSON array from the response")
                    return []
            else:
                return []

        # Normalize structure
        if isinstance(raw_data, dict):
            generated_cases_data = raw_data.get("test_cases", raw_data.get("cases", []))
        elif isinstance(raw_data, list):
            generated_cases_data = raw_data
        else:
            logger.error(f"Unexpected data format from LLM: {type(raw_data)}")
            return []

        return generated_cases_data if isinstance(generated_cases_data, list) else []

    async def _process_generated_cases(
        self,
        cases_data: List[Dict[str, Any]],
        path: str,
        method: str
    ) -> int:
        """Process generated cases with deduplication (thread-safe)."""
        valid_count = 0

        async with self.lock:  # Ensure deduplication is safe under concurrency
            for case_data in cases_data:
                if not isinstance(case_data, dict):
                    continue

                # Guarantee path and method are present
                case_data['api_path'] = case_data.get('api_path', path)
                case_data['http_method'] = case_data.get('http_method', method)

                test_case = TestCase(case_data)

                # Validate before storing
                if not validate_test_case(test_case):
                    logger.warning(f"Dropped invalid test case: {test_case.title}")
                    continue
                
                if not self.config.enable_deduplication:
                    self.test_cases.append(test_case)
                    valid_count += 1
                else:
                    unique_key = test_case.get_unique_key()
                    if unique_key not in self.seen_keys:
                        self.seen_keys.add(unique_key)
                        self.test_cases.append(test_case)
                        valid_count += 1
                    else:
                        logger.debug(f"Skipped duplicate test case: {test_case.title}")

        return valid_count

