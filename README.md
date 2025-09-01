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
pip install -r requirements.txt

# run the script
python build_calendar.py            # writes phoenix.ics
python build_calendar.py out.ics    # writes out.ics
```

Notes

- The scraper is throttled with brief pauses between requests to be polite.
- If the cinema changes page structure, parsing may need small tweaks.

## Automated Updates

This repository includes a GitHub Actions workflow that automatically:

- Runs daily at 05:07 UTC (05:07 Europe/London) 
- Scrapes the latest Phoenix Leicester listings
- Updates the `phoenix.ics` file if changes are detected
- Commits and pushes changes automatically

The workflow is designed to be robust and handles:
- Network timeouts and transient failures (with built-in retries)
- No-change scenarios (skips unnecessary commits)  
- Git conflicts (with automatic resolution)
- Build timeouts (15-minute limit with 10-minute scraping timeout)

You can also trigger the workflow manually from the Actions tab in GitHub.
