#!/usr/bin/env python3
"""
Test case quality analyzer and duplicate detector for output.csv
"""

import csv
import sys
from collections import defaultdict, Counter
from typing import Dict, List, Set

def analyze_csv(file_path: str):
    """Analyze the exported CSV file with test cases."""
    
    test_cases = []
    unique_keys = defaultdict(list)
    duplicates = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=2):  # start at 2 to account for the header
            test_cases.append(row)
            
            # Build a unique key to spot duplicates
            key = (
                row.get('API Path', '').strip(),
                row.get('HTTP Method', '').strip(),
                row.get('Test Type', '').strip(),
                row.get('Design Technique', '').strip(),
                row.get('Title', '').strip()[:50]  # first 50 characters
            )
            unique_keys[key].append((idx, row))
    
    # Find duplicates
    for key, occurrences in unique_keys.items():
        if len(occurrences) > 1:
            duplicates.append({
                'key': key,
                'count': len(occurrences),
                'rows': occurrences
            })
    
    # Stats
    total_cases = len(test_cases)
    unique_cases = len(unique_keys)
    duplicate_count = sum(d['count'] - 1 for d in duplicates)
    
    # Type breakdowns
    test_types = Counter(row.get('Test Type', 'Unknown') for row in test_cases)
    techniques = Counter(row.get('Design Technique', 'Unknown') for row in test_cases)
    methods = Counter(row.get('HTTP Method', 'Unknown') for row in test_cases)
    priorities = Counter(row.get('Priority', 'Unknown') for row in test_cases)
    
    # Quality checks
    quality_issues = []
    
    # Empty fields
    empty_titles = [i+2 for i, row in enumerate(test_cases) if not row.get('Title', '').strip()]
    empty_actions = [i+2 for i, row in enumerate(test_cases) if not row.get('Test Step Action', '').strip()]
    empty_results = [i+2 for i, row in enumerate(test_cases) if not row.get('Test Step Expected Result', '').strip()]
    
    if empty_titles:
        quality_issues.append(f"Empty titles: {len(empty_titles)} cases (rows: {empty_titles[:10]})")
    if empty_actions:
        quality_issues.append(f"Empty actions: {len(empty_actions)} cases (rows: {empty_actions[:10]})")
    if empty_results:
        quality_issues.append(f"Empty expected results: {len(empty_results)} cases (rows: {empty_results[:10]})")
    
    # Very short titles
    short_titles = [i+2 for i, row in enumerate(test_cases) if len(row.get('Title', '').strip()) < 10]
    if short_titles:
        quality_issues.append(f"Extremely short titles (<10 chars): {len(short_titles)} cases")
    
    # Group by API Path
    paths = Counter(row.get('API Path', 'Unknown') for row in test_cases)
    
    # Report
    print("=" * 80)
    print("TEST CASE QUALITY ANALYSIS")
    print("=" * 80)
    print()
    
    print("📊 OVERALL STATS:")
    print(f"  Total test cases: {total_cases}")
    print(f"  Unique test cases: {unique_cases}")
    print(f"  Duplicates: {duplicate_count}")
    print(f"  Duplicate share: {duplicate_count/total_cases*100:.1f}%")
    print()
    
    print("📈 BY TEST TYPE:")
    for test_type, count in test_types.most_common():
        print(f"  {test_type}: {count} ({count/total_cases*100:.1f}%)")
    print()
    
    print("🎯 BY DESIGN TECHNIQUE:")
    for technique, count in techniques.most_common():
        print(f"  {technique}: {count} ({count/total_cases*100:.1f}%)")
    print()
    
    print("🔧 BY HTTP METHOD:")
    for method, count in methods.most_common():
        print(f"  {method}: {count} ({count/total_cases*100:.1f}%)")
    print()
    
    print("⭐ BY PRIORITY:")
    for priority, count in priorities.most_common():
        print(f"  {priority}: {count} ({count/total_cases*100:.1f}%)")
    print()
    
    print("📍 TOP-10 API PATHS BY CASE COUNT:")
    for path, count in paths.most_common(10):
        print(f"  {path}: {count} cases")
    print()
    
    if duplicates:
        print("⚠️  DUPLICATE GROUPS:")
        print(f"  Total duplicate groups: {len(duplicates)}")
        print()
        for i, dup in enumerate(duplicates[:10], 1):  # show first 10
            print(f"  Duplicate #{i}:")
            print(f"    Path: {dup['key'][0]}")
            print(f"    Method: {dup['key'][1]}")
            print(f"    Type: {dup['key'][2]}")
            print(f"    Technique: {dup['key'][3]}")
            print(f"    Title: {dup['key'][4]}")
            print(f"    Count: {dup['count']}")
            print(f"    Rows: {[r[0] for r in dup['rows']]}")
            print()
        if len(duplicates) > 10:
            print(f"  ... plus {len(duplicates) - 10} more duplicate groups")
        print()
    
    if quality_issues:
        print("🔍 QUALITY ISSUES:")
        for issue in quality_issues:
            print(f"  ⚠️  {issue}")
        print()
    else:
        print("✅ NO QUALITY ISSUES FOUND")
        print()
    
    # Quality score
    quality_score = 100
    if duplicate_count > 0:
        quality_score -= min(30, duplicate_count/total_cases*100)
    if empty_titles or empty_actions or empty_results:
        quality_score -= 20
    if short_titles:
        quality_score -= 10
    
    print("=" * 80)
    print(f"QUALITY SCORE: {quality_score:.1f}/100")
    print("=" * 80)
    
    return {
        'total': total_cases,
        'unique': unique_cases,
        'duplicates': duplicate_count,
        'duplicate_groups': len(duplicates),
        'quality_score': quality_score,
        'test_types': dict(test_types),
        'techniques': dict(techniques),
        'quality_issues': quality_issues
    }

if __name__ == "__main__":
    file_path = "example_petstore/output.csv"
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    
    try:
        analyze_csv(file_path)
    except FileNotFoundError:
        print(f"❌ File {file_path} not found!")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

