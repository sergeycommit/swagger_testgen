# Swagger Test Case Generator

Automatic Swagger/OpenAPI test case generator powered by LLMs.

## 🚀 Features

- ✅ Generates both positive and negative test cases
- ✅ Applies every major test design technique (EP, BVA, Error Guessing, Decision Table, Pairwise, State Transition)
- ✅ **OpenAI Structured Outputs** for reliable JSON parsing (gpt-4o, gpt-4o-mini)
- ✅ **Streaming mode** to capture partial responses on truncation
- ✅ **Multi-strategy JSON recovery** for non-structured output models
- ✅ Async pipeline with per-operation parallelism
- ✅ Supports Swagger 2.0 and OpenAPI 3.x
- ✅ Automatically resolves `$ref` links
- ✅ Accepts specs from URLs or local files
- ✅ Built-in deduplication with Pydantic validation
- ✅ CSV and JSON export
- ✅ Works with local LLMs (Ollama, LM Studio, vLLM, etc.)
- ✅ Fully configurable via YAML

## 📦 Installation

```bash
pip install -r requirements
```

**Dependencies:**
- `openai>=1.50.0` — OpenAI SDK with structured outputs support
- `pydantic>=2.0.0` — Schema validation
- `PyYAML>=6.0.3` — Config parsing
- `httpx>=0.24.0` — HTTP client
- `python-dotenv>=0.9.9` — Environment variables

## ⚙️ Configuration

### 1. API key (for OpenRouter)

```bash
export OPENROUTER_API_KEY="your-key-here"
```

### 2. Optional config file

Create `config.yaml` based on the provided sample:

```yaml
llm:
  base_url: "https://openrouter.ai/api/v1"  # or a local endpoint
  model: "openai/gpt-4o-mini"  # supports structured outputs
  temperature: 0.7
  max_tokens: 16000  # gpt-4o-mini supports up to 16k output tokens
  max_concurrent_requests: null  # null = unlimited
  use_streaming: true  # capture partial responses on truncation

generation:
  enable_deduplication: true
```

## 🔧 Usage

### Basic run (local spec file)

```bash
python -m swagger_test_case_generator.main swagger.json output.csv
```

### Downloading a spec from URL

```bash
# From URL (JSON)
python -m swagger_test_case_generator.main \
  https://petstore.swagger.io/v2/swagger.json output.csv

# From URL (YAML)
python -m swagger_test_case_generator.main \
  https://api.example.com/openapi.yaml output.csv
```

### Using a config file

```bash
python -m swagger_test_case_generator.main swagger.json output.csv --config config.yaml
```

### Local LLM (Ollama, LM Studio, etc.)

```bash
python -m swagger_test_case_generator.main swagger.json output.csv \
  --llm-url http://localhost:1234/v1
```

Or via `config.yaml`:

```yaml
llm:
  base_url: "http://localhost:11434/v1"  # Ollama
  model: "llama3.2"
  use_streaming: true  # recommended for local models
```

### Combining remote spec + local LLM

```bash
# Fetch spec from URL and use a local LLM
python -m swagger_test_case_generator.main \
  https://petstore.swagger.io/v2/swagger.json output.csv \
  --llm-url http://localhost:11434/v1
```

### Full CLI help

```bash
python -m swagger_test_case_generator.main --help
```

**Available options:**

| Option | Description |
|--------|-------------|
| `--format csv\|json` | Export format |
| `--config PATH` | Path to YAML config |
| `--api-key KEY` | LLM API key |
| `--llm-url URL` | LLM endpoint (local or OpenRouter) |
| `--max-concurrent N` | Limit async requests (0 = unlimited) |
| `--log-file PATH` | Log file location |
| `--log-level LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) |

## 📊 Sample output

```text
📋 Swagger Test Case Generator (v5 - Modular & Async)
============================================================
Specification: swagger.json
Output file: output.csv
LLM URL: https://openrouter.ai/api/v1
LLM model: openai/gpt-4o-mini
Concurrent requests: unlimited
============================================================

1️⃣  Loading and parsing specification...
2️⃣  Generating test cases with the LLM (async fan-out)...

   Generated test cases: 342

   Breakdown:
   - Positive test cases: 68
   - Negative test cases: 274

   By test design technique:
   - BVA: 89
   - EP: 112
   - Error Guessing: 98
   - Decision Table Testing: 43

