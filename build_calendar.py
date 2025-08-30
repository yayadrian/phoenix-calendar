#!/usr/bin/env python3
import hashlib, time, re, sys, datetime as dt
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event

BASE = "https://www.phoenix.org.uk"
WHATSON = f"{BASE}/whats-on/"
TZ = ZoneInfo("Europe/London")
HEADERS = {"User-Agent": "PhoenixICalBot/1.0 (+github.com/yayadrian/phoenix-ical)"}

# Build a resilient session with retries/backoff to tolerate transient timeouts in CI
def _build_session():
    # Import locally to keep top-level imports minimal and resilient
    session = requests.Session()
    try:
        import importlib
        HTTPAdapter = getattr(importlib.import_module("requests.adapters"), "HTTPAdapter")
        Retry = getattr(importlib.import_module("urllib3.util.retry"), "Retry")
        # Handle urllib3 v1 vs v2 differences (allowed_methods vs method_whitelist)
        retry_kwargs = dict(
            total=5,
            connect=3,
            read=3,
            backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            raise_on_status=False,
        )
        try:
            # urllib3 v2
            retries = Retry(allowed_methods={"HEAD", "GET", "OPTIONS"}, **retry_kwargs)
        except TypeError:
            # urllib3 v1
            retries = Retry(method_whitelist={"HEAD", "GET", "OPTIONS"}, **retry_kwargs)  # type: ignore[arg-type]
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
    except Exception:
        # Fallback: plain session (no retries)
        pass
    session.headers.update(HEADERS)
    return session

SESSION = _build_session()

def get_soup(url):
    # Split connect/read timeouts: tolerate slower responses on GitHub-hosted runners
    r = SESSION.get(url, timeout=(10, 45))
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def iter_whats_on_pages():
    # Page 1, then follow ?pageno=2,3,... until “Next” disappears
    page = 1
    while True:
        url = WHATSON if page == 1 else f"{WHATSON}?pageno={page}"
        soup = get_soup(url)
        yield soup
        next_link = soup.find("a", string=re.compile(r"Next", re.I))
        if not next_link:
            break
        page += 1
        time.sleep(1.5)

def find_programme_links(soup):
    # Programme pages look like /whats-on/programme/<slug>/
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/whats-on/programme/" in href:
            links.add(requests.compat.urljoin(BASE, href))
    return sorted(links)

def parse_duration_minutes(soup):
    # On programme page: "Duration: 109 mins"
    text = soup.get_text(" ", strip=True)
    m = re.search(r"Duration:\s*(\d+)\s*mins", text, re.I)
    return int(m.group(1)) if m else 120  # sensible default

def parse_certificate(soup):
    # Heading often shows certificate after title; also appears as “Certificate: 15”
    text = soup.get_text(" ", strip=True)
    m = re.search(r"Certificate:\s*([A-Z0-9+]{1,4})", text, re.I)
    if m:
        return m.group(1)
    # fallback: try title block like “Caught Stealing  15”
    h1 = soup.find(["h1","h2"])
    if h1:
        m2 = re.search(r"\b(U|PG|12A|12|15|18)\b", h1.get_text(" ", strip=True))
        if m2:
            return m2.group(1)
    return ""

def parse_description(soup):
    # Grab the first descriptive paragraph under the header
    # Keep it short to avoid giant ICS fields
    paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    for p in paras:
        if len(p) > 40:
            return p[:800]  # trim
    return ""

