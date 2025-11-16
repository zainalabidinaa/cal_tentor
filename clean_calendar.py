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
]

def clean_event_summary(summary):
    """
    Extracts Moment ONLY when it's a real field.
    Keeps full event name otherwise.
    """
    if summary is None:
        return ""

    # Remove Aktivitetstyp lines
    summary = re.sub(r'Aktivitetstyp[: ]*.*', '', summary)

    # Remove unwanted course codes (keep BMA451)
    for code in ["BMA401", "BMK101", "KUBM26"]:
        summary = re.sub(r'\b' + code + r'\b,?\s*', '', summary)

    # STRICT Moment block (must be real field, not broken text)
    moment_match = re.search(r'\bMoment:\s*(.+)$', summary)
    if moment_match:
        moment_text = moment_match.group(1).strip()
        if moment_text.startswith("Laboration Klinisk hematologi:"):
            moment_text = re.sub(r':\s*Okänd$', '', moment_text)
        return moment_text.strip()

    # Otherwise keep full summary
    return summary.strip()


def should_keep_event(raw_summary: str) -> bool:
    """
    Filters events:
    - Always keep BMA451 events
    - Otherwise only keep exam-related keywords
    """
    if raw_summary is None:
        return False

    text = raw_summary.lower()

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

        cleaned_summary = clean_event_summary(raw_summary)

        evt = Event()
        evt.add('summary', cleaned_summary)
        evt.add('dtstart', comp.get('dtstart'))
        evt.add('dtend', comp.get('dtend'))
        evt.add('location', comp.get('location', ''))
        evt.add('description', comp.get('description', ''))

        clean_cal.add_component(evt)

    return clean_cal.to_ical()

if __name__ == "__main__":
    print(clean_calendar().decode("utf-8"))
