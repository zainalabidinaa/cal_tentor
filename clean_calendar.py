import os
import requests
import re
from icalendar import Calendar, Event

# Retrieve the ICS_URL from environment variables
ICS_URL = os.environ.get('ICS_URL')

# Optional: Check if the variable is set and raise an error if not
if not ICS_URL:
    raise ValueError("Missing ICS_URL environment variable. Please set it in your Render dashboard.")

# Nyckelord för vilka events som ska behållas
KEYWORDS = [
    "omtentamen",
    "salstentamen",
    "tentamen",
    "muntlig tentamen",
    "dugga",
]

def clean_event_summary(summary):
    """
    Rensar händelsens sammanfattning enligt följande:
      - Tar bort strängen 'Aktivitetstyp'.
      - Tar bort oönskade kurskoder (BMA401, BMK101, KUBM26) men behåller BMA451.
      - Om sammanfattningen innehåller 'Moment:' extraheras texten efter detta.
         - Om den extraherade texten börjar med "Laboration Klinisk hematologi:" tas en avslutande " : Okänd" bort.
         - För andra fall extraheras texten upp till första kolon.
    """
    if summary is None:
        return ""

    # Ta bort 'Aktivitetstyp'
    summary = re.sub(r'Aktivitetstyp', '', summary)
    
    # Ta bort oönskade kurskoder (behåller BMA451)
    undesired_codes = ["BMA401", "BMK101", "KUBM26"]
    for code in undesired_codes:
        summary = re.sub(r'\b' + code + r'\b,?\s*', '', summary)
    
    # Rensa eventuella inledande kommatecken
    summary = re.sub(r'^\s*,\s*', '', summary)
    
    # Om texten innehåller "Moment:" så extrahera det relevanta innehållet
    if "Moment:" in summary:
        # Extrahera allt efter "Moment:"
        moment_text = summary.split("Moment:", 1)[1].strip()
        # Om det är ett "Laboration Klinisk hematologi:"-moment
        if moment_text.startswith("Laboration Klinisk hematologi:"):
            # Ta bort en eventuell avslutning " : Okänd"
            moment_text = re.sub(r'\s*:\s*Okänd$', '', moment_text)
            return moment_text.strip()
        else:
            # För andra moment: extrahera texten upp till första kolon
            moment_pattern = r'^([^:]+)'
            match = re.search(moment_pattern, moment_text)
            if match:
                return match.group(1).strip()
            else:
                return moment_text.strip()
    else:
        return summary.strip()

def should_keep_event(raw_summary: str) -> bool:
    """
    Returnerar True om eventet ska behållas:
      - Endast om sammanfattningen (ORIGINAL, orensad) innehåller något av nyckelorden:
        'Omtentamen', 'Salstentamen', 'Tentamen', 'muntlig tentamen', 'dugga'
      - Matchning sker case-insensitive.
    """
    if raw_summary is None:
        return False

    text = raw_summary.lower()
    return any(keyword in text for keyword in KEYWORDS)

def clean_calendar():
    """
    Hämtar ICS-kalendern, rensar varje VEVENT med den modifierade sammanfattningen
    och returnerar den nya kalendern som iCal-data.
    
    Filtrering av tentor görs på ORIGINALSUMMARY,
    medan vi visar den rensade summaryn i output.
    """
    response = requests.get(ICS_URL)
    response.raise_for_status()

    original_cal = Calendar.from_ical(response.text)
    
    clean_cal = Calendar()
    clean_cal.add('prodid', '-//Cleaned HKR Calendar//EN')
    clean_cal.add('version', '2.0')
    
    for component in original_cal.walk():
        if component.name == "VEVENT":
            raw_summary = component.get('summary')
            
            # Filtrera först på ORIGINALET (så vi inte tappar "Tentamen" som ligger utanför Moment:)
            if not should_keep_event(raw_summary):
                continue

            # Sedan rensar vi summaryn för att den ska se snygg ut
            cleaned_summary = clean_event_summary(raw_summary)

            clean_event = Event()
            clean_event.add('summary', cleaned_summary)
            clean_event.add('dtstart', component.get('dtstart'))
            clean_event.add('dtend', component.get('dtend'))
            clean_event.add('location', component.get('location', ''))
            clean_event.add('description', component.get('description', ''))
            
            clean_cal.add_component(clean_event)
    
    return clean_cal.to_ical()

if __name__ == "__main__":
    # För testning: skriv ut den rensade iCal-strängen
    cleaned_ical = clean_calendar()
    print(cleaned_ical.decode('utf-8'))
