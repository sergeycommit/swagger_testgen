# Methodology for Generating API Test Cases from Swagger/OpenAPI

This document describes the methodology used by the AI agent to automatically generate positive and negative test cases from a given Swagger/OpenAPI specification. The goal is to reach maximum coverage by applying every major test design technique.

## 1. Overview of API Test Design Techniques

The generator applies the following techniques, tailored to the structure and data models defined in the specification:

| Technique | How it applies to Swagger/OpenAPI | Test type |
| :--- | :--- | :--- |
| **Equivalence Partitioning (EP)** | Identify valid and invalid ranges/values for each parameter (query, path, header, body) using `type`, `format`, `minimum`, `maximum`, `enum`, `pattern`. | Positive (valid classes) and Negative (invalid classes) |
| **Boundary Value Analysis (BVA)** | Exercise min/max boundaries: `min`, `min+1`, `max-1`, `max`. Works for numeric values and strings with length limits. | Positive and Negative |
| **Decision Table Testing** | Cover operations where the outcome depends on multiple inputs (e.g., access rights combined with resource status). | Positive and Negative |
| **Pairwise Testing** | Generate combinations that ensure every pair of parameters is tested together. Useful when parameter interaction matters. | Positive |
| **Error Guessing** | Leverage domain knowledge to model typical API issues (SQL injection, XSS, invalid tokens, missing required fields, etc.). | Negative |
| **State Transition Testing** | Apply to resources with a lifecycle (orders, user accounts, etc.) to verify valid and invalid state transitions. | Positive and Negative |

## 2. Test Case Structure for CSV Export

To keep exports compatible with TestIT, Allure TestOps, and other TMS tools, the generator emits a generic CSV schema that maps easily everywhere.

| CSV field | Description | Example |
| :--- | :--- | :--- |
| `Title` | Short, unique test case title. | `POST /users - Positive - Valid new user data (EP)` |
| `Preconditions` | Actions required before the test (auth, seed data, etc.). | `User is authenticated. No account with this email exists.` |
| `Test Step Action` | Detailed step/action to execute. | `Send a POST /api/v1/users request with a valid JSON body.` |
| `Test Step Expected Result` | What should happen after the step. | `HTTP 201. Response body contains the created user object with a valid ID.` |
| `Test Type` | High-level type for filtering. | `Positive` or `Negative` |
| `Design Technique` | Technique applied for this case. | `EP`, `BVA`, `Error Guessing`, etc. |
| `API Path` | Target resource path. | `/api/v1/users` |
| `HTTP Method` | HTTP verb. | `POST` |

## 3. Generation Algorithm

For every operation (path + method) the agent executes the following:

1. **Parse the operation.** Extract path, method, parameters, request bodies, and response schemas.
2. **Generate positive cases.**
   - **Baseline positive case:** Minimum required valid data that satisfies all mandatory fields.
   - **EP/BVA (positive):** For each constrained parameter, create cases that cover all valid partitions and boundary points (`min`, `max`, etc.).
   - **Pairwise/Decision Table:** Generate combinations of valid data to cover meaningful interactions.
3. **Generate negative cases.**
   - **EP/BVA (negative):**
     - Values outside the allowed range (`min-1`, `max+1`).
     - Wrong data types (string instead of number, etc.).
     - Missing required fields.
     - Empty/null values when not permitted.
   - **Error Guessing:**
     - Invalid formats (email without `@`, malformed URLs, etc.).
     - Strings that exceed `maxLength`.
     - Special characters/injection payloads in text fields.
     - Invalid/expired/missing auth tokens.
   - **State Transition:** Attempt invalid transitions (e.g., paying an already paid order).
4. **Formatting.** Convert each generated case into a CSV row per the structure from section 2.

## 4. Implementation Notes

The AI agent ships as a modular Python package and relies on:

- A parser for Swagger/OpenAPI (2.0 and 3.x support)
- OpenRouter (or any OpenAI-compatible API) for LLM access
- Async processing to parallelize generation per operation

**Current implementation (v5):**

1. **Modular architecture**
   - `parser.py` — parsing and `$ref` resolution
   - `generator.py` — async LLM-driven generation
   - `exporter.py` — CSV and JSON export
   - `config.py` — configuration handling
   - `models.py` — data models

2. **Key capabilities**
   - Automatic `$ref` resolution
   - Swagger 2.0 / OpenAPI 3.x support
   - Configurable concurrency
   - Validation of generated test cases
   - Duplicate removal
   - Filtering by path, method, and tag
   - CSV and JSON output

3. **Usage**

```bash
python -m swagger_test_case_generator.main swagger.json output.csv
```

4. **Configuration**

- YAML-based (`config.yaml`)
- LLM model, temperature, token limits
- Concurrency and filter settings

**Implementation details**

- `generate_test_cases()` drives the LLM to analyze schemas and produce valid/invalid datasets per parameter.
- Each test case includes action/expected result descriptions mapped to the selected technique.
- All techniques are applied automatically for maximum coverage.
- The generator does not limit the number of cases—coverage takes priority over quantity.

