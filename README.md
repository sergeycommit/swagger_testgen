# Swagger Test Case Generator

Automatic Swagger/OpenAPI test case generator powered by LLMs.

## 🚀 Features

- ✅ Generates both positive and negative test cases
- ✅ Applies every major test design technique (EP, BVA, Error Guessing, Decision Table, Pairwise, State Transition)
- ✅ Async pipeline with per-operation parallelism
- ✅ Supports Swagger 2.0 and OpenAPI 3.x
- ✅ Automatically resolves `$ref` links
- ✅ Accepts specs from URLs or local files
- ✅ Built-in deduplication
- ✅ CSV and JSON export
- ✅ Works with local LLMs (Ollama, LM Studio, vLLM, etc.)
- ✅ Fully configurable via YAML

## 📦 Installation

```bash
pip install -r requirements
```

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
  model: "openai/gpt-4o-mini"
  temperature: 0.7
  max_tokens: 4000
  max_concurrent_requests: null  # null = unlimited

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

- `--format csv|json` - export format
- `--config PATH` - path to YAML config
- `--api-key KEY` - LLM API key
- `--llm-url URL` - LLM endpoint (local or OpenRouter)
- `--max-concurrent N` - limit async requests (0 = unlimited)
- `--log-file PATH` - log file location
- `--log-level LEVEL` - logging level (DEBUG, INFO, WARNING, ERROR)

## 📊 Sample output

```text
📋 Swagger Test Case Generator (v5 - Modular & Async)
============================================================
Spec: swagger.json
Output file: output.csv
LLM URL: https://openrouter.ai/api/v1
LLM model: openai/gpt-4o-mini
Concurrent requests: unlimited
============================================================

1️⃣  Loading and parsing spec...
2️⃣  Generating test cases with the LLM (async fan-out)...

   Test cases generated: 444

   Stats:
   - Positive test cases: 74
   - Negative test cases: 370

3️⃣  Exporting to CSV...
✓ Test cases exported to: output.csv
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
├── generator.py         # Async test case generation
├── exporter.py          # CSV/JSON exporters
├── models.py            # Data models
└── utils.py             # Helpers
```

## 🎯 Test design techniques

The generator applies every technique automatically:

- **EP** (Equivalence Partitioning) - equivalence classes
- **BVA** (Boundary Value Analysis) - boundary values
- **Error Guessing** - typical issues and vulnerabilities
- **Decision Table Testing** - parameter combinations
- **Pairwise Testing** - pairwise coverage
- **State Transition Testing** - state changes

## 📝 Export format

CSV export works with TestIT, Allure TestOps, and most TMS tools:

| Field | Description |
|------|-------------|
| Title | Test case name |
| Test Step # | Step number |
| Test Step Action | Action description |
| Test Step Expected Result | Expected outcome |
| Test Type | Positive / Negative |
| Design Technique | EP, BVA, Error Guessing, etc. |
| API Path | Resource path |
| HTTP Method | GET, POST, PUT, DELETE |
| Priority | High, Medium, Low |

## 🔌 Local LLM support

Works with any OpenAI-compatible API:

- **Ollama**: `http://localhost:11434/v1`
- **LM Studio**: `http://localhost:1234/v1`
- **vLLM**: `http://localhost:8000/v1`
- Any other compatible server

## 📚 Documentation

- `Methodology_for_generating_API_test_cases_from_Swagger_OpenAPI.md` - full methodology
- `config.yaml` - configuration sample
- `analyze_output.py` - CLI quality/duplicate analyzer

## 📄 License

MIT
