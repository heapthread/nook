"""Everything nook can answer on its own, as a list: for the /tools page and the ctrl+k palette."""

CATALOG = [
    ("words", [
        ("definitions", ["define serendipity", "what does ephemeral mean"]),
        ("rhymes and synonyms", ["rhymes with orange", "synonyms for happy", "antonyms of hot", "words that end in tion"]),
        ("translate", ["hello in german", "translate good night to japanese", "how do you say thank you in spanish"]),
    ]),
    ("places and time", [
        ("time anywhere", ["time in tokyo", "ethiopia time to germany time", "10am est to cet"]),
        ("weather", ["weather in bonn", "sunrise in oslo"]),
        ("distance and routes", ["distance from bonn to berlin", "how far is paris from london", "walk from bonn to cologne", "bike from bonn to cologne"]),
        ("the earth right now", ["earthquakes today", "where is the iss", "moon phase"]),
        ("facts", ["capital of peru", "germany population", "switzerland facts"]),
        ("history", ["old capital of germany", "former currency of france", "on this day", "what happened on 20 july"]),
        ("anything on wikipedia", ["hotlink", "alan turing", "mount fuji"]),
    ]),
    ("numbers", [
        ("sums and units", ["12*7", "(3+4)^2", "5 km in miles", "72 f to c"]),
        ("percentages", ["15% of 80", "20% off 80", "change from 50 to 80", "20 is what percent of 50"]),
        ("number bases", ["255 in binary", "0xff to decimal", "255 in hex"]),
        ("graphs", ["plot sin(x)", "graph x^2 - 3", "plot sin(x), cos(x) from -5 to 5"]),
        ("money", ["100 usd in eur", "loan 200000 at 4% for 30 years", "split 84 between 3 with 15% tip", "tip 15% on 48"]),
        ("prices", ["aapl stock", "bitcoin price"]),
    ]),
    ("dates", [
        ("days and weeks", ["days until christmas", "45 days from now", "what day is 1 march 2027", "week number"]),
        ("ages and gaps", ["how old is someone born 12 may 1990", "days between 2026-01-01 and 2026-12-25", "moon phase"]),
    ]),
    ("search tricks", [
        ("by date", ["python release notes after:2023", "olympics before:2000", "election during:2020", "climate report after:2024-01 before:2024-06"]),
        ("narrow it down", ['"sourdough starter"', "tide site:wikipedia.org", "python -snake", "annual report filetype:pdf", "intitle:recipe sourdough"]),
    ]),
    ("small things", [
        ("calendar and clocks", ["calendar", "calendar march 2027", "stopwatch", "pomodoro"]),
        ("decide and count", ["choose pizza, pasta or soup", "word count the quick brown fox", "uppercase hello", "slugify Hello World", "roman numerals 2026", "xiv in decimal"]),
        ("about you", ["my ip", "my user agent"]),
        ("dice and coins", ["roll d20", "roll 2d6", "flip a coin", "random number between 1 and 100"]),
        ("a timer", ["timer 5 min", "timer 90 seconds"]),
    ]),
    ("for developers", [
        ("packages", ["npm react", "pip install httpx", "cargo add tokio"]),
        ("networks", ["dns example.com", "dig github.com mx", "whois github.com", "192.168.1.0/24 range"]),
        ("make something", ["uuid", "random password 24", "lorem ipsum 3 paragraphs"]),
        ("encode and hash", ["sha256 of hello", "base64 encode hi", "url encode a b"]),
        ("colours and time", ["#ff8800", "rgb(255,136,0)", "epoch 1700000000"]),
    ]),
]

PAGES = [("news", "/news"), ("maps", "/maps"), ("tools", "/tools"), ("shelf", "/shelf"), ("code", "/code"),
         ("today", "/today"), ("travel", "/travel"), ("world", "/world"), ("learn", "/learn"),
         ("watching", "/watching"), ("surprise me", "/surprise"),
         ("weather", "/weather"), ("convert", "/convert"), ("books", "/books"), ("status", "/status"), ("compare engines", "/versus"), ("about", "/about"), ("home", "/")]


def flat():
    """[(label, example)] for every example."""
    return [(title, ex) for _, items in CATALOG for title, examples in items for ex in examples]
