# pytest-chronicle demo script (for GIF/recording)

This walkthrough shows a failing test, timeline inspection, a fix, and a green rerun—all using the default local SQLite backend.

## One-time setup
```bash
pytest-chronicle init --project demo --suite pytest   # creates .pytest-chronicle.toml + local sqlite
```

Create the files:

`mathops.py`
```python
def divide_and_offset(x: int) -> float:
    # Buggy: division by zero when x == 0
    return (10 / x) + 1
```

`test_mathops.py`
```python
import pytest
from mathops import divide_and_offset

@pytest.mark.parametrize(
    "x,expected",
    [
        (5, 3.0),
        (2, 6.0),
        (0, 1.0),  # blows up
    ],
)
def test_divide_and_offset(x, expected):
    assert divide_and_offset(x) == pytest.approx(expected)
```

## Phase 1 – fail and ingest
```bash
clear
pytest -q                                  # plugin auto-ingests into local sqlite
pytest-chronicle query errors --format text
pytest-chronicle query timeline --runs 5 --max-tests 10 --compact
pytest-chronicle query flipped-green --format text
```
Expect: ZeroDivisionError in errors; timeline row shows E/F on latest run; flipped-green empty.

## Phase 2 – fix the bug
Edit `mathops.py`:
```python
def divide_and_offset(x: int) -> float:
    if x == 0:
        return 1.0  # graceful fallback
    return (10 / x) + 1
```

## Phase 3 – rerun and confirm green
```bash
clear
pytest -q
pytest-chronicle query last-red --format text
pytest-chronicle query flipped-green --format text
pytest-chronicle query timeline --runs 5 --max-tests 10 --compact
```
Expect: last-red empty for this test, flipped-green shows the new run, timeline shows the flip to P on the latest column.

## Recording tips
- Keep terminal width modest; `--compact` keeps the timeline sparkline tight.
- Use `clear` between phases to separate scenes.
- Brief pauses after each command make the GIF easier to follow.
