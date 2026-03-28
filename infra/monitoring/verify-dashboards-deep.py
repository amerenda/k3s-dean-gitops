#!/usr/bin/env python3
"""
Deep verification of Grafana dashboard panel queries against Prometheus.

Port-forwards to Prometheus, parses every dashboard YAML, extracts all PromQL
expressions, executes them, and reports which panels have data, which are empty,
and which reference missing metrics.
"""

import glob
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DASHBOARDS_DIR = Path(__file__).parent / "dashboards"
PROM_SVC = "svc/infra-monitoring-kube-prom-prometheus"
PROM_NS = "monitoring"
LOCAL_PORT = 19091
PROM_URL = f"http://localhost:{LOCAL_PORT}"

# Patterns that suggest a query is legitimately empty (error counters, etc.)
EXPECTED_EMPTY_PATTERNS = [
    r'code\s*[=~]+\s*"["\s]*[45]',    # HTTP 4xx/5xx codes
    r'code\s*=~\s*"5\.\.',              # 5xx regex
    r'code\s*=~\s*"4\.\.',              # 4xx regex
    r'==\s*0',                           # equality to zero
    r'error',                            # error in expression
    r'fail',                             # fail in expression
    r'reject',                           # reject in expression
    r'panic',                            # panic in expression
    r'drop',                             # drop in expression
    r'miss(?:ed|es|ing)?(?:[^a-z]|$)',   # cache misses etc
    r'timeout',                          # timeout counters
    r'restart',                          # restart counters
    r'evict',                            # eviction counters
    r'oom',                              # out of memory
    r'code!~"2',                         # not 2xx (error codes)
]


@dataclass
class QueryResult:
    dashboard: str
    panel_title: str
    expr: str
    status: str  # HAS_DATA, NO_DATA, METRIC_MISSING, EXPECTED_EMPTY, QUERY_ERROR
    detail: str = ""
    metrics_info: dict = field(default_factory=dict)


