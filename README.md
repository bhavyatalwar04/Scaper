# Coventry University Course Scraper

Scrapes postgraduate course details from [coventry.ac.uk](https://www.coventry.ac.uk/) and saves them as JSON.

Only uses official university pages — no third-party sites.

## Setup

Requires Python 3.10+

```bash
pip install -r requirements.txt
```

## Usage

```bash
python scraper.py
```

This will:
- Pull course links from the [PG A-Z listing](https://www.coventry.ac.uk/study-at-coventry/postgraduate-study/az-course-list/)
- Pick the first 5 unique courses
- Scrape each page and write `courses_output.json`

Adds a 1.5-3s delay between requests to not hammer the server.

## Output

`courses_output.json` — array of 5 course objects. Each has these keys:

| Key | What it is |
|-----|-----------|
| `program_course_name` | e.g. "MSc Accounting and Financial Management" |
| `university_name` | Always "Coventry University" |
| `course_website_url` | Link to the course page |
| `campus` | Which campus(es) |
| `country` | "United Kingdom" |
| `address` | Physical address from the footer |
| `study_level` | "Postgraduate (MSc)", "Postgraduate (MBA)" etc. |
| `course_duration` | "1 year full-time", "3 years part-time" etc. |
| `all_intakes_available` | Start dates listed on the page |
| `mandatory_documents_required` | Entry requirements text (first 500 chars) |
| `yearly_tuition_fee` | International fee preferred, falls back to UK |
| `scholarship_availability` | Any scholarship mentions found |
| `min_ielts` | IELTS requirement if listed |
| `min_pte` | PTE score if listed |
| `min_toefl` | TOEFL score if listed |
| `min_duolingo` | Duolingo score if listed |
| `ug_academic_min_gpa` | Academic grade requirement |
| `mandatory_work_exp` | Work experience requirement if mentioned |

Fields not available on the page are set to `"NA"`. There are 27 keys total — the rest (GRE/GMAT, backlogs, class 12 boards, etc.) are always `"NA"` since Coventry doesn't list those.

## Files

```
scraper.py            - the scraper
requirements.txt      - dependencies
README.md             - you're reading it
courses_output.json   - generated output
```

## Notes

- Only scrapes `coventry.ac.uk` domain
- Deduplicates courses by URL slug
- Skips online-only courses
- Uses BeautifulSoup with the built-in html.parser (no lxml needed)
- If a page fails to load it just skips it and moves on
