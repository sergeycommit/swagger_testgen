"""
LLM-powered test case generator (OpenRouter or local) with async parallelism.
Supports OpenAI Structured Outputs for reliable JSON parsing.
"""

import json
import re
import asyncio
import logging
from typing import Dict, List, Any, Set, Optional
from openai import AsyncOpenAI
from pydantic import ValidationError
from .models import TestCase, TestCaseSchema, TestCasesResponse
from .parser import SwaggerParser
from .config import Config
from .utils import validate_test_case

logger = logging.getLogger(__name__)

# Models known to support structured outputs (response_format with json_schema)
STRUCTURED_OUTPUT_MODELS = {
    "gpt-4o",
    "gpt-4o-2024-08-06",
    "gpt-4o-2024-11-20",
    "gpt-4o-mini",
    "gpt-4o-mini-2024-07-18",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "openai/gpt-4o-2024-08-06",
    "openai/gpt-4o-2024-11-20",
    "openai/gpt-4o-mini-2024-07-18",
}


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
        
        # Check if the model supports structured outputs
        self.use_structured_output = self._supports_structured_output(config.llm_model)
        if self.use_structured_output:
            logger.info(f"Model '{config.llm_model}' supports structured outputs - using JSON schema validation")
        else:
            logger.info(f"Model '{config.llm_model}' may not support structured outputs - using fallback parsing")
        
        # Log streaming mode
        if config.use_streaming:
            logger.info("Streaming mode enabled - partial responses will be captured on truncation")
        else:
            logger.info("Streaming mode disabled")

    def _supports_structured_output(self, model: str) -> bool:
        """Check if the model supports structured outputs."""
        # Check exact match or prefix match
        model_lower = model.lower()
        for supported in STRUCTURED_OUTPUT_MODELS:
            if model_lower == supported.lower() or model_lower.startswith(supported.lower()):
                return True
        return False

    def _build_system_prompt(self) -> str:
        """Build an optimized system prompt for test case generation."""
        return """You are a senior QA engineer specializing in API testing. Generate comprehensive test cases for the provided API operation.

## Test Design Techniques to Apply

1. **EP (Equivalence Partitioning)**: Group inputs into valid/invalid classes
   - Valid: within type, format, enum values, required constraints
   - Invalid: wrong type, out of enum, violates constraints

2. **BVA (Boundary Value Analysis)**: Test edges of valid ranges
   - Positive: min, max, minLength, maxLength (exact boundaries)
   - Negative: min-1, max+1, below minLength, above maxLength

3. **Error Guessing**: Common API failures
   - Missing/invalid/expired auth tokens
   - SQL injection: ' OR 1=1 --, '; DROP TABLE
   - XSS: <script>alert(1)</script>
   - Empty strings, null, very long strings (10000+ chars)
   - Special chars: <>&"'\\/
   - Invalid formats: malformed email/URL/UUID/date

4. **Decision Table Testing**: Combinations of conditions
   - Required vs optional fields present/missing
   - Auth + resource ownership combinations

5. **State Transition Testing** (when applicable):
   - Valid state changes (created→active→completed)
   - Invalid transitions (completed→created)

## Priority Guidelines
- **High**: Happy path, auth failures, type mismatches
- **Medium**: Boundary values, validation errors, missing fields
- **Low**: Edge cases, unusual combinations, exploratory

## Output Requirements
Return JSON object: {"test_cases": [...]}

Each test case must have:
- title: Concise name with method, scenario, technique
- description: What this test verifies
- preconditions: Setup needed (auth, test data)
- test_type: "Positive" or "Negative"
- design_technique: "EP" | "BVA" | "Error Guessing" | "Decision Table Testing" | "Pairwise Testing" | "State Transition Testing"
- priority: "High" | "Medium" | "Low"
- api_path: The endpoint path
- http_method: GET/POST/PUT/PATCH/DELETE
- test_steps: [{action: "...", expected_result: "..."}]

## Example Test Case
```json
{
  "title": "POST /users - Invalid email format (EP-Negative)",
  "description": "Verify API rejects user creation with malformed email",
  "preconditions": "Valid auth token available",
  "test_type": "Negative",
  "design_technique": "EP",
  "priority": "Medium",
  "api_path": "/users",
  "http_method": "POST",
  "test_steps": [
    {
      "action": "Send POST /users with body: {\"email\": \"invalid-email\", \"name\": \"Test\"}",
      "expected_result": "HTTP 400/422. Error message indicates invalid email format."
    }
  ]
}
```"""

    def _build_user_prompt(self, operation_spec_json: str) -> str:
        """Build the user prompt with operation context."""
        return f"""Generate test cases for this API operation:

```json
{operation_spec_json}
```

## Generation Checklist

**Positive cases (aim for 20-30%):**
- [ ] Happy path with all required fields (valid data)
- [ ] Each enum value as separate test
- [ ] Boundary values within valid range (min, max)
- [ ] Request with all optional fields included

**Negative cases (aim for 70-80%):**
For EACH parameter, generate cases for:
- [ ] Missing (if required)
- [ ] Wrong type (string→number, etc.)
- [ ] Out of range (BVA: min-1, max+1)
- [ ] Invalid format (if format specified)
- [ ] Empty/null value
- [ ] Injection payloads (strings only)

**Auth scenarios (if security defined):**
- [ ] Missing authorization header
- [ ] Invalid/malformed token
- [ ] Expired token (if applicable)

**Resource scenarios (for paths with IDs):**
- [ ] Non-existent ID (expect 404)
- [ ] Invalid ID format

Focus on QUALITY over quantity. Each test case should verify ONE specific scenario.
Generate 15-40 focused test cases depending on operation complexity."""

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

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(operation_spec_json)

        for attempt in range(self.config.max_retries):
            try:
                logger.debug(f"LLM request for {method} {path} (attempt {attempt + 1}/{self.config.max_retries})")
                
                # Use structured outputs if supported, otherwise fall back to json_object
                if self.use_structured_output:
                    generated_cases_data = await self._generate_with_structured_output(
                        system_prompt, user_prompt, path, method
                    )
                else:
                    generated_cases_data = await self._generate_with_json_mode(
                        system_prompt, user_prompt
                    )

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

    async def _generate_with_structured_output(
        self,
        system_prompt: str,
        user_prompt: str,
        path: str,
        method: str
    ) -> List[Dict[str, Any]]:
        """Generate test cases using OpenAI Structured Outputs with Pydantic schema."""
        try:
            response = await self.client.beta.chat.completions.parse(
                model=self.config.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format=TestCasesResponse,
                temperature=self.config.llm_temperature,
                max_tokens=self.config.llm_max_tokens
            )

            parsed = response.choices[0].message.parsed
            
            if parsed is None:
                # Check if response was refused or truncated
                if response.choices[0].message.refusal:
                    logger.warning(f"Model refused to generate: {response.choices[0].message.refusal}")
                    return []
                
                # Try fallback parsing from content
                content = response.choices[0].message.content
                if content:
                    logger.warning("Structured parsing failed, attempting fallback")
                    return self._parse_llm_response(content)
                return []

            # Convert Pydantic models to dicts
            return [tc.model_dump() for tc in parsed.test_cases]

        except ValidationError as e:
            logger.warning(f"Pydantic validation error: {e}")
            # Try to extract partial valid data
            return []
        except Exception as e:
            error_str = str(e).lower()
            
            # Handle length limit reached - fall back to JSON mode for this request
            if "length limit" in error_str or "could not parse response content" in error_str:
                logger.warning(f"Response truncated due to token limit, falling back to JSON mode for {method} {path}")
                return await self._generate_with_json_mode(system_prompt, user_prompt)
            
            # If structured output not supported, fall back permanently
            if "does not support" in error_str or "response_format" in error_str:
                logger.warning(f"Structured output not supported, falling back to JSON mode: {e}")
                self.use_structured_output = False
                return await self._generate_with_json_mode(system_prompt, user_prompt)
            raise

    async def _generate_with_json_mode(
        self,
        system_prompt: str,
        user_prompt: str
    ) -> List[Dict[str, Any]]:
        """Generate test cases using JSON mode with optional streaming."""
        if self.config.use_streaming:
            return await self._generate_with_streaming(system_prompt, user_prompt)
        else:
            return await self._generate_without_streaming(system_prompt, user_prompt)

    async def _generate_with_streaming(
        self,
        system_prompt: str,
        user_prompt: str
    ) -> List[Dict[str, Any]]:
        """Generate test cases using streaming to capture partial responses."""
        collected_content = ""
        finish_reason = None
        
        try:
            stream = await self.client.chat.completions.create(
                model=self.config.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=self.config.llm_temperature,
                max_tokens=self.config.llm_max_tokens,
                stream=True
            )

            async for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    choice = chunk.choices[0]
                    
                    # Collect content delta
                    if choice.delta and choice.delta.content:
                        collected_content += choice.delta.content
                    
                    # Track finish reason
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason

            # Log truncation warning
            if finish_reason == "length":
                logger.warning(
                    f"Response was truncated due to max_tokens limit. "
                    f"Collected {len(collected_content)} characters. "
                    f"Consider increasing max_tokens in config."
                )
            elif finish_reason == "stop":
                logger.debug("Response completed normally")
            else:
                logger.debug(f"Response finished with reason: {finish_reason}")

        except Exception as e:
            logger.error(f"Streaming error: {e}")
            # If streaming fails, fall back to non-streaming
            if collected_content:
                logger.info(f"Attempting to parse partial streamed content ({len(collected_content)} chars)")
            else:
                return await self._generate_without_streaming(system_prompt, user_prompt)

        if not collected_content:
            logger.warning("No content received from streaming response")
            return []

        return self._parse_llm_response(collected_content)

    async def _generate_without_streaming(
        self,
        system_prompt: str,
        user_prompt: str
    ) -> List[Dict[str, Any]]:
        """Fallback non-streaming generation."""
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
        return self._parse_llm_response(json_string)

    def _parse_llm_response(self, json_string: str) -> List[Dict[str, Any]]:
        """Parse the LLM response with multiple fallback strategies."""
        if not json_string:
            return []

        # Strategy 1: Direct JSON parse
        raw_data = self._try_direct_parse(json_string)
        if raw_data is not None:
            return self._normalize_response(raw_data)

        # Strategy 2: Extract from markdown code block
        raw_data = self._try_extract_code_block(json_string)
        if raw_data is not None:
            return self._normalize_response(raw_data)

        # Strategy 3: Find array boundaries
        raw_data = self._try_extract_array(json_string)
        if raw_data is not None:
            return self._normalize_response(raw_data)

        # Strategy 4: Repair truncated JSON
        raw_data = self._try_repair_json(json_string)
        if raw_data is not None:
            result = self._normalize_response(raw_data)
            if result:
                logger.info(f"Recovered {len(result)} cases using JSON repair")
                return result

        # Strategy 5: Extract individual complete objects
        partial_cases = self._extract_complete_objects(json_string)
        if partial_cases:
            logger.info(f"Recovered {len(partial_cases)} cases from partial response")
            return partial_cases

        logger.error("All JSON parsing strategies failed")
        return []

    def _try_direct_parse(self, json_string: str) -> Optional[Any]:
        """Attempt direct JSON parsing."""
        try:
            return json.loads(json_string)
        except json.JSONDecodeError:
            return None

    def _try_extract_code_block(self, json_string: str) -> Optional[Any]:
        """Extract JSON from markdown code blocks."""
        code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', json_string)
        if code_block_match:
            try:
                return json.loads(code_block_match.group(1))
            except json.JSONDecodeError:
                pass
        return None

    def _try_extract_array(self, json_string: str) -> Optional[Any]:
        """Extract JSON array from response."""
        start_idx = json_string.find('[')
        end_idx = json_string.rfind(']') + 1
        if start_idx != -1 and end_idx > start_idx:
            try:
                return json.loads(json_string[start_idx:end_idx])
            except json.JSONDecodeError:
                pass
        return None

    def _try_repair_json(self, json_string: str) -> Optional[Any]:
        """Attempt to repair truncated JSON by closing open structures."""
        # Find the array start
        start_idx = json_string.find('[')
        if start_idx == -1:
            # Try to find object start for {"test_cases": [...]}
            start_idx = json_string.find('{')
        
        if start_idx == -1:
            return None

        fragment = json_string[start_idx:]
        
        # Try to find the last complete object
        last_complete = self._find_last_complete_object(fragment)
        if last_complete:
            fragment = last_complete

        # Count and close open brackets
        open_braces = fragment.count('{') - fragment.count('}')
        open_brackets = fragment.count('[') - fragment.count(']')
        
        # Remove trailing comma if present
        fragment = fragment.rstrip()
        if fragment.endswith(','):
            fragment = fragment[:-1]
        
        # Close structures
        fragment += '}' * max(0, open_braces)
        fragment += ']' * max(0, open_brackets)
        
        try:
            return json.loads(fragment)
        except json.JSONDecodeError:
            return None

    def _find_last_complete_object(self, json_str: str) -> Optional[str]:
        """Find the position after the last complete JSON object in an array."""
        depth = 0
        last_complete_pos = 0
        in_string = False
        escape_next = False
        
        for i, char in enumerate(json_str):
            if escape_next:
                escape_next = False
                continue
            
            if char == '\\':
                escape_next = True
                continue
            
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            
            if in_string:
                continue
            
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    last_complete_pos = i + 1
            elif char == '[':
                depth += 1
            elif char == ']':
                depth -= 1
        
        if last_complete_pos > 0:
            # Include everything up to and including the last complete object
            result = json_str[:last_complete_pos]
            # Check if we need to close the array
            if result.count('[') > result.count(']'):
                result += ']'
            return result
        
        return None

    def _extract_complete_objects(self, json_string: str) -> List[Dict[str, Any]]:
        """Extract all complete JSON objects that look like test cases."""
        results = []
        
        # Pattern to find complete objects with test case structure
        # This handles nested objects but not deeply nested
        depth = 0
        start = -1
        in_string = False
        escape_next = False
        
        for i, char in enumerate(json_string):
            if escape_next:
                escape_next = False
                continue
            
            if char == '\\':
                escape_next = True
                continue
            
            if char == '"':
                in_string = not in_string
                continue
            
            if in_string:
                continue
            
            if char == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0 and start != -1:
                    try:
                        obj_str = json_string[start:i+1]
                        obj = json.loads(obj_str)
                        # Check if it looks like a test case
                        if self._is_test_case_like(obj):
                            results.append(obj)
                    except json.JSONDecodeError:
                        pass
                    start = -1
        
        return results

    def _is_test_case_like(self, obj: Dict[str, Any]) -> bool:
        """Check if an object looks like a test case."""
        test_case_keys = {'title', 'test_steps', 'test_type', 'api_path', 'http_method'}
        return len(test_case_keys & set(obj.keys())) >= 3

    def _normalize_response(self, raw_data: Any) -> List[Dict[str, Any]]:
        """Normalize the parsed response to a list of test case dicts."""
        if isinstance(raw_data, dict):
            # Try common wrapper keys
            for key in ['test_cases', 'cases', 'testCases', 'data', 'results']:
                if key in raw_data and isinstance(raw_data[key], list):
                    return self._validate_cases(raw_data[key])
            # If it's a single test case
            if self._is_test_case_like(raw_data):
                return self._validate_cases([raw_data])
            return []
        elif isinstance(raw_data, list):
            return self._validate_cases(raw_data)
        
        logger.error(f"Unexpected data format from LLM: {type(raw_data)}")
        return []

    def _validate_cases(self, cases: List[Any]) -> List[Dict[str, Any]]:
        """Validate and filter cases using Pydantic schema."""
        valid_cases = []
        
        for case in cases:
            if not isinstance(case, dict):
                continue
            
            try:
                # Try to validate with Pydantic
                validated = TestCaseSchema(**case)
                valid_cases.append(validated.model_dump())
            except ValidationError as e:
                # If validation fails, try to salvage with minimal required fields
                if self._is_test_case_like(case):
                    # Fill in defaults for missing fields
                    salvaged = self._salvage_case(case)
                    if salvaged:
                        valid_cases.append(salvaged)
                        logger.debug(f"Salvaged case with defaults: {case.get('title', 'Unknown')}")
                else:
                    logger.debug(f"Dropped invalid case: {str(e)[:100]}")
        
        return valid_cases

    def _salvage_case(self, case: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Try to salvage a partially valid case by filling defaults."""
        required = ['title', 'test_steps']
        if not all(case.get(k) for k in required):
            return None
        
        # Ensure test_steps is valid
        steps = case.get('test_steps', [])
        if not steps or not isinstance(steps, list):
            return None
        
        valid_steps = []
        for step in steps:
            if isinstance(step, dict) and step.get('action'):
                valid_steps.append({
                    'action': step.get('action', ''),
                    'expected_result': step.get('expected_result', 'Verify the result')
                })
        
        if not valid_steps:
            return None
        
        return {
            'title': case.get('title', 'Untitled'),
            'description': case.get('description', ''),
            'preconditions': case.get('preconditions', ''),
            'test_type': case.get('test_type', 'Unknown'),
            'design_technique': case.get('design_technique', 'Unknown'),
            'api_path': case.get('api_path', ''),
            'http_method': case.get('http_method', ''),
            'priority': case.get('priority', 'Medium'),
            'test_steps': valid_steps
        }

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