def start_port_forward():
    """Start kubectl port-forward and return the subprocess."""
    print(f"Starting port-forward to {PROM_SVC} in namespace {PROM_NS} on port {LOCAL_PORT}...")
    proc = subprocess.Popen(
        ["kubectl", "port-forward", "-n", PROM_NS, PROM_SVC, f"{LOCAL_PORT}:9090"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Wait for port-forward to be ready
    for attempt in range(30):
        try:
            req = urllib.request.Request(f"{PROM_URL}/-/ready")
            urllib.request.urlopen(req, timeout=2)
            print("Port-forward is ready.")
            return proc
        except Exception:
            time.sleep(1)
    print("ERROR: Port-forward did not become ready in 30 seconds.", file=sys.stderr)
    proc.kill()
    sys.exit(1)


def prom_query(expr: str) -> Optional[dict]:
    """Execute an instant query against Prometheus."""
    try:
        now = int(time.time())
        params = urllib.parse.urlencode({"query": expr, "time": now})
        url = f"{PROM_URL}/api/v1/query?{params}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"status": "error", "error": str(e)}


def prom_label_values(label: str) -> list:
    """Get all values for a label from Prometheus."""
    try:
        url = f"{PROM_URL}/api/v1/label/{label}/values"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            if data.get("status") == "success":
                return data.get("data", [])
    except Exception:
        pass
    return []


def prom_metric_labels(metric_name: str) -> dict:
    """Get label names and sample values for a specific metric."""
    try:
        # Query a single sample to see what labels exist
        params = urllib.parse.urlencode({"query": f"{metric_name}", "time": int(time.time())})
        url = f"{PROM_URL}/api/v1/query?{params}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            if data.get("status") == "success" and data.get("data", {}).get("result"):
                # Collect all label keys and sample values
                labels = {}
                for result in data["data"]["result"][:10]:  # sample up to 10
                    for k, v in result.get("metric", {}).items():
                        if k == "__name__":
                            continue
                        if k not in labels:
                            labels[k] = set()
                        labels[k].add(v)
                return {k: sorted(v) for k, v in labels.items()}
    except Exception:
        pass
    return {}


def replace_template_vars(expr: str) -> str:
    """Replace Grafana template variables with regex wildcards or remove them."""
    # ${varname:regex} -> .*
    expr = re.sub(r'\$\{[^}]+:regex\}', '.*', expr)
    # ${varname} or $varname in regex matchers (=~ or !~)
    # We need to handle label matchers: label=~"$var" -> label=~".*"
    # and label="$var" -> label=~".*"

    # First, replace inside =~ "..." and !~ "..." (regex context)
    def replace_in_regex_matcher(m):
        op = m.group(1)
        val = m.group(2)
        # Replace $var and ${var} with .*
        val = re.sub(r'\$\{[^}]+\}', '.*', val)
        val = re.sub(r'\$[a-zA-Z_][a-zA-Z0-9_]*', '.*', val)
        return f'{op}"{val}"'

    expr = re.sub(r'(=~|!~)\s*"([^"]*)"', replace_in_regex_matcher, expr)

    # For equality matchers: label="$var" -> label=~".*"
    def replace_in_eq_matcher(m):
        label = m.group(1)
        op = m.group(2)
        val = m.group(3)
        if re.search(r'\$\{?[a-zA-Z_]', val):
            val = re.sub(r'\$\{[^}]+\}', '.*', val)
            val = re.sub(r'\$[a-zA-Z_][a-zA-Z0-9_]*', '.*', val)
            # Switch to regex match
            if op == '=':
                return f'{label}=~"{val}"'
            elif op == '!=':
                return f'{label}!~"{val}"'
        return m.group(0)

    expr = re.sub(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*(=|!=)\s*"([^"]*)"', replace_in_eq_matcher, expr)

    # Handle $__rate_interval, $__interval, $__range -> 5m as fallback
    expr = re.sub(r'\$__rate_interval', '5m', expr)
    expr = re.sub(r'\$__interval', '1m', expr)
    expr = re.sub(r'\$__range', '1h', expr)

    # Handle any remaining $var references not inside quotes (shouldn't happen normally)
    # but be conservative here - only replace in label value positions

    return expr


def extract_metric_names(expr: str) -> list:
    """Extract metric names from a PromQL expression."""
    # Metric names are word characters (including colons for recording rules)
    # that appear before { or are standalone identifiers
    # Exclude PromQL functions and keywords
    functions = {
        'rate', 'irate', 'increase', 'sum', 'avg', 'min', 'max', 'count',
        'stddev', 'stdvar', 'topk', 'bottomk', 'quantile', 'count_values',
        'histogram_quantile', 'label_replace', 'label_join', 'sort', 'sort_desc',
        'abs', 'absent', 'ceil', 'floor', 'round', 'clamp', 'clamp_max', 'clamp_min',
        'delta', 'deriv', 'exp', 'ln', 'log2', 'log10', 'sqrt',
        'predict_linear', 'resets', 'changes', 'time', 'timestamp',
        'vector', 'scalar', 'sgn', 'sign', 'days_in_month', 'day_of_month',
        'day_of_week', 'day_of_year', 'hour', 'minute', 'month', 'year',
        'group', 'on', 'ignoring', 'by', 'without', 'offset', 'bool',
        'and', 'or', 'unless', 'inf', 'nan',
    }

    # Find all potential metric names: word chars (including :) followed by { or space
    candidates = re.findall(r'\b([a-zA-Z_:][a-zA-Z0-9_:]*)\s*(?:\{|\[|$|\s|,|\))', expr)
    # Also find standalone metrics that might be in binary expressions
    candidates += re.findall(r'\b([a-zA-Z_:][a-zA-Z0-9_:]*)\b', expr)

    metrics = set()
    for c in candidates:
        c_lower = c.lower()
        if c_lower not in functions and not c.startswith('__') and len(c) > 1:
            # Likely a metric name if it contains _ and doesn't look like a duration
            if re.match(r'^[0-9]', c):
                continue
            if c in ('le', 'by', 'without', 'on', 'ignoring', 'group_left',
                      'group_right', 'bool', 'offset', 'NaN', 'Inf'):
                continue
            metrics.add(c)
    return sorted(metrics)


def extract_label_filters(expr: str, metric_name: str) -> dict:
    """Extract label filters applied to a specific metric in the expression."""
    # Find the metric name followed by {filters}
    pattern = re.escape(metric_name) + r'\s*\{([^}]*)\}'
    matches = re.findall(pattern, expr)
    filters = {}
    for match in matches:
        # Parse individual label matchers
        for lm in re.finditer(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*(=~|!~|=|!=)\s*"([^"]*)"', match):
            label, op, val = lm.group(1), lm.group(2), lm.group(3)
            filters[label] = (op, val)
    return filters


