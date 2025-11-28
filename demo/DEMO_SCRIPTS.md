# pytest-chronicle Demo Scripts

Manual scripts for recording demo videos. Run these commands in a terminal.

## Setup (Before Recording)

```bash
cd demo-workspace
source .venv/bin/activate
export PS1='$ '
clear
```

---

## Short Demo (~40 seconds)

Optimized for GIF/social media. Shows the key features quickly.

### Scene 1: Intro (5s)
```bash
# pytest-chronicle — track your test history
ls *.py
```

### Scene 2: Timeline (6s)
```bash
pytest-chronicle query timeline --runs 3 -t --compact
```

### Scene 3: Flaky Tests (6s)
```bash
pytest-chronicle query stats --sort-by failure-rate --limit 3
```

### Scene 3b: Filter with -k (4s)
```bash
# Filter tests like pytest -k
pytest-chronicle query last-red -k edge_case --limit 3
```

### Scene 4: Slow Tests (6s)
```bash
pytest-chronicle query slowest --limit 3
```

### Scene 5: Error Details (6s)
```bash
pytest-chronicle query errors --limit 1
```

### Scene 6: CTA (5s)
```bash
clear
pip install pytest-chronicle
```

---

## Full Demo (~3-4 minutes)

Comprehensive walkthrough for YouTube or documentation.

### Part 1: Intro (20s)
```bash
# pytest-chronicle - Track your test history
ls *.py
head -25 test_mathops.py
```

### Part 2: Auto-Ingestion (20s)
```bash
clear
# Run pytest - results auto-ingest
pytest test_mathops.py -q
```

### Part 3: Core Queries (90s)

```bash
clear
# Query: Recent failures
pytest-chronicle query last-red --limit 5
```

```bash
# Query: Recent passes
pytest-chronicle query last-green --limit 5
```

```bash
clear
# Query: Error details with tracebacks
pytest-chronicle query errors --limit 3
```

```bash
clear
# Query: Visual timeline
pytest-chronicle query timeline --runs 5 -t
```

### Part 4: Advanced Features (60s)

```bash
clear
# Advanced: Flaky test detection
pytest-chronicle query stats --sort-by failure-rate
```

```bash
# Advanced: Performance analysis
pytest-chronicle query slowest --limit 5
```

```bash
clear
# Advanced: Branch comparison
pytest-chronicle query compare --branch main --branch feature/new-api --only-diff
```

### Part 5: Outro (15s)
```bash
clear
# Install: pip install pytest-chronicle
```

---

## Feature Demos (Individual)

### Timeline with Times
```bash
# Visual timeline of test runs
pytest-chronicle query timeline --runs 10 -t

# Compact mode for tighter display
pytest-chronicle query timeline --runs 10 -t --compact
```

### Failure Analysis
```bash
# Find recent test failures
pytest-chronicle query last-red --limit 5

# Get error details with tracebacks
pytest-chronicle query errors --limit 3

# Filter by keyword like pytest -k
pytest-chronicle query last-red -k "divide"
```

### Flaky Test Detection
```bash
# Find flaky tests by failure rate
pytest-chronicle query stats --sort-by failure-rate

# Filter by time range
pytest-chronicle query stats --since 1h --sort-by failure-rate

# Minimum runs filter removes low-sample tests
pytest-chronicle query stats --min-runs 3 --sort-by failure-rate
```

### Performance Analysis
```bash
# Find slowest tests (yellow ≥1s, red ≥5s)
pytest-chronicle query slowest --limit 10

# Slowest failures only
pytest-chronicle query slowest --status failed --limit 5

# Sort stats by average time
pytest-chronicle query stats --sort-by avg-time --limit 5
```

### Branch Comparison
```bash
# Compare test results across branches
pytest-chronicle query compare --branch main --branch feature/new-api

# Show only tests that differ
pytest-chronicle query compare --branch main --branch feature/new-api --only-diff

# Tests that flipped from red to green
pytest-chronicle query flipped-green
```

### JSON Output
```bash
# JSON output for scripting
pytest-chronicle query last-red --format json --pretty | head -25

# Stats as JSON
pytest-chronicle query stats --format json --pretty | head -20
```
