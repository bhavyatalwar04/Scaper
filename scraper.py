import json
import re
import time
import random
import logging
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.coventry.ac.uk"
AZ_LIST_URL = BASE_URL + "/study-at-coventry/postgraduate-study/az-course-list/"
OUTPUT_FILE = "courses_output.json"
TARGET_COUNT = 5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def _clean(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _get_soup(url, session):
    try:
        log.info(f"GET  {url}")
        resp = session.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as e:
        log.error(f"request failed: {e}")
        return None


def _main_content(soup):
    return soup.find("main") or soup.find(id="main") or soup


def _sidebar_value(soup, label):
    content = _main_content(soup)
    for tag in content.find_all(["h3", "h4"]):
        if label.lower() in _clean(tag.get_text()).lower():
            parent = tag.find_parent("div")
            if parent:
                txt = _clean(parent.get_text()).replace(_clean(tag.get_text()), "").strip()
                if txt:
                    return txt
    return ""


def discover_courses(session):
    log.info("--- discovering course URLs ---")
    soup = _get_soup(AZ_LIST_URL, session)
    if not soup:
        return []

    urls = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/course-structure/pg/" not in href:
            continue

        full_url = urljoin(BASE_URL, href)

        if "term=2025-26" in full_url or "/online/" in full_url:
            continue

        m = re.search(r"/course-structure/pg/[^/]+/([^/?]+)", full_url)
        if not m:
            continue
        slug = m.group(1)
        if slug in seen:
            continue
        seen.add(slug)
        urls.append(full_url)

    log.info(f"found {len(urls)} courses total")
    return urls


def _get_course_name(soup):
    title = soup.find("title")
    if title:
        t = _clean(title.get_text())
        if "|" in t:
            return t.split("|")[0].strip()
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        c = _clean(og["content"])
        return c.split("|")[0].strip() if "|" in c else c
    h1 = soup.find("h1")
    return _clean(h1.get_text()) if h1 else ""


def _get_uni_name(soup):
    title = soup.find("title")
    if title and "Coventry University" in title.get_text():
        return "Coventry University"
    og = soup.find("meta", property="og:site_name")
    if og and og.get("content"):
        return _clean(og["content"])
    return ""


def _get_address(soup):
    txt = soup.get_text()
    m = re.search(r"(Priory\s+Street\s+Coventry\s+CV\d\s*\d\w{2})\s*(United\s+Kingdom|UK)?", txt, re.I)
    if m:
        addr = _clean(m.group(1))
        if m.group(2):
            addr += ", " + _clean(m.group(2))
        return addr
    return ""


def _get_country(soup):
    footer = soup.find("footer")
    check = footer.get_text() if footer else soup.get_text()
    return "United Kingdom" if "United Kingdom" in check else ""


def _get_campus(soup):
    loc = _sidebar_value(soup, "Location")
    if loc:
        return loc
    for tag in _main_content(soup).find_all(["span", "p", "div"]):
        t = _clean(tag.get_text())
        if "Coventry University" in t and len(t) < 80:
            return t
    return ""


def _get_duration(soup):
    d = _sidebar_value(soup, "Duration")
    if d:
        return d
    txt = _main_content(soup).get_text()
    for pat in [r"(\d+\s*years?\s*(?:full[- ]?time|part[- ]?time))",
                r"(\d+\s*months?\s*(?:full[- ]?time|part[- ]?time))"]:
        m = re.search(pat, txt, re.I)
        if m:
            return _clean(m.group(1))
    return ""


def _get_study_level(soup, url):
    if "/pg/" not in url:
        return "Undergraduate" if "/ug/" in url else ""
    title = soup.find("title")
    title_txt = _clean(title.get_text()) if title else ""
    for deg in ["MBA", "MSc", "MA", "MArch", "LLM", "MRes", "PhD"]:
        if deg in title_txt:
            return f"Postgraduate ({deg})"
    return "Postgraduate"


def _get_start_dates(soup):
    return _sidebar_value(soup, "Start date") or _sidebar_value(soup, "Start") or ""


def _parse_entry_reqs(soup):
    result = {"entry_text": "", "english_text": ""}
    content = _main_content(soup)

    for heading in content.find_all(["h2", "h3"]):
        htxt = _clean(heading.get_text()).lower()

        if "entry requirement" in htxt:
            parts = []
            sib = heading.find_next_sibling()
            while sib and sib.name != "h2":
                t = _clean(sib.get_text())
                if t and len(t) < 1000:
                    parts.append(t)
                sib = sib.find_next_sibling()
            result["entry_text"] = " ".join(parts)

        elif "english language" in htxt:
            parts = []
            sib = heading.find_next_sibling()
            while sib and sib.name not in ("h2", "h3"):
                t = _clean(sib.get_text())
                if t and len(t) < 500:
                    parts.append(t)
                sib = sib.find_next_sibling()
            result["english_text"] = " ".join(parts)

    return result


def _parse_fees(soup):
    content = _main_content(soup)
    txt = content.get_text()
    out = {"uk": "", "intl": "", "scholarships": ""}

    for pat in [r"international[^£]{0,50}(£[\d,]+)", r"(?:international|overseas)[^£]{0,80}(£[\d,]+)"]:
        m = re.search(pat, txt, re.I)
        if m:
            out["intl"] = m.group(1)
            break

    if not out["intl"]:
        for tag in content.find_all(["td", "span", "p"]):
            t = _clean(tag.get_text())
            if "international" in t.lower() and "£" in t and len(t) < 200:
                fm = re.search(r"£[\d,]+", t)
                if fm:
                    out["intl"] = fm.group(0)
                    break

    m = re.search(r"uk[^£]{0,50}(£[\d,]+)", txt, re.I)
    if m:
        out["uk"] = m.group(1)

    schol_bits = []
    for a in content.find_all("a", href=True):
        atxt = _clean(a.get_text())
        if ("scholarship" in atxt.lower() or "scholarship" in a["href"].lower()) and 10 < len(atxt) < 200:
            schol_bits.append(atxt)

    if not schol_bits:
        for p in content.find_all(["p", "li"]):
            t = _clean(p.get_text())
            if "scholarship" in t.lower() and 20 < len(t) < 300:
                schol_bits.append(t)

    unique = list(dict.fromkeys(schol_bits))
    out["scholarships"] = " | ".join(unique[:3])

    return out


def _regex_score(label, text):
    m = re.search(rf"\b{label}\b[^.]*?(\d{{2,3}})", text, re.I)
    return m.group(0).strip() if m else ""


def _find_ielts(text):
    m = re.search(r"IELTS[:\s]*(\d+\.?\d?)\s*(?:overall)?[^.]*", text, re.I)
    return m.group(0).strip() if m else ""


def scrape_course(url, session):
    soup = _get_soup(url, session)
    if not soup:
        return None

    content = _main_content(soup)
    page_text = content.get_text()
    reqs = _parse_entry_reqs(soup)
    fees = _parse_fees(soup)

    eng_text = reqs["english_text"]
    req_text = reqs["entry_text"]

    data = {
        "program_course_name": _get_course_name(soup),
        "university_name": _get_uni_name(soup),
        "course_website_url": url,
        "campus": _get_campus(soup),
        "country": _get_country(soup),
        "address": _get_address(soup),
        "study_level": _get_study_level(soup, url),
        "course_duration": _get_duration(soup),
        "all_intakes_available": _get_start_dates(soup),
        "mandatory_documents_required": req_text[:500] if req_text else "",
        "yearly_tuition_fee": fees["intl"] or fees["uk"] or "",
        "scholarship_availability": fees["scholarships"] or "",
        "gre_gmat_mandatory_min_score": "",
        "indian_regional_institution_restrictions": "",
        "class_12_boards_accepted": "",
        "gap_year_max_accepted": "",
        "min_duolingo": _regex_score("Duolingo", eng_text) or _regex_score("Duolingo", page_text) or "",
        "english_waiver_class12": "",
        "english_waiver_moi": "",
        "min_ielts": _find_ielts(eng_text) or _find_ielts(page_text) or "",
        "kaplan_test_of_english": "",
        "min_pte": _regex_score("PTE", eng_text) or _regex_score("PTE", page_text) or "",
        "min_toefl": _regex_score("TOEFL", eng_text) or _regex_score("TOEFL", page_text) or "",
        "ug_academic_min_gpa": "",
        "twelfth_pass_min_cgpa": "",
        "mandatory_work_exp": "",
        "max_backlogs": "",
    }

    for pat in [r"(?:require|need|must have|minimum of)\s+([\w\s]*work experience[^.]{0,100}\.)",
                r"(\d+\s*years?\s*(?:of\s+)?(?:relevant\s+)?(?:work|professional|industry)\s+experience[^.]*\.)"]:
        m = re.search(pat, page_text, re.I)
        if m:
            hit = _clean(m.group(0))
            if "field trips" not in hit.lower() and "competitive application" not in hit.lower():
                data["mandatory_work_exp"] = hit
                break

    for pat in [r"((?:first|second|2:1|2:2|third)[\s-]*class[^.]*\.)",
                r"(minimum\s+of\s+\d+%[^.]*\.)",
                r"(\d+\.?\d*\s*GPA[^.]*\.)"]:
        m = re.search(pat, req_text or page_text, re.I)
        if m:
            data["ug_academic_min_gpa"] = _clean(m.group(1))
            break

    log.info(f"  -> {data['program_course_name']}")
    return data


def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log.info(f"saved {len(data)} courses to {path}")


def main():
    session = requests.Session()

    all_urls = discover_courses(session)
    if not all_urls:
        log.error("no courses found, exiting")
        return

    urls = all_urls[:TARGET_COUNT]
    log.info(f"scraping {len(urls)} courses:\n" + "\n".join(f"  {i+1}. {u}" for i, u in enumerate(urls)))

    results = []
    for i, url in enumerate(urls):
        log.info(f"\n[{i+1}/{len(urls)}]")
        course = scrape_course(url, session)
        if course:
            results.append(course)
        else:
            log.warning("  skipped (failed)")

        if i < len(urls) - 1:
            time.sleep(random.uniform(1.5, 3.0))

    if results:
        save_json(results, OUTPUT_FILE)
        print(f"\ndone - {len(results)} courses written to {OUTPUT_FILE}")
    else:
        log.error("nothing scraped successfully")

    for i, c in enumerate(results, 1):
        print(f"  {i}. {c['program_course_name']}  |  {c['course_duration']}  |  {c['yearly_tuition_fee']}")


if __name__ == "__main__":
    main()