def is_expected_empty(expr: str, panel_title: str) -> bool:
    """Check if a query is expected to potentially return empty results."""
    check_str = (expr + " " + panel_title).lower()
    for pattern in EXPECTED_EMPTY_PATTERNS:
        if re.search(pattern, check_str, re.IGNORECASE):
            return True
    return False


def parse_dashboard_yaml(yaml_path: str) -> Optional[dict]:
    """Parse a dashboard YAML file and extract the JSON dashboard spec."""
    with open(yaml_path, 'r') as f:
        content = f.read()

    # The YAML is a ConfigMap with data: containing a JSON string
    # We need to find the JSON content. It's under `data:` -> `<name>.json: |`
    # or it could be inline JSON

    # Find the JSON start - look for the first { after the `data:` section
    # Strategy: find lines after a key ending in .json:
    lines = content.split('\n')
    json_lines = []
    in_json = False
    json_indent = 0

    for line in lines:
        if not in_json:
            # Look for a key like `  something.json: |` or `  something.json: |-`
            m = re.match(r'^(\s+)\S+\.json:\s*\|?-?\s*$', line)
            if m:
                json_indent = len(m.group(1)) + 2  # content is indented further
                in_json = True
                continue
            # Or inline JSON: `  something.json: {`
            m = re.match(r'^(\s+)\S+\.json:\s*(\{.*)$', line)
            if m:
                json_indent = len(m.group(1)) + 2
                in_json = True
                json_lines.append(m.group(2))
                continue
        else:
            # Check if we've exited the JSON block (dedented)
            if line.strip() == '':
                json_lines.append('')
                continue
            stripped = line.lstrip()
            current_indent = len(line) - len(stripped)
            if current_indent < json_indent and stripped and not stripped.startswith('{') and not stripped.startswith('"') and not stripped.startswith('}') and not stripped.startswith('[') and not stripped.startswith(']'):
                break
            # Remove the base indentation
            if len(line) >= json_indent:
                json_lines.append(line[json_indent:])
            else:
                json_lines.append(line.lstrip())

    json_str = '\n'.join(json_lines).strip()
    if not json_str:
        return None

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"  WARNING: Failed to parse JSON from {yaml_path}: {e}", file=sys.stderr)
        return None


def extract_panels(dashboard: dict) -> list:
    """Recursively extract all panels from a dashboard, including those nested in rows."""
    panels = []

    def _walk(panel_list):
        for panel in panel_list:
            # Panel might have targets directly
            if 'targets' in panel:
                panels.append(panel)
            # Collapsed rows contain nested panels
            if panel.get('type') == 'row' and 'panels' in panel:
                _walk(panel['panels'])
            # Some panels have nested panels array
            elif 'panels' in panel and isinstance(panel['panels'], list):
                _walk(panel['panels'])

    if 'panels' in dashboard:
        _walk(dashboard['panels'])

    return panels


