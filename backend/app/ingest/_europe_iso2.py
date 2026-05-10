"""European country names -> ISO 3166-1 alpha-2.

Used by:

- the SPARQL path in :mod:`app.ingest.wikidata` to validate country shape
  (every WDQS row already carries an ISO2, so this is mostly defensive);
- the Wikipedia fallback in :mod:`app.ingest.wikipedia_calendar` to map
  link/anchor text to ISO2 (Wikipedia HTML does not expose ISO codes).

Coverage matches Wikidata items with ``P30 = Q46`` (continent: Europe) that
hold ISO2 codes. We intentionally include the few transcontinental states
that are in scope for the European elections dashboard (RU, TR, AZ, GE, KZ,
AM, CY).

Aliases (``UK``, ``Britain``, ``Czechia``, ``Türkiye``, ``Holy See`` ...) are
the link-anchor variants we've seen on Wikipedia "Elections in YYYY" pages.
"""

from __future__ import annotations

COUNTRY_NAME_TO_ISO2: dict[str, str] = {
    "Albania": "AL",
    "Andorra": "AD",
    "Armenia": "AM",
    "Austria": "AT",
    "Azerbaijan": "AZ",
    "Belarus": "BY",
    "Belgium": "BE",
    "Bosnia and Herzegovina": "BA",
    "Bulgaria": "BG",
    "Croatia": "HR",
    "Cyprus": "CY",
    "Czech Republic": "CZ",
    "Czechia": "CZ",
    "Denmark": "DK",
    "Estonia": "EE",
    "Finland": "FI",
    "France": "FR",
    "Georgia": "GE",
    "Germany": "DE",
    "Greece": "GR",
    "Hungary": "HU",
    "Iceland": "IS",
    "Ireland": "IE",
    "Italy": "IT",
    "Kazakhstan": "KZ",
    "Kosovo": "XK",
    "Latvia": "LV",
    "Liechtenstein": "LI",
    "Lithuania": "LT",
    "Luxembourg": "LU",
    "Malta": "MT",
    "Moldova": "MD",
    "Monaco": "MC",
    "Montenegro": "ME",
    "Netherlands": "NL",
    "North Macedonia": "MK",
    "Norway": "NO",
    "Poland": "PL",
    "Portugal": "PT",
    "Republic of Ireland": "IE",
    "Romania": "RO",
    "Russia": "RU",
    "San Marino": "SM",
    "Serbia": "RS",
    "Slovakia": "SK",
    "Slovenia": "SI",
    "Spain": "ES",
    "Sweden": "SE",
    "Switzerland": "CH",
    "Turkey": "TR",
    "Türkiye": "TR",
    "Ukraine": "UA",
    "United Kingdom": "GB",
    "Vatican City": "VA",
    # Common Wikipedia link-anchor aliases.
    "UK": "GB",
    "Britain": "GB",
    "Great Britain": "GB",
    "Holy See": "VA",
    "Vatican": "VA",
    "Republic of North Macedonia": "MK",
    "The Netherlands": "NL",
}

EUROPE_ISO2: frozenset[str] = frozenset(COUNTRY_NAME_TO_ISO2.values())


# Adjective ("demonym") -> ISO2.
#
# The Wikipedia "Elections in YYYY" page expresses each election as a bullet
# whose title is "<year> <Demonym> <type> election" (e.g. "2026 Cypriot
# legislative election"). The country is *not* a separate cell, so we infer
# ISO2 from the demonym embedded in the title.
DEMONYM_TO_ISO2: dict[str, str] = {
    "Albanian": "AL",
    "Andorran": "AD",
    "Armenian": "AM",
    "Austrian": "AT",
    "Azerbaijani": "AZ",
    "Belarusian": "BY",
    "Belgian": "BE",
    "Bosnian": "BA",
    "Bulgarian": "BG",
    "Croatian": "HR",
    "Cypriot": "CY",
    "Czech": "CZ",
    "Danish": "DK",
    "Estonian": "EE",
    "Finnish": "FI",
    "French": "FR",
    "Georgian": "GE",
    "German": "DE",
    "Greek": "GR",
    "Hungarian": "HU",
    "Icelandic": "IS",
    "Irish": "IE",
    "Italian": "IT",
    "Kazakh": "KZ",
    "Kazakhstani": "KZ",
    "Kosovan": "XK",
    "Kosovar": "XK",
    "Latvian": "LV",
    "Liechtensteiner": "LI",
    "Lithuanian": "LT",
    "Luxembourgish": "LU",
    "Macedonian": "MK",
    "North Macedonian": "MK",
    "Maltese": "MT",
    "Moldovan": "MD",
    "Monégasque": "MC",
    "Monegasque": "MC",
    "Montenegrin": "ME",
    "Dutch": "NL",
    "Norwegian": "NO",
    "Polish": "PL",
    "Portuguese": "PT",
    "Romanian": "RO",
    "Russian": "RU",
    "Sammarinese": "SM",
    "Serbian": "RS",
    "Slovak": "SK",
    "Slovakian": "SK",
    "Slovene": "SI",
    "Slovenian": "SI",
    "Spanish": "ES",
    "Swedish": "SE",
    "Swiss": "CH",
    "Turkish": "TR",
    "Ukrainian": "UA",
    "British": "GB",
    "Scottish": "GB",
    "Welsh": "GB",
    "Northern Irish": "GB",
    "English": "GB",
    # Demonyms tied to overseas territories of European states.
    "Faroese": "DK",
    "Manx": "GB",
}

