# nook

A tiny metasearch page. It asks other search engines and shows one merged list. No index, no database, no logging.

## Run
```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python app.py
```
Open http://127.0.0.1:8080. Press `ctrl+k` for the jump box and see `/tools` for everything it can answer. Your browser can add it as a search engine (it offers `/opensearch.xml`).

## Home page
It is just the name and a search box. The pencil in the corner opens a small editor where you can switch on a greeting, today's date and a few bookmarks. All of that is saved only in your own browser (never sent to the server) and stays off until you turn it on.

## More results
"more" at the bottom of a results page asks for the next page. Only DuckDuckGo pages properly: Bing ignores paging for nook, so it gives page one only, and the image tab has no "more". Pages that repeat earlier results are filtered out. The line under the results says which engines answered and which didn't.

## Which engines, and why not others
Web results come from DuckDuckGo, Bing, Yahoo and Seznam, all on by default (Wikipedia too, once you set `contact` in `config.toml`, because its API insists on knowing who is asking). The small "engines" button on the home page and on web results lets each visitor switch engines off; it is remembered in a cookie in that browser, with no account or settings page. The `engines` list in `config.toml` decides which engines an instance offers at all. Seznam is a Czech engine with an index of its own, so Czech and Slovak (.cz, .sk) sites are left out of its results. Yahoo only answers HTTP/2 clients, so nook asks every engine over HTTP/2. Brave, Mojeek and Startpage turn nook away with captchas or proof-of-work challenges, and nook doesn't try to get around those. `!brave`, `!mojeek` and `!sp` open a search there in your own browser instead, where you can answer their checks yourself. Which engines answer can differ from one network to another, so run `python check_engines.py` to see what works for you.

## When an engine misbehaves
Engines get throttled now and then. nook retries a failed engine once straight away; an engine that fails twice in a row is left alone for a minute (longer if it keeps failing) so it isn't hammered; and if nobody answers at all, you see the last results for that search, marked as old. The line under the results says which engines answered. Requests carry the headers a real browser sends, which seems to make throttling rarer.
`per_site` in `config.toml` (default 2) keeps one site from filling a page. Run `python check_engines.py` any time to test every engine and news feed live: it tells you which ones fail, so you know whether a parser needs updating.