def diagnose_empty(expr: str, all_metric_names: set) -> tuple:
    """
    Diagnose why a query returned empty results.
    Returns (status, detail, metrics_info).
    """
    metric_names = extract_metric_names(expr)
    missing_metrics = []
    existing_metrics = []
    metrics_info = {}

    for mn in metric_names:
        if mn in all_metric_names:
            existing_metrics.append(mn)
        else:
            missing_metrics.append(mn)

    if missing_metrics and not existing_metrics:
        return (
            "METRIC_MISSING",
            f"Missing metrics: {', '.join(missing_metrics)}",
            {}
        )

    if missing_metrics:
        detail = f"Some metrics missing: {', '.join(missing_metrics)}. "
    else:
        detail = ""

    # For existing metrics, check what labels they have vs what's queried
    label_details = []
    for mn in existing_metrics:
        actual_labels = prom_metric_labels(mn)
        queried_filters = extract_label_filters(expr, mn)

        if actual_labels and queried_filters:
            mismatches = []
            for label, (op, val) in queried_filters.items():
                if label not in actual_labels:
                    mismatches.append(f"label '{label}' not found on metric (available: {', '.join(sorted(actual_labels.keys()))})")
                else:
                    sample_values = actual_labels[label][:5]
                    if op in ('=', '=~') and val == '.*':
                        pass  # wildcard, should match
                    else:
                        mismatches.append(f"label '{label}' {op} \"{val}\" (actual values sample: {sample_values})")

            if mismatches:
                label_details.append(f"  {mn}: {'; '.join(mismatches)}")

            metrics_info[mn] = {
                "actual_labels": {k: v[:5] for k, v in actual_labels.items()},
                "queried_filters": {k: f'{v[0]}"{v[1]}"' for k, v in queried_filters.items()},
            }

    if label_details:
        detail += "Label analysis:\n" + "\n".join(label_details)
    elif not missing_metrics:
        detail += "All metrics exist but query combination returns empty (may need different label values or time range)"

    status = "METRIC_MISSING" if missing_metrics and not existing_metrics else "NO_DATA"
    return status, detail.strip(), metrics_info


def verify_query(expr: str, panel_title: str, dashboard_name: str,
                 all_metric_names: set) -> QueryResult:
    """Verify a single PromQL expression."""
    # Replace template variables
    cleaned_expr = replace_template_vars(expr)

    result = prom_query(cleaned_expr)

    if result is None or result.get("status") == "error":
        err = result.get("error", "Unknown error") if result else "No response"
        return QueryResult(
            dashboard=dashboard_name,
            panel_title=panel_title,
            expr=expr,
            status="QUERY_ERROR",
            detail=f"Query error: {err}",
        )

    data = result.get("data", {})
    results = data.get("result", [])

    if results:
        return QueryResult(
            dashboard=dashboard_name,
            panel_title=panel_title,
            expr=expr,
            status="HAS_DATA",
            detail=f"{len(results)} series returned",
        )

    # Empty result - is this expected?
    if is_expected_empty(expr, panel_title):
        return QueryResult(
            dashboard=dashboard_name,
            panel_title=panel_title,
            expr=expr,
            status="EXPECTED_EMPTY",
            detail="Query returned empty but matches expected-empty pattern (error/failure counters, etc.)",
        )

    # Diagnose why it's empty
    status, detail, metrics_info = diagnose_empty(expr, all_metric_names)
    return QueryResult(
        dashboard=dashboard_name,
        panel_title=panel_title,
        expr=expr,
        status=status,
        detail=detail,
        metrics_info=metrics_info,
    )


def load_all_metric_names() -> set:
    """Load all known metric names from Prometheus."""
    print("Loading all metric names from Prometheus...")
    names = prom_label_values("__name__")
    print(f"  Found {len(names)} metrics.")
    return set(names)


STATUS_COLORS = {
    "HAS_DATA": "\033[32m",       # green
    "NO_DATA": "\033[31m",        # red
    "METRIC_MISSING": "\033[31;1m",  # bold red
    "EXPECTED_EMPTY": "\033[33m", # yellow
    "QUERY_ERROR": "\033[35m",    # magenta
}
RESET = "\033[0m"


def print_result(r: QueryResult, idx: int):
    """Print a single query result."""
    color = STATUS_COLORS.get(r.status, "")
    short_expr = r.expr.replace('\n', ' ').strip()
    if len(short_expr) > 120:
        short_expr = short_expr[:117] + "..."

    print(f"    [{idx}] {color}{r.status}{RESET}: {short_expr}")
    if r.detail and r.status not in ("HAS_DATA",):
        for line in r.detail.split('\n'):
            print(f"         {line}")