def parse_times_and_dates(soup):
    # The “Times & tickets” section lists date headings like “Sun 31 Aug”
    # followed by a row of <a> links with times (“12.00pm”, etc.).
    events = []
    h2s = soup.find_all(["h2","h3"])
    # Find the “Times & tickets” header
    start_index = None
    for i,h in enumerate(h2s):
        if "Times & tickets" in h.get_text():
            start_index = i
            break
    if start_index is None:
        return events

    # From there, parse the subsequent date blocks until the next strong section
    block = h2s[start_index].parent
    # fallback: just scan following siblings
    current_date = None
    for node in block.find_all_next():
        txt = node.get_text(" ", strip=True)
        # Date line like "Sun 31 Aug" or "Mon 1 Sep"
        if re.match(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b", txt):
            # Extract a concrete date with year. If month/day lacks year, assume current year or next if past.
            # We’ll parse with day+mon name; add year heuristically.
            current_date = txt.split(" ")[1:]  # ['31','Aug'] or ['1','Sep,','7pm'] etc
            # Just keep the full string and re-extract carefully:
            current_date_str = re.sub(r",.*$", "", txt)  # "Sun 31 Aug"
            current_date = current_date_str

        # Time links for that date
        if node.name == "a" and node.has_attr("href"):
            time_str = node.get_text(strip=True)
            if re.match(r"^\d{1,2}\.\d{2}(am|pm)$", time_str, re.I) and current_date:
                events.append((current_date, time_str, requests.compat.urljoin(BASE, node["href"])))
        # Stop if we hit another big page section like “Screening Key”
        if node.name in ("h2","h3") and "Screening Key" in txt:
            break

    # Convert date strings to YYYY-MM-DD with year disambiguation
    resolved = []
    today = dt.date.today()
    this_year = today.year
    month_map = {m.lower(): i for i,m in enumerate(["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], start=1)}
    for dlabel, tlabel, href in events:
        # dlabel like "Sun 31 Aug"
        m = re.match(r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\d{1,2})\s+([A-Za-z]{3})", dlabel)
        if not m:
            continue
        day = int(m.group(1))
        mon = month_map[m.group(2).lower()]
        # Pick a year: if that date has already passed this calendar year (relative to today), roll forward 1 year.
        year = this_year
        try_date = dt.date(year, mon, day)
        if try_date < today - dt.timedelta(days=2):
            year += 1
            try_date = dt.date(year, mon, day)

        # time like "5.30pm" → 17:30
        tm = re.match(r"^(\d{1,2})\.(\d{2})(am|pm)$", tlabel, re.I)
        if not tm:
            continue
        hh = int(tm.group(1)) % 12
        mm = int(tm.group(2))
        if tm.group(3).lower() == "pm":
            hh += 12
        start_dt = dt.datetime(year, mon, day, hh, mm, tzinfo=TZ)
        resolved.append((start_dt, href))
    return resolved

def make_uid(title, start_dt, href):
    base = f"{title}|{start_dt.isoformat()}|{href}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest() + "@phoenix-leicester"

def build_calendar():
    cal = Calendar()
    cal.add("prodid", "-//Phoenix Leicester iCal//EN")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", "Phoenix Leicester — What’s On")
    cal.add("x-wr-timezone", "Europe/London")

    # Gather programme pages
    programme_urls = set()
    for soup in iter_whats_on_pages():
        programme_urls |= set(find_programme_links(soup))
        time.sleep(1.5)

    for url in sorted(programme_urls):
        psoup = get_soup(url)
        title_el = psoup.find(["h1","h2"])
        title = title_el.get_text(" ", strip=True) if title_el else "Phoenix Screening"
        # Strip trailing cert from title in H1 (we’ll add our own formatted summary)
        title = re.sub(r"\s+\b(U|PG|12A|12|15|18)\b$", "", title)
        cert = parse_certificate(psoup)
        desc = parse_description(psoup)
        dur = parse_duration_minutes(psoup)

        for start_dt, href in parse_times_and_dates(psoup):
            ev = Event()
            ev.add("uid", make_uid(title, start_dt, href))
            ev.add("summary", f"{title}" + (f" ({cert})" if cert else ""))
            ev.add("dtstart", start_dt)
            ev.add("dtend", start_dt + dt.timedelta(minutes=dur))
            ev.add("location", "Phoenix, 4 Midland Street, Leicester LE1 1TG")
            ev.add("url", href)
            if desc:
                ev.add("description", desc)
            cal.add_component(ev)
    time.sleep(1.5)

    return cal

if __name__ == "__main__":
    cal = build_calendar()
    out = "phoenix.ics" if len(sys.argv) < 2 else sys.argv[1]
    with open(out, "wb") as f:
        f.write(cal.to_ical())
    print(f"Wrote {out}")