## Cards above the results
- **Definitions.** `define serendipity`, `serendipity meaning`, `what does serendipity mean`: a card with the pronunciation (and a button to hear it), numbered senses with examples, similar words and the word's origin. nook reads the American Heritage Dictionary and Cambridge Dictionary pages and Datamuse (similar words) itself, so your browser never visits them, and builds the card from whichever answer. The sound clip is passed through nook too.
- **Wikipedia, worked out for whatever you typed.** Nothing is hardcoded about any subject. A short query is tried as an article title first, so redirects work (`hotlink` leads to *Inline linking*), then as a Wikipedia search, and a search hit is only used when it really covers every word you typed (`python tutorial` gets no card; `mercury`, which means too many things, gets none either). The card shows a summary, the article's picture, a few more photographs, the flag of the country it is about, the place on a map, and the Simple English version of the same subject under "in simple words". The region you pick sets the language (a German region reads de.wikipedia.org). **Text only** (engines dropdown, "pictures") leaves out the photographs, flag and map. If Wikipedia has nothing fitting, DuckDuckGo's instant answer is the fallback (only while that engine is on).
- **Time anywhere.** `time in germany`, `tokyo time`, and conversions between two places: `ethiopia time to germany time`, `3pm in ethiopia to germany`, `10am est to cet`, `time difference between lagos and berlin`. Cities, countries and zone names (EST, CET, JST...) all work, and daylight saving is handled. A country with several zones uses its main one (USA is New York, Russia is Moscow), and the card names the city it used. The built-in tables know countries and a few hundred big cities; for any other place (Bonn, Hallstatt...) nook asks Open-Meteo's free place search once (the card says so), then remembers the answer. Only the name of the place is sent, only for time questions, and only when one side of the question is a place nook already knows.
- **Money, dice, timers.** `100 usd in eur` (European Central Bank rates), `roll d20`, `roll 2d6`, `flip a coin`, `random number between 1 and 100`, `timer 5 min` (counts down in the page and beeps).
- **Weather.** `weather in bonn`, `bonn weather`, `sunrise in oslo`: now, the next five days, sunrise and sunset, from Open-Meteo (free, no key). Only the place name is sent.
- **Dates and the moon.** `days until christmas`, `45 days from now`, `what day is 1 march 2027`, `how old is someone born 12 may 1990`, `days between 2026-01-01 and 2026-12-25`, `week number`, `moon phase`. Worked out here, no network.
- **Word tools.** `rhymes with orange`, `synonyms for happy`, `antonyms of hot`, `words that end in tion`, `words starting with pre`, `adjectives to describe rain` (from Datamuse). Each word links to its definition.
- **Developer tools.** `uuid`, `random password 24`, `sha256 of hello` (md5, sha1, sha512 too), `base64 encode hi`, `url encode a b`, `#ff8800` or `rgb(255,136,0)` (shows hex, rgb and hsl), `epoch 1700000000`, `lorem ipsum 3 paragraphs`. All worked out here, with a copy button.
- **Translate.** `hello in german`, `translate good night to japanese`, `how do you say thank you in spanish`, `translate hello from english to french` (MyMemory's free service, no key; only the phrase is sent).
- **Facts about places.** `capital of peru`, `germany population`, `currency of japan`, `what languages are spoken in switzerland`, `brazil facts` (Wikidata).
- **Prices.** `aapl stock`, `apple stock price`, `bitcoin price`: the price, the day's change and a three-month line (Yahoo Finance's public chart service; can be a little late, and it is information, not advice).
- **Percentages and number bases.** `15% of 80`, `20 is what percent of 50`, `increase 80 by 15%`, `20% off 80`, `change from 50 to 80`, `255 in binary`, `0xff to decimal`. Worked out here.
- **Graphs.** `plot sin(x)`, `graph x^2 - 3`, `y = 2x + 1`, `plot sin(x), cos(x) from -5 to 5`. nook has its own small expression parser (no eval, so nothing typed can run as code) and draws the curves as an SVG in its own colours.
- **Distance and routes.** `distance from bonn to berlin`, `how far is paris from london`, `walk from bonn to cologne`, `bike from ... to ...`: the distance, how long it takes, the straight-line distance, and the route drawn on a nook map. Places come from OpenStreetMap's place search, roads from OpenStreetMap's free routing service. Where no road joins two places (across an ocean) nook says so and draws a straight line instead.
- **History.** `old capital of germany`, `former currency of france`, `capitals of japan in history` (Wikidata statements that have ended, with their years), and `on this day`, `what happened on 20 july` (Wikipedia's "on this day").
- **People.** A person's Wikipedia card gets a small timeline: born, died, aged.
- **Earth and space.** `earthquakes today` (US Geological Survey, magnitude 4.5 and up, with a map), `where is the iss` (wheretheiss.at). Tides are left out: there is no free worldwide source.
- **Loans and the bill.** `loan 200000 at 4% for 30 years`, `monthly payment on 20000 at 5% for 5 years`, `split 84 between 3 with 15% tip`, `tip 15% on 48`.
- **Did you mean.** For a search with a typo (`pyhton programing`), Wikipedia's own spelling suggestion appears above the results, but only when the words as typed hardly exist anywhere, so a correct search never gets a wrong "correction".
Cards that need the outside world are remembered for an hour (prices for two minutes). Time, dice, timers, dates and developer tools are worked out fresh every time.

## Region, safe search, time, and your own site list
The "engines" dropdown has **region** (like DuckDuckGo's: a country and its language), **safe search** (moderate, strict, off), **time** (past day to year), and two boxes: sites to **hide** and sites to **show first**. A "hide site" button on every web result adds to the hide list. All of it is a cookie in your browser.
How the region works: DuckDuckGo takes a region code with every search (`kl`, like `de-de`) and weights its results towards that country; nook sends the same code. Yahoo has a site per country, so nook uses that one (Germany gets `de.search.yahoo.com`, and 13 countries work). Bing breaks when it is told a region, so it can't take part, and neither can Seznam. When a region, the time filter or strict safe search is on, only the engines that can do it are asked, and the page says which. Safe search is DuckDuckGo's `kp`, Bing's `adlt` and Yahoo's `vm`. Without a region chosen, each engine picks one from your connection.

## Maps
`/maps` (and the map inside a Wikipedia card, and "bigger map" under it) is a small map in nook's colours: the tiles are OpenStreetMap's, warmed up with a filter and a wash of the page colour, so the same map is cream in the day and brown at night. Drag to move, `+` `-` or double-click to zoom (the mouse wheel zooms once you have clicked the map, so the page still scrolls normally), arrow keys when it is focused. Search for a place by name (OpenStreetMap's Nominatim, at most one question a second as its rules ask) and click one in the list.
Tiles are fetched by nook and remembered for a week, so your browser never talks to the tile server, and no JavaScript library is loaded from anywhere. The OpenStreetMap credit (a link to openstreetmap.org/copyright) stays for five seconds, as OpenStreetMap's attribution guideline allows, or until you use the map; the small **i** in the corner brings it back, and it is also on the about page. OpenStreetMap's free tile server is meant for light use, so for a busy instance set `tile_url` (and `map_credit`) in `config.toml` to a tile server you are allowed to use.

## Search tools
- **Suggestions while you type.** A small list under the search box, from DuckDuckGo's suggestion service through nook (after a short pause, so not every keystroke). "suggestions" in the engines dropdown switches them off (a cookie).
- **ctrl+k.** One box to jump anywhere: a page, an example from the tools list, a `!bang`, something you saved or searched for, or search / images / videos / news / maps / code for what you typed.
- **Lenses.** Under the tabs: *narrow to discussions, code, academic*. A lens is only a list of sites added to your search as `site:` filters, so every engine understands it; change the lists or add your own under `[lenses]` in `config.toml`.
- **Dots.** A small dot before the engines under a result means more than one engine found it.
- **Peek.** "peek" under a result shows the opening of the page right there (through the reader, so the site never sees your browser).
- **Share.** "share" copies a link to the search with your region, engines, safe search and time filter in it, so the other person sees what you see. The settings travel in the link and are not saved in their browser.
- **Your own feeds.** On the news page, a **mine** wing: add the address of any RSS or Atom feed (a blog, a subreddit's `.rss`, a YouTube channel feed). Up to six, kept in a cookie; nook fetches them, and only public addresses are accepted.

## Quiet touches
- **It appears at once.** The search box and tabs are sent immediately and the results fill in when the engines answer (a small "asking the engines" line goes away by itself). A remembered search is one piece, as before. Under a result, the seconds the engines took are shown next to "answered by".
- **Quieter results.** Each result shows its address as a trail (`en.wikipedia.org › wiki › Bonn`), a small label when it is a pdf, a video or a forum, and a thumbnail for YouTube links. Under it only the engines and "read" show; **more** opens the rest: save, peek, hide site, **favour site** (show it first from now on), more from this site, an archived copy, copy link. `s` still saves the result you are on.
- **News and maps** are one click from any search (the tabs), and an empty search offers the same question to DuckDuckGo, Bing, Brave, Startpage and Mojeek. When two or more engines fail, a link goes to `/status`.
- **Engines dropdown:** "open results in a new tab". Click the empty search box and your recent searches appear (if you switched them on with the pencil).
- **Home page:** the pencil can switch on a **word of the day** under the box (from Wiktionary, through nook).
- **Cards:** `calendar`, `calendar march 2027`, `stopwatch`, `pomodoro`, `choose pizza, pasta or soup`, `word count ...`, `uppercase ...`, `reverse ...`, `slugify ...`, `roman numerals 2026`, `xiv in decimal`, `my ip`, `my user agent`. Answers have a small **copy**. `/surprise` takes you to a random Wikipedia subject. Search tricks (`"exact phrase"`, `site:`, `-word`, `filetype:`) are listed on `/tools`.
- **For everyone:** a skip link, clear keyboard focus, no animation if your system asks for none, a print style (just the words), and a thin progress line while you read an article.

## Watching a search, comparing engines, keeping an article
- **Watch.** "watch" under a search keeps an eye on it. `/watching` asks again and shows which results are new since you last looked ("mark as seen" resets it); `/today` shows a count. The list is only in your browser. Every search also has a **feed** link (`/search.rss?q=...`): put it in a feed reader and the reader does the watching, with nothing kept on the server. `/search.json?q=...` gives the same results as data.
- **Compare engines.** `/versus?q=...` (and a link under every web search) asks each engine on its own and lists their answers side by side, with a dot on pages more than one found.
- **Image filters.** The images tab has size, type (photo, clipart, drawing, animated) and colour, through Bing's own filters.
- **Keep a copy.** "keep a copy" in the reader saves the article's text in this browser, so you still have it if the page changes or goes behind a paywall. They are on the shelf. (It is kept for you, but opening it still needs nook running: this is not an offline app.)

## More pages
`/tools` lists everything nook can answer on its own with an example to click. `/shelf` is your saved items (searchable, with tags), recent searches, notes and bookmarks in one place, all in your browser. `/code` searches GitHub, npm, MDN, Stack Overflow and PyPI at once. `/today` is an opt-in glance page: weather and clocks for places you choose and the main headlines. `/maps` is above. They are all linked from the footer.
`/travel` is the way between two places on one page: distance, time, the route on the map, the time difference and the weather at both ends. `/world` is the earth right now: earthquakes and the space station on a map, and the moon. `/learn` is a word-lookup box (define, rhymes, synonyms, opposites...) with the word of the day (Wiktionary), today's featured article and "on this day". `/watching` is above. `/status` shows which engines and news feeds are working, when each last answered, and a button that runs the same live check as `check_engines.py` (once a minute at most).

## Reading, saving, shortcuts
- **Read it here.** Every web result has a "read" link that opens the page in nook's reader (clean text, with a button to the original). It works when the site lets nook fetch it.
- **Save and recent.** "save" on any result or news story keeps it in this browser; the home page lists what you saved. Recent searches are only remembered if you switch them on with the pencil. Both stay in your browser (never sent to the server) and "forget recent and saved" clears them.
- **Keyboard.** `/` search, `j` `k` move through results, `enter` open, `r` read it here, `s` save, `1` `2` `3` web, images, videos, `n` news, `?` for the list.
- **Related searches.** A few other searches under the results, from DuckDuckGo's suggestion service (only while that engine is on).
- **A better reader.** Reading time, text size, a wider layout, and a "listen" button that uses your browser's own voice (nothing is sent anywhere). Your choices are kept in your browser.
- **News, searchable.** The news page has a search box that looks through every story in the feeds, and stories that are new since you last looked get a small dot.
- **Notes and backup.** The pencil on the home page can show a small notes box (saved as you type). "Back up" downloads one small file with everything nook keeps for you in this browser (saved items, notes, bookmarks, settings, region, site lists); "restore" loads it back, on this browser or another.
- **Easier scanning.** Your search words are bold in snippets, leading dates are moved out of the way, and each result has its site's icon (fetched through nook).
- **Time filter.** The "engines" dropdown has a "time" choice (past day, week, month, year). Only DuckDuckGo and Yahoo can filter by time, so only they are asked while it is on, and the page says so.

## Quick answers and bangs
Type a sum (`12*7`, `(3+4)^2`) or a conversion (`5 km in miles`, `72 f to c`, `2 kg to lb`) and the answer appears above the results. Bangs jump straight to a site: `!w`, `!yt`, `!gh`, `!hn`, `!so`, `!r`, `!mdn`, `!pypi`, `!npm`, `!maps`, `!a`, `!imdb`, `!g`, `!ddg`, `!bing`, `!brave`, `!sp` (startpage), `!mojeek`, `!qwant`, `!yahoo`, as `!w sourdough` or `sourdough !w`. Add your own under `[bangs]` in `config.toml`.
Operators like `"exact phrase"`, `site:example.com`, `-word` and `filetype:pdf` work too, because nook passes your query to the engines untouched.

## Images and videos
Tabs under the search box. Images come from Bing and open in a small viewer (arrow keys, Esc). Videos come from DuckDuckGo and play on `/watch` in nook's own player. YouTube videos are streamed by YouTube's embed, with nook's controls drawn on top; direct `.mp4`/`.webm` links play natively. A video whose owner blocks embedding shows a link to the source instead.

## News
`/news` (linked under the logo on the home page) shows headlines from the outlets in `feeds.toml`, one wing at a time: far left, left, centre, right, far right, or all. You can read text only or with pictures; nook remembers your choice in a cookie.
Feeds are refreshed in the background every few minutes (`news_refresh_minutes`), so the page is instant. Headlines about the same story are grouped: under a story you'll see "also told by" with the other outlets and the wing each sits in. Under "all", the stories the most outlets covered come first.
"compare" next to "also told by" opens one page with the same story told by every outlet that ran it, grouped from the far left to the far right.
Clicking a story opens it in nook's reader: the whole article as plain text, with a "read at <outlet>" button at the top and bottom that takes you to the original. nook fetches the article page itself and extracts the text. If an outlet blocks that or is behind a paywall, you get the text from its feed if it carries any, otherwise the summary and a note.
Which wing an outlet sits in is my rough reading of public media-bias ratings, so it is an opinion. Move outlets, add feeds or remove them by editing `feeds.toml` and restarting.

## Privacy
- Pictures (thumbnails, full images, news photos, video posters) are fetched by nook and passed on, so your browser only ever talks to nook. Only addresses nook itself put on a page can be fetched (each is signed), private and local addresses are refused, and SVG is never passed on.
- Every page is sent with `Referrer-Policy: no-referrer` and a strict Content-Security-Policy, so a page cannot quietly load anything from another site.
- A video does not touch YouTube until you press play. After that YouTube sees your IP address, because the video comes from them. Nothing here can hide that, short of downloading the video through the server.
- Links you click (results, news stories, "source page") go straight to those sites, as any link would.
- Some cards and features ask a service for you, and only when your query calls for it: Wikipedia, Wikimedia Commons and Wikidata (summaries, pictures, flags, facts), OpenStreetMap (map tiles, place search), Open-Meteo (weather, and finding a place by name), Datamuse (rhymes, synonyms, similar words), the American Heritage and Cambridge dictionary pages (definitions), MyMemory (translations), Yahoo Finance (prices), DuckDuckGo (suggestions, related searches, site icons), GitHub, npm, MDN, Stack Overflow and PyPI (only on `/code`), OpenStreetMap's routing service (routes), the US Geological Survey and wheretheiss.at (`/world`, earth cards), Wikimedia's feeds (on this day, word of the day), and the European Central Bank's rates (money). Each sees only the word or place involved, from nook's server and not your browser. Wikimedia's servers insist on a descriptive User-Agent, so nook introduces itself to them as `nook/1.0` with your `contact` if you set one.
- The server still talks to the engines and feeds, so on a shared instance the server's operator sees searches. Nothing is stored or logged.
- If you run it for others, set `secret` in `config.toml` (any long random string) so picture links stay valid across restarts.

## Settings
Everything is in `config.toml`: which engines, timeout, port, cache time, rate limit.
To let others reach it, set `host = "0.0.0.0"` and put it behind a reverse proxy with HTTPS.
Wikipedia only works once `contact` is set (their API rules require it).

## Add an engine
Copy `engines/duckduckgo.py`: write `parse(text)` for the engine's results page, `search(client, query)` to fetch it, and add its name to `AVAILABLE` in `engines/__init__.py`. Save a sample page in `tests/fixtures/` and test the parser.

## Test
`.venv\Scripts\python -m pytest`
