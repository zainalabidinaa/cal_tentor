import os
import requests
import re
from icalendar import Calendar, Event

ICS_URL = os.environ.get('ICS_URL')
if not ICS_URL:
    raise ValueError("Missing ICS_URL variable.")

KEYWORDS = [
    "omtentamen",
    "salstentamen",
    "tentamen",
    "muntlig tentamen",
    "dugga",
    "examination",
    "omexamination",
    "frågestund",
    "ominlämning",
]

# When multiple course codes appear in a Moment, keep the first match here
PREFERRED_COURSES = ["BMA451", "BMA452", "BMA352", "BMA201", "BMA153", "BMA052", "BMA402"]

# Regex to find any BMA/BMK/KUBM course code
COURSE_CODE_RE = re.compile(r'\b(BMA\d{3}|BMK\d{3}|KUBM\d{2})\b')

# Kurs.grp keyword → preferred course code (order matters: most specific first)
KURSGRP_TO_CODE = [
    ('cellbiologi', 'BMA201'),
    ('biomedicinsk laboratorievetenskap ii', 'BMA452'),
    ('laboratorievetenskap ii', 'BMA153'),
    ('proteinkemi och analysmetoder', 'BMA052'),
    ('laboratoriemedicin', 'BMA352'),
]

# Boilerplate text — truncate here (keep the phrase itself, drop everything after)
TRUNCATE_AFTER = "Ingen sen ankomst efter start är tillåten!"


def extract_kursgrp_code(raw_summary: str):
    """
    Read the 'Kurs.grp:' field from the raw SUMMARY string and map it
    to a known BMA course code. Returns None if no match.
    """
    match = re.search(r'Kurs\.grp:\s*(.+?)(?=\s+Sign:|\s+Moment:|$)', raw_summary)
    if not match:
        return None
    kursgrp_text = match.group(1).lower()
    for keyword, code in KURSGRP_TO_CODE:
        if keyword in kursgrp_text:
            return code
    return None


def simplify_moment(moment: str) -> str:
    """
    Clean up an extracted Moment string:
    - Truncate long Inspera disclaimer after the 'no late entry' sentence.
    - Strip sala seating/room placement info (e.g. 'Placering14-425 Alla A-Ö …').
    - When multiple course codes appear, keep only the preferred one.
    - Remove a trailing '(Dpx)' that duplicates info already in the text.
    """
    # 1. Truncate Inspera boilerplate
    cut_idx = moment.find(TRUNCATE_AFTER)
    if cut_idx != -1:
        moment = moment[:cut_idx + len(TRUNCATE_AFTER)]

    # 2. Strip sala seating info that runs on directly after 'Salstentamen'
    moment = re.sub(r'\s*Placering.*', '', moment, flags=re.DOTALL)

    # 3. Prefer one course code when multiple are listed
    codes_found = COURSE_CODE_RE.findall(moment)
    if len(codes_found) > 1:
        preferred = next((c for c in PREFERRED_COURSES if c in codes_found), codes_found[0])
        for code in codes_found:
            if code != preferred:
                moment = re.sub(r'\b' + re.escape(code) + r'\b,?\s*', '', moment)

    # 4. Remove trailing '(Dpx)' duplication e.g. 'Frågestund: inför Dp4 (Dp4)'
    moment = re.sub(r'\s*\(Dp\d+\)\s*$', '', moment)

    # 5. Tidy up stray commas / whitespace
    moment = re.sub(r',\s*,', ',', moment)
    moment = moment.strip().strip(',').strip()

    return moment


def clean_event_summary(raw_summary):
    """
    Extract and clean the Moment field from the raw SUMMARY.
    The SUMMARY from HKR's ICS looks like:
      Program: … Kurs.grp: … Sign: … Moment: <content> Aktivitetstyp: …
    Returns just the cleaned <content>.
    """
    if raw_summary is None:
        return ""

    summary = str(raw_summary)

    # Drop everything from 'Aktivitetstyp' onward
    summary = re.sub(r'\s*Aktivitetstyp[: ].*', '', summary, flags=re.DOTALL)

    # Extract the Moment field
    moment_match = re.search(r'\bMoment:\s*(.+)', summary, re.DOTALL)
    if moment_match:
        return simplify_moment(moment_match.group(1).strip())

    # Fallback: return whatever is left (should not happen for well-formed events)
    return summary.strip()


def should_keep_event(raw_summary: str) -> bool:
    """
    Keep an event if it is BMA451-related or contains an exam keyword.
    """
    if raw_summary is None:
        return False
    text = str(raw_summary).lower()
    if "bma451" in text:
        return True
    return any(k in text for k in KEYWORDS)


def clean_calendar():
    response = requests.get(ICS_URL)
    response.raise_for_status()
    original = Calendar.from_ical(response.text)

    clean_cal = Calendar()
    clean_cal.add('prodid', '-//Cleaned HKR Calendar//EN')
    clean_cal.add('version', '2.0')

    for comp in original.walk():
        if comp.name != "VEVENT":
            continue

        raw_summary = comp.get('summary')

        if not should_keep_event(raw_summary):
            continue

        cleaned_moment = clean_event_summary(raw_summary)

        # If the cleaned moment has no course code at the start, derive one
        # from the Kurs.grp field and prepend it.
        if not COURSE_CODE_RE.match(cleaned_moment):
            course = extract_kursgrp_code(str(raw_summary))
            if course:
                cleaned_moment = f"{course}: {cleaned_moment}"

        evt = Event()
        evt.add('summary', cleaned_moment)
        evt.add('dtstart', comp.get('dtstart'))
        evt.add('dtend', comp.get('dtend'))
        evt.add('location', comp.get('location', ''))
        evt.add('description', comp.get('description', ''))

        clean_cal.add_component(evt)

    return clean_cal.to_ical()


if __name__ == "__main__":
    print(clean_calendar().decode("utf-8"))