def main():
    # Start port-forward
    pf_proc = start_port_forward()

    try:
        # Load all metric names once
        all_metric_names = load_all_metric_names()

        # Find all dashboard YAMLs
        yaml_files = sorted(glob.glob(str(DASHBOARDS_DIR / "*.yaml")))
        if not yaml_files:
            print(f"ERROR: No YAML files found in {DASHBOARDS_DIR}", file=sys.stderr)
            sys.exit(1)

        print(f"\nFound {len(yaml_files)} dashboard files.\n")

        all_results = []

        for yaml_path in yaml_files:
            fname = os.path.basename(yaml_path)
            dashboard = parse_dashboard_yaml(yaml_path)
            if dashboard is None:
                print(f"SKIP: Could not parse {fname}")
                continue

            dashboard_title = dashboard.get("title", fname.replace(".yaml", ""))
            print(f"{'=' * 70}")
            print(f"Dashboard: {dashboard_title} ({fname})")
            print(f"{'=' * 70}")

            panels = extract_panels(dashboard)
            if not panels:
                print("  No panels with targets found.")
                continue

            query_idx = 0
            for panel in panels:
                panel_title = panel.get("title", "Untitled")
                targets = panel.get("targets", [])
                if not targets:
                    continue

                print(f"\n  Panel: {panel_title}")

                for target in targets:
                    expr = target.get("expr", "").strip()
                    if not expr:
                        continue

                    query_idx += 1
                    result = verify_query(expr, panel_title, dashboard_title, all_metric_names)
                    all_results.append(result)
                    print_result(result, query_idx)

            if query_idx == 0:
                print("  No PromQL expressions found.")
            print()

        # Summary
        print(f"\n{'=' * 70}")
        print("SUMMARY")
        print(f"{'=' * 70}")

        total = len(all_results)
        has_data = sum(1 for r in all_results if r.status == "HAS_DATA")
        no_data = sum(1 for r in all_results if r.status == "NO_DATA")
        missing = sum(1 for r in all_results if r.status == "METRIC_MISSING")
        expected_empty = sum(1 for r in all_results if r.status == "EXPECTED_EMPTY")
        errors = sum(1 for r in all_results if r.status == "QUERY_ERROR")

        print(f"  Total queries:       {total}")
        print(f"  {STATUS_COLORS['HAS_DATA']}HAS_DATA:{RESET}          {has_data}")
        print(f"  {STATUS_COLORS['EXPECTED_EMPTY']}EXPECTED_EMPTY:{RESET}    {expected_empty}")
        print(f"  {STATUS_COLORS['NO_DATA']}NO_DATA:{RESET}           {no_data}")
        print(f"  {STATUS_COLORS['METRIC_MISSING']}METRIC_MISSING:{RESET}    {missing}")
        if errors:
            print(f"  {STATUS_COLORS['QUERY_ERROR']}QUERY_ERROR:{RESET}       {errors}")

        # List problem queries
        problems = [r for r in all_results if r.status in ("NO_DATA", "METRIC_MISSING")]
        if problems:
            print(f"\n{'=' * 70}")
            print("PROBLEM QUERIES (NO_DATA or METRIC_MISSING)")
            print(f"{'=' * 70}")
            for r in problems:
                color = STATUS_COLORS.get(r.status, "")
                short_expr = r.expr.replace('\n', ' ').strip()
                if len(short_expr) > 100:
                    short_expr = short_expr[:97] + "..."
                print(f"\n  {color}{r.status}{RESET}: [{r.dashboard}] {r.panel_title}")
                print(f"    expr: {short_expr}")
                if r.detail:
                    for line in r.detail.split('\n'):
                        print(f"    {line}")

        # Exit code: non-zero if there are missing metrics
        if missing > 0:
            print(f"\nExiting with code 1 ({missing} queries have missing metrics).")
            sys.exit(1)
        else:
            print(f"\nAll metrics exist. {no_data} queries returned no data (may need different label values or time range).")

    finally:
        print("\nStopping port-forward...")
        pf_proc.terminate()
        try:
            pf_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pf_proc.kill()


if __name__ == "__main__":
    main()
