# phoenix-calendar

A polite web scraper that presents the Phoenix Leicester Cinema

## How to run

This script scrapes Phoenix Leicester's listings and writes an iCalendar file.

- Output: creates `phoenix.ics` by default, or pass a custom filename as the first argument.
- Requirements: Python 3.9+ and the packages `requests`, `beautifulsoup4`, and `icalendar`.

### Option A: one-shot with uv (no manual venv)

```sh
uv run --with requests --with beautifulsoup4 --with icalendar build_calendar.py

# with a custom output path
uv run --with requests --with beautifulsoup4 --with icalendar build_calendar.py my_calendar.ics
```

### Option B: standard venv + pip

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install requests beautifulsoup4 icalendar

# run the script
python build_calendar.py            # writes phoenix.ics
python build_calendar.py out.ics    # writes out.ics
```

Notes

- The scraper is throttled with brief pauses between requests to be polite.
- If the cinema changes page structure, parsing may need small tweaks.
