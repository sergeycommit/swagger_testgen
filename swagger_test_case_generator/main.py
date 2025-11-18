#!/usr/bin/env python3
"""
Main entry point for the test case generator CLI.
"""

import sys
import os
import asyncio
import argparse

from swagger_test_case_generator.parser import SwaggerParser
from swagger_test_case_generator.generator import LLMTestCaseGenerator
from swagger_test_case_generator.exporter import CSVExporter, JSONExporter
from swagger_test_case_generator.config import Config
from swagger_test_case_generator.utils import setup_logging

def print_statistics(test_cases):
    """Print summary stats for generated test cases."""
    if not test_cases:
        print("   No test cases generated")
        return

    positive_count = sum(1 for tc in test_cases if tc.test_type == "Positive")
    negative_count = sum(1 for tc in test_cases if tc.test_type == "Negative")

    print("\n   Breakdown:")
    print(f"   - Positive test cases: {positive_count}")
    print(f"   - Negative test cases: {negative_count}")

    technique_counts = {}
    for tc in test_cases:
        technique = tc.design_technique
        technique_counts[technique] = technique_counts.get(technique, 0) + 1

    print("\n   By test design technique:")
    for technique, count in sorted(technique_counts.items()):
        print(f"   - {technique}: {count}")


async def main_async(args):
    """Async main routine."""
    # Logging setup
    setup_logging(args.log_file, args.log_level)

    # Load configuration
    config = Config(args.config) if args.config else Config()
    
    # Override config with CLI args
    if args.api_key:
        # Override API key from CLI
        os.environ["OPENROUTER_API_KEY"] = args.api_key
        os.environ["LLM_API_KEY"] = args.api_key  # set for local LLMs as well
    if args.llm_url:
        # Override LLM URL
        config._config.setdefault("llm", {})["base_url"] = args.llm_url
    
    # Ensure OpenRouter key is present when needed
    llm_base_url = config.llm_base_url
    is_openrouter = "openrouter.ai" in llm_base_url.lower()
    
    if is_openrouter and not args.api_key and not os.getenv("OPENROUTER_API_KEY") and not os.getenv("LLM_API_KEY"):
        print("✗ Error: OPENROUTER_API_KEY environment variable is not set.")
        print("Please set it before running or pass --api-key.")
        print("Alternatively provide a local LLM URL via config.yaml (llm.base_url) or --llm-url.")
        sys.exit(1)
    if args.max_concurrent is not None:
        # Override max_concurrent (0 = unlimited)
        config._config.setdefault("llm", {})["max_concurrent_requests"] = args.max_concurrent if args.max_concurrent > 0 else None

    print(f"📋 Swagger Test Case Generator (v5 - Modular & Async)")
    print(f"{'='*60}")
    print(f"Specification: {args.spec}")
    print(f"Output file: {args.output}")
    print(f"LLM URL: {config.llm_base_url}")
    print(f"LLM model: {config.llm_model}")
    max_concurrent = config.max_concurrent_requests
    concurrent_info = "unlimited" if max_concurrent is None or max_concurrent == 0 else str(max_concurrent)
    print(f"Concurrent requests: {concurrent_info}")
    print(f"{'='*60}\n")

    # Load spec
    print("1️⃣  Loading and parsing specification...")
    try:
        parser = SwaggerParser(args.spec)
    except Exception as e:
        print(f"✗ Spec loading error: {e}")
        sys.exit(1)

    # Generate test cases
    print("2️⃣  Generating test cases with the LLM (async fan-out)...")
    generator = LLMTestCaseGenerator(parser, config)
    test_cases = await generator.generate_all_test_cases()

    print(f"\n   Generated test cases: {len(test_cases)}\n")

    if not test_cases:
        print("⚠️  No test cases were generated")
        return

    # Stats
    print_statistics(test_cases)

    # Export
    print(f"\n3️⃣  Exporting to {args.format.upper()}...")
    try:
        if args.format.lower() == "json":
            JSONExporter.export(test_cases, args.output, encoding=config.get("export.encoding", "utf-8"))
        else:
            CSVExporter.export(test_cases, args.output, encoding=config.get("export.encoding", "utf-8"))
        print(f"✓ Test cases exported to: {args.output}")
    except Exception as e:
        print(f"✗ Export error: {e}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print("✓ Generation finished successfully!")
    if args.log_file:
        print(f"📝 Log saved to: {args.log_file}")
    print(f"{'='*60}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Swagger/OpenAPI test case generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s swagger.json output.csv
  %(prog)s swagger.json output.json --format json
  %(prog)s swagger.json output.csv --config config.yaml
  %(prog)s swagger.json output.csv --api-key YOUR_KEY --max-concurrent 10
  
  # Using a local LLM (Ollama, LM Studio, etc.)
  %(prog)s swagger.json output.csv --llm-url http://localhost:1234/v1
  %(prog)s swagger.json output.csv --llm-url http://localhost:11434/v1 --config config.yaml
        """
    )

    parser.add_argument(
        "spec",
        help="Path or URL to the Swagger/OpenAPI spec (.json, .yaml, .yml, http://...)"
    )
    parser.add_argument(
        "output",
        nargs="?",
        default="generated_test_cases.csv",
        help="Path to the output file (default: generated_test_cases.csv)"
    )
    parser.add_argument(
        "--format",
        choices=["csv", "json"],
        default="csv",
        help="Output format (default: csv)"
    )
    parser.add_argument(
        "--config",
        help="Path to a YAML config file"
    )
    parser.add_argument(
        "--api-key",
        help="LLM API key (defaults to OPENROUTER_API_KEY or LLM_API_KEY env vars)"
    )
    parser.add_argument(
        "--llm-url",
        help="LLM API URL (overrides config, e.g. http://localhost:1234/v1)"
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        help="Max concurrent requests (0 = unlimited, overrides config)"
    )
    parser.add_argument(
        "--log-file",
        default="test_case_generation.log",
        help="Path to log file (default: test_case_generation.log)"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Log level (default: INFO)"
    )

    args = parser.parse_args()

    # Verify spec file exists when using local paths
    from urllib.parse import urlparse
    try:
        parsed = urlparse(args.spec)
        is_url = all([parsed.scheme, parsed.netloc])
    except Exception:
        is_url = False
    
    if not is_url and not os.path.exists(args.spec):
        print(f"✗ Spec file not found: {args.spec}")
        print("   Make sure the file exists or provide a URL")
        sys.exit(1)

    # Infer output format from extension when needed
    if args.format == "csv" and args.output.endswith(".json"):
        args.format = "json"
    elif args.format == "json" and args.output.endswith(".csv"):
        args.format = "csv"

    # Run async routine
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Critical error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