3️⃣  Exporting to CSV...
✓ Test cases exported to: output.csv
```

## 🧠 Structured Outputs & JSON Recovery

The generator uses a multi-layer approach for reliable JSON parsing:

### For models with Structured Outputs support (gpt-4o, gpt-4o-mini)

```
┌─────────────────────────────────────┐
│  OpenAI beta.chat.completions.parse │
│  with Pydantic schema validation    │
└─────────────────────────────────────┘
              │
              ▼
     Automatic type coercion
     and validation via Pydantic
```

### For other models (fallback with streaming)

```
┌─────────────────────────────────────┐
│     Streaming JSON collection       │
│   (captures partial on truncation)  │
└─────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│   5-Strategy JSON Recovery:         │
│   1. Direct parse                   │
│   2. Extract from code blocks       │
│   3. Find array boundaries          │
│   4. Repair truncated JSON          │
│   5. Extract complete objects       │
└─────────────────────────────────────┘
              │
              ▼
     Pydantic validation per case
     (salvage partial data)
```

## 🧮 Result analysis (`analyze_output.py`)

Run the analyzer to quickly spot duplicates and quality issues:

```bash
python analyze_output.py output.csv
```

The script summarizes test types, design techniques, HTTP methods, and priorities, highlights duplicate groups, flags empty or overly short steps, and outputs an overall `quality_score`. It defaults to `output.csv` but accepts any exported CSV path.

## 📁 Project layout

```text
swagger_test_case_generator/
├── __init__.py
├── main.py              # CLI entry point
├── config.py            # Configuration management
├── parser.py            # Swagger/OpenAPI parser
├── generator.py         # Async test case generation + structured outputs
├── exporter.py          # CSV/JSON exporters
├── models.py            # Pydantic data models & schemas
└── utils.py             # Helpers
```

## 🎯 Test design techniques

The generator applies every technique automatically:

| Technique | Description | Test Types |
|-----------|-------------|------------|
| **EP** (Equivalence Partitioning) | Valid/invalid input classes | Positive & Negative |
| **BVA** (Boundary Value Analysis) | min, max, min-1, max+1 | Positive & Negative |
| **Error Guessing** | SQLi, XSS, auth failures, invalid formats | Negative |
| **Decision Table Testing** | Required/optional field combinations | Both |
| **Pairwise Testing** | Parameter pair coverage | Positive |
| **State Transition Testing** | Valid/invalid state changes | Both |

## 📝 Export format

CSV export works with TestIT, Allure TestOps, and most TMS tools:

| Field | Description |
|-------|-------------|
| Title | Test case name |
| Description | What the test verifies |
| Preconditions | Setup required |
| Test Step # | Step number |
| Test Step Action | Action description |
| Test Step Expected Result | Expected outcome |
| Test Type | Positive / Negative |
| Design Technique | EP, BVA, Error Guessing, etc. |
| API Path | Resource path |
| HTTP Method | GET, POST, PUT, PATCH, DELETE |
| Priority | High, Medium, Low |
| Created Date | Generation timestamp |

## 🔌 Local LLM support

Works with any OpenAI-compatible API:

| Provider | URL | Notes |
|----------|-----|-------|
| **Ollama** | `http://localhost:11434/v1` | Use `use_streaming: true` |
| **LM Studio** | `http://localhost:1234/v1` | Good structured output support |
| **vLLM** | `http://localhost:8000/v1` | High performance |
| **LocalAI** | `http://localhost:8080/v1` | Multi-model support |

**Note:** For local models without structured output support, the generator automatically falls back to streaming + JSON recovery mode.

## ⚡ Performance tips

1. **Use gpt-4o-mini** for best balance of speed/quality/cost
2. **Set `max_tokens: 16000`** to avoid truncation
3. **Enable streaming** (`use_streaming: true`) for partial recovery
4. **Limit concurrency** for local LLMs (`max_concurrent_requests: 2-4`)
5. **Filter operations** with `include_paths` / `include_methods` for large specs

## 📚 Documentation

- `Methodology_for_generating_API_test_cases_from_Swagger_OpenAPI.md` - full methodology
- `config.yaml` - configuration sample with all options
- `analyze_output.py` - CLI quality/duplicate analyzer

## 📄 License

MIT
