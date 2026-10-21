"""Regions, the way DuckDuckGo offers them: a country and its language, like "de-de".

DuckDuckGo takes the code as it is (its `kl` setting). Yahoo has a site per country, so a
region means its address. Bing breaks when it is told a region, so it can't take part."""

REGIONS = [
    ("wt-wt", "all regions"), ("ar-es", "argentina"), ("au-en", "australia"), ("at-de", "austria"),
    ("be-fr", "belgium (french)"), ("be-nl", "belgium (dutch)"), ("br-pt", "brazil"), ("bg-bg", "bulgaria"),
    ("ca-en", "canada (english)"), ("ca-fr", "canada (french)"), ("cl-es", "chile"), ("cn-zh", "china"),
    ("co-es", "colombia"), ("hr-hr", "croatia"), ("cz-cs", "czech republic"), ("dk-da", "denmark"),
    ("ee-et", "estonia"), ("fi-fi", "finland"), ("fr-fr", "france"), ("de-de", "germany"),
    ("gr-el", "greece"), ("hk-tzh", "hong kong"), ("hu-hu", "hungary"), ("is-is", "iceland"),
    ("in-en", "india"), ("id-en", "indonesia"), ("ie-en", "ireland"), ("il-en", "israel"),
    ("it-it", "italy"), ("jp-jp", "japan"), ("kr-kr", "korea"), ("lv-lv", "latvia"),
    ("lt-lt", "lithuania"), ("my-en", "malaysia"), ("mx-es", "mexico"), ("nl-nl", "netherlands"),
    ("nz-en", "new zealand"), ("no-no", "norway"), ("pk-en", "pakistan"), ("pe-es", "peru"),
    ("ph-en", "philippines"), ("pl-pl", "poland"), ("pt-pt", "portugal"), ("ro-ro", "romania"),
    ("ru-ru", "russia"), ("xa-ar", "saudi arabia"), ("sg-en", "singapore"), ("sk-sk", "slovakia"),
    ("sl-sl", "slovenia"), ("za-en", "south africa"), ("es-es", "spain"), ("se-sv", "sweden"),
    ("ch-de", "switzerland (german)"), ("ch-fr", "switzerland (french)"), ("tw-tzh", "taiwan"),
    ("th-en", "thailand"), ("tr-tr", "turkey"), ("ua-uk", "ukraine"), ("uk-en", "united kingdom"),
    ("us-en", "united states"),
]
VALID = {code for code, _ in REGIONS}
LABELS = dict(REGIONS)

# The country sites Yahoo answered when tried (a region is its country part, "de" in "de-de").
YAHOO_SITES = {"de": "de", "at": "de", "ch": "de", "uk": "uk", "ie": "uk", "fr": "fr", "es": "es", "it": "it",
               "ca": "ca", "au": "au", "in": "in", "br": "br", "mx": "mx", "sg": "sg", "nz": "nz", "nl": "nl"}


def yahoo_site(region):
    """The Yahoo country site for a region, or None when Yahoo has none that works."""
    return YAHOO_SITES.get((region or "")[:2]) if region != "wt-wt" else None
