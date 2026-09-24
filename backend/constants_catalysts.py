"""Catalyst classifier tunables (ADR 024) -- one set of rules for the history and the live desk.

Every pattern is matched case-insensitively against a headline (EDGAR: headline plus the opening
of the press release). Order matters and lives in ``catalysts/classify.py``: noise first, then
routine announcements, then dilution, then the positive classes strongest first.
"""
from __future__ import annotations

CATALYST_RULES_VERSION = "catalyst-rules-v6-2026-09-23"

# Verdicts for one symbol-day.
CATALYST_VERDICT_CATALYST = "catalyst"      # a real, company-specific positive catalyst
CATALYST_VERDICT_NEGATIVE = "negative"      # only dilution / delisting news
CATALYST_VERDICT_ROUTINE = "routine_only"   # only routine company items (officer change, earnings date)
CATALYST_VERDICT_NOISE = "noise_only"       # only movers lists, law firms, opinion, roundups
CATALYST_VERDICT_NONE = "none_found"        # every source answered and none named the ticker
CATALYST_VERDICT_NOT_CHECKED = "not_checked"  # no source answered for this day

CATALYST_KIND_CATALYST = "catalyst"
CATALYST_KIND_NEGATIVE = "negative"
CATALYST_KIND_ROUTINE = "routine"
CATALYST_KIND_NOISE = "noise"

CATALYST_STRONG = "strong"
# A single-company headline no rule placed. Kept as a weak catalyst in the verdict (one classifier for the
# history), but the live News pillar treats it as unknown: right about half the time on the labelled samples.
CATALYST_UNCLASSIFIED = "company_news"
CATALYST_WEAK = "weak"

# A news item naming more than this many tickers is a roundup (EDGAR filings are exempt: one filer).
CATALYST_MAX_TICKERS = 3
# Opinion mills: their headlines are never a company's own catalyst.
CATALYST_OPINION_PUBLISHERS = ("the motley fool", "zacks investment research", "zacks", "investorplace", "seeking alpha",
                               "seekingalpha")
# v6: stock screens ("Unusual volume stocks in Wednesday's session", "Let's take a look at the stocks that
# are in motion"): Finnhub files them under every ticker the screen lists. A screen publisher's headline that
# tags no ticker is a screen; one that does ("Pagaya Technologies (NASDAQ:PGY) Soars After Q1 Earnings Beat")
# is judged like any rewrite.
CATALYST_SCREEN_PUBLISHERS = ("chartmill",)
# Sources ranked for the representative item of a verdict (a filing beats a rewrite of it).
CATALYST_SOURCE_RANK = ("edgar", "globenewswire", "prnewswire", "newsfile", "fda", "alpaca", "finnhub", "massive")
# How much of a press release's opening the classifier reads besides its headline.
CATALYST_SUMMARY_CHARS = 600
# Live desk: symbols per Alpaca request and how often a roster's catalysts are re-read.
CATALYST_LIVE_BATCH = 50
CATALYST_LIVE_TTL_SEC = 120.0
# Live desk, Finnhub company news (catalysts/live_finnhub.py). The free tier's 60 calls / min is shared with the
# earnings calendar and the logos, so the reads take half; a read counts as having looked for its TTL and is
# renewed at half of it (a board of ~140 symbols is ~19 calls / min).
CATALYST_FINNHUB_URL = "https://finnhub.io/api/v1/company-news"
CATALYST_FINNHUB_KEY_ENV = "FINNHUB_API_KEY"
CATALYST_FINNHUB_CALLS_PER_MIN = 30.0
CATALYST_FINNHUB_TTL_SEC = 900.0
CATALYST_FINNHUB_HTTP_TIMEOUT_SEC = 10.0
# Publishers whose Finnhub copies are dropped: Alpaca carries Benzinga's articles, and Finnhub stamps them with
# Eastern wall-clock time read as UTC -- four hours early (#516; 4,072 of 5,568 title matches on the research store).
CATALYST_FINNHUB_SKIP_PUBLISHERS = ("benzinga",)
# Scanner rows: how often the board's verdicts are recomputed from what the live reads hold (in memory).
CATALYST_BOARD_INTERVAL_SEC = 15.0
# Labels kept per process (``classify_item`` is pure): every board pass re-reads the same items, and
# classifying them again took ~0.6 ms each -- about a second of the GIL per pass (2026-09-23).
CATALYST_CLASSIFY_CACHE_MAX = 16384
# The Trader's News panel (GET /api/catalysts/{symbol}): items listed, newest first; the payload's version.
CATALYST_PANEL_MAX_ITEMS = 40
CATALYST_PANEL_SCHEMA_VERSION = 1

# -- noise ---------------------------------------------------------------------------------------
CATALYST_LAW_FIRM_RE = (
    r"\b(announces|launches|opens|continues|commences)\b.{0,40}\binvestigation\b(?!.{0,30}(concluded|completed|closed))|"
    r"investigation on behalf|"
    r"investigation of (possible|potential)|investigating (whether|claims|potential|possible)|class action|securities fraud|"
    r"lead plaintiff|shareholder(s)? (alert|rights|reminder)|investor(s)? (alert|who (have )?lost|reminder)|"
    r"reminds? (investors|shareholders)|(lead plaintiff|filing|class action) deadline|deadline to (file|join|contact)|"
    r"rosen law|pomerantz|levi & korsinsky|bragar|hagens berman|faruqi|kessler topaz|glancy|bronstein|"
    r"schall law|gross law|kirby mcinerney|robbins llp|halper sadeh|block & leviton|johnson fistel|"
    r"encouraged to contact|secure counsel|losses? in (excess|of)|investor scrutiny|\bhbss\b"
)
CATALYST_MOVERS_RE = (
    # v6: "Why Did SOC, HTZ, COSM Stocks Tumble", "These stocks are moving in today's after hours session".
    r"\bwhy\b.{0,80}\b(shares?|stocks?)\b|stocks? (that )?(are )?(moving|showing activity|in motion|on the move)\b|"
    r"unusual (volume|options activity)|most active (stocks|names)|"
    r"\bwhy\b.{0,80}\b(is|are) (surging|soaring|jumping|falling|plunging|sinking|"
    r"rising|rallying|tanking|trading)|what'?s going on|here'?s why|here'?s what('?s| is) (going on|happening)|"
    r"what you should know|week ahead|"
    r"\b(shares?|stock)\s+(is\s+)?(jumps?|soars?|surges?|spikes?|rall(y|ies)|plunges?|tumbles?|skyrockets?|"
    r"trending|trading (higher|lower)|higher|lower|rockets?|climbs?|sinks?)\b.{0,60}\b(after hours|premarket|"
    r"pre-market|what|why|here|details|today)|stocks? (moving|to watch|making (big )?moves|on the move|in motion)|"
    r"top (gainers|losers|movers)|(premarket|pre-market|mid-?day|after-?hours) (gainers|movers|session)|"
    r"gapping|notable movement|which stocks|stock market today|market (wrap|update|recap)|"
    r"(gainers|losers) (and|&) (losers|gainers)|movers|penny stocks|what sparked|stock surge|"
    r"\b(shares?|stock) (is )?(soars?|jumps?|surges?|spikes?|plunges?|rockets?|skyrockets?|rall(y|ies)|tumbles?|"
    r"sinks?|climbs?|doubles?|triples?) (over |nearly |about |more than |almost )?\d+%|"
    r"(?<!revenue )(?<!sales )(?<!earnings )(?<!income )(?<!backlog )(?<!profit )"
    r"\b(soars?|jumps?|surges?|spikes?|rockets?|skyrockets?|plunges?|tumbles?) (over |nearly |about |more than |almost )?\d+%|"
    r"\b(shares?|stock) (are|is) (trading|moving) (higher|lower)|\bshares? (up|down) \d+%|"
    r"\b(shares?|stock) (spikes?|jumps?|soars?|surges?|rises?|falls?|slides?|drops?|sinks?|plunges?|tumbles?|"
    r"rockets?) (higher|lower|after|on|as|following)|market-moving news|^(crude|oil|gold|nasdaq futures|"
    r"dow futures|s&p 500 futures|stock futures|us stocks)\b|futures (indicate|point|signal)|pending home sales|"
    r"jobless claims|drawing investor attention|\b(etf|etn)\b|\b\dx (long|short)\b|"
    r"\b(stock|shares?)\b.{0,15}\b(gains?|pops?|rall(y|ies)|crash(es)?|jumps?|surges?|soars?|sinks?|slumps?|dips?|"
    r"climbs?|rises?|falls?|drops?|plunges?|tumbles?|spikes?|slides?|rebounds?|moves? (higher|lower))\b.{0,12}\b(on|after|as|amid|"
    r"following)\b|\b(jumps|soars|surges|slumps|pops|rallies|crashes|tumbles|plunges) on\b|"
    r"\b(drops|rises|rebounds|gains|falls) \d+(\.\d+)?%|^(dow|s&p 500|nasdaq|stocks)\b.{0,20}\b(jumps|falls|rises|"
    # v6: "Nasdaq Surges 200 Points; Nvidia Posts Upbeat Q2 Results" is a market wrap, not PPCB's earnings.
    r"slides|gains|drops|rall(y|ies)|surges|soars|tumbles|sinks|climbs|slumps|plunges|dips|edges)|deal dispatch|"
    r"biotech pulse|^watching\b"
)
# Exchange halt notices: the halt is not the news (the news, if any, follows as its own item).
CATALYST_HALT_RE = (
    r"^trading halt|halt news pending|halted at \d|quotation resumption|luld pause|halted,? (pending|news)|news pending|"
    # v5: Benzinga's circuit-breaker notices ("Digital World Acquisition Shares Halted On Circuit Breaker").
    r"\bshares? (are )?halted\b|halted on circuit breaker|\bshares? (to )?resumes? trad(e|ing)\b"
)
# v6: a one-ticker "why is it moving" piece names its cause in the summary ("... are surging Wednesday after the
# company announced the filing of a new provisional patent application"). The clause after the first of these
# markers is judged like a headline; the piece keeps its movers-list label unless that clause is placed.
CATALYST_CAUSE_RE = (
    # "just days after the company announced a buyback" dates something else; it is not the cause.
    # (\b: "Wednesday after the company announced" is a cause).
    r"(?<!\bdays )(?<!\bday )(?<!\bweeks )(?<!\bweek )(?<!\bmonths )(?<!\bmonth )"
    r"\b(after|following|on the heels of|in response to|on news (that|of)|as investors (react|respond) to)\b"
)
# ... and only for a one-ticker piece: a headline naming several stocks ("Here Are 20 Stocks Moving Premarket")
# gives the first one's cause, which Finnhub (no ticker count) would pin on every name in the list.
CATALYST_MULTI_STOCK_RE = (
    r"\bstocks\b|\bmovers\b|\bgainers\b|\blosers\b|\bround-?up\b|stock market|market-moving|futures|"
    r"^(dow|s&p|nasdaq)\b"
)
# ... unless the summary says there is no news, or that the move is someone else's news.
CATALYST_NO_CAUSE_RE = (
    r"\bno (company[- ]specific |apparent |obvious |clear |fresh |new |specific )?(news|catalyst|announcement)s?\b|"
    r"\bwithout (any )?(company[- ]specific |fresh |new )?news\b|absence of (any )?news|sympathy|"
    r"\b(rival|peer|competitor)s?\b|"
    # "... after the company pushed back against a report claiming it was considering going private" (Lucid).
    r"\b(den(y|ies|ied)|refut\w+|pushed back against|dismiss(es|ed) (a |the )?reports?)\b"
)
# Analyst notes: not the company's own news.
CATALYST_ANALYST_RE = (
    r"price target|initiates? coverage|(upgrades?|downgrades?)\b.{0,60}\b(to|from)\b|maintains (buy|hold|sell|"
    r"outperform|overweight|neutral|underweight)|reiterates? (buy|outperform|overweight)|analyst"
)
CATALYST_OPINION_RE = (
    r"\bshould you\b|\bis .{0,50} a (good )?buy\b|better buy|(\d+|top|best) .{0,40}stocks? to (buy|own|watch|hold)|"
    r"stock forecast|price prediction|zacks rank|(bull|bear) case|dividend stocks|"
    r"\bvs\.? .{0,40}(stock|buy)|could (soar|double|triple)|millionaire"
)
# -- routine (company news that is not a catalyst) ----------------------------------------------
CATALYST_ROUTINE_RE = (
    r"(to|will) (report|announce|host|release|present|participate|hold)\b.{0,80}(results|call|webcast|"
    r"conference|meeting|summit)|conference call|to present at|to participate in|fireside chat|"
    r"investor (conference|day)|annual (general )?meeting of (share|stock)holders|\bagm\b|results of (the )?annual|"
    r"earnings release date|"
    r"(appoints|names|welcomes|announces (the )?appointment of) .{0,60}(director|officer|board|ceo|cfo|president)|"
    r"(resign|retire)(s|ment)|annual report|notification of|form 20-f filing|earnings call (presentation|transcript)|"
    r"call transcript|(files?|filed|submits?|submitted) .{0,40}patent application|provisional patent|\bcro agreement|"
    r"planned .{0,30}(submission|filing)|plans to (submit|file)|quarterly (cash )?dividend|regular (quarterly )?dividend|"
    r"report of independent registered|disclaimer|investor presentation|corporate presentation|"
    r"\b(affirms|reaffirms|reiterates|maintains) .{0,30}guidance|extends? .{0,40}(expiration|term|maturity)|"
    r"\bclarif(ies|ication)\b|responds to (market|unusual)|labor (contract|agreement)|collective bargaining|"
    r"(letter|update) to (stock|share)holders|(stock|share)holder letter|\bceo letter|^exclusive: .{0,80}\b(says|tells)\b|"
    r"pre-(ind|investigational)|anticipated .{0,40}(submission|filing)|outlines? .{0,40}(submission|plans?)|"
    r"(brand|proprietary) name|(reaches|completes|achieves) .{0,20}enrollment|enrollment target|"
    r"(operational|production) update|operational changes|restructuring plan|workforce|lay ?offs?|"
    r"debt financing|credit (facility|agreement)|loan (agreement|facility)|line of credit|term loan|"
    r"filing of (a |its )?patent|strategically focused pipeline|pipeline (prioriti|reprioriti)"
)
# Fluff: a release that announces motion, not an event ("reports progress", "continued advancement").
# Judged after strong catalysts and before weak ones; a results release is never fluff.
CATALYST_FLUFF_RE = (
    r"(reports|provides|announces|shares) (continued |further |recent )?(progress|advancement|momentum)|"
    r"continued advancement|continues? to (strengthen|advance|expand|build)|\badvances\b|\bdrive\b.{0,40}target|"
    r"revamped website|unveils? .{0,20}approach|new dawn|compliance-driven|strategic vision|sets a new standard|"
    r"empowering the future|innovative (marketing )?approach"
)
# EDGAR cover-page lines a headline extractor can mistake for a release title.
CATALYST_SEC_COVER_RE = (
    r"name of registrant|translation of registrant|exact name|specified in its charter|^n/?a$|"
    r"^\(?address|principal executive offices|\d+(st|nd|rd|th) floor|office park|take no responsibility|"
    r"exchanges and clearing|"
    # v6: a street address ("Room 1207-08, No. 2488 Huandao East Road Huli District, Xiamen City" -- CPOP's 6-K).
    r"^(room|suite|unit|flat|floor|no\.)\s*[\d-]+|\b(road|street|avenue|boulevard)\b.{0,60}\b(district|city|province)\b"
)
# A rebrand or ticker change is routine unless it names a theme pivot (AI, crypto ...).
CATALYST_REBRAND_RE = r"rebrand\w*|name change|chang\w+ (its )?(trading )?symbol|ticker change"
# -- negative -----------------------------------------------------------------------------------
CATALYST_OFFERING_RE = (
    r"(public|registered direct|underwritten|best[- ]efforts|follow-on|secondary)\s+offering|"
    r"private placement|pricing of|prices? .{0,60}offering|proposed offering|warrant (inducement|exercise)|"
    r"\bat[- ]the[- ]market|\batm\b (program|offering|facility|agreement)|equity line|"  # v5: not "wh-at the market"
    r"securities purchase agreement|shelf registration|convertible (notes?|preferred|debentures?)|"
    r"placement agent|underwriting agreement|announces? (an? |its )?offering|offering of [\d.,]+ ?(m|k|million)?\b|"
    r"shares and warrants|\bwarrants? to purchase"
)
CATALYST_OFFERING_ENDED_RE = r"terminat\w*.{0,40}(\bat[- ]the[- ]market|\batm\b|equity line|offering)"
CATALYST_DELISTING_RE = (
    r"delist|(nasdaq|nyse|listing|bid price|equity).{0,40}deficiency|deficiency (letter|notice)|"
    r"notice of non-?compliance|minimum bid price (notice|deficiency)|"
    r"reverse (stock |share )?split|going concern|bankruptcy|chapter 11|"
    # v5: a share consolidation is a reverse split by another name ("1-for-6 Share Consolidation"); 1-for-1 is not.
    r"share consolidation|consolidation of (the company'?s |its )?(issued |outstanding )?(ordinary |common )?shares|"
    r"\b1[- ]for[- ]([2-9]|\d{2,4})\b"
)
# -- positive, strongest first ------------------------------------------------------------------
CATALYST_FDA_STRONG_RE = (
    r"(fda|ema|european commission|health canada|nmpa|pmda|mhra)\b.{0,60}(approv|clear(s|ed|ance)|authori[sz])|"
    r"(approv\w*|clear(s|ed|ance)|authori[sz]\w*)\b.{0,40}\b(fda|ema|health canada|nmpa|pmda|mhra)\b|"
    r"510\(k\) clearance|marketing authori[sz]ation|\bce mark\b|emergency use authori[sz]ation|"
    # v6: "Utebzi (tebipenem pivoxil) approved in the US for adults with ..." names no agency.
    r"\bapproved (in|for use in) the (u\.?s\.?|united states|european union|eu)\b"
)
CATALYST_FDA_WEAK_RE = (
    r"\bfda\b|breakthrough (therapy|device) designation|fast track|orphan drug|rare pediatric|pdufa|"
    r"\b(bla|nda|ind)\b (submission|acceptance|filing|clearance)|regulatory (submission|filing)"
)
CATALYST_CLINICAL_STRONG_RE = (
    r"(positive|statistically significant|met (its|the) primary|achiev\w+ (its |the )?primary|"
    r"successful) .{0,60}(results|data|endpoint|trial|study)|topline|top-line|primary endpoints? (were |was )?met|"
    r"met .{0,30}primary endpoint"
)
CATALYST_CLINICAL_WEAK_RE = (
    r"phase\s?(1|2|3|i{1,3}|1/2|2/3)\b|clinical (trial|study|data)|trial (results|data)|preclinical|"
    r"results from .{0,60}(trial|study)"
)
CATALYST_MERGER_STRONG_RE = (
    r"to be acquired|take[- ]private|go(ing)?[- ]private|tender offer|per share in cash|all-cash (deal|transaction|offer)|"
    r"definitive (merger )?agreement|merger agreement|agree[sd]? to merge|business combination|"
    r"acquisition (proposal|offer)|unsolicited (offer|proposal)|strategic alternatives|offer for .{0,40}shares|"
    r"takeover (offer|bid)|\bproposal\b.{0,60}(per share|/share)|(per share|/share) proposal|"
    r"to acquire .{0,60}(\$[\d.]+|per share|/share)|/share in cash|agreed to be acquired"
)
CATALYST_MERGER_WEAK_RE = r"\bacquir(e|es|ed|ing)\b|acquisition|\bmerger\b|\bmerge\b|\d+(\.\d+)?% stake|activist"
CATALYST_REGAINED_RE = r"regains?.{0,40}complian|regained .{0,40}complian"
CATALYST_CONTRACT_STRONG_RE = (
    r"(?<!labor )(?<!employment )\bcontract\b|\baward(ed|s)?\b|purchase order|\binks?\b.{0,40}\b(deal|agreement|pact)\b|"
    r"multi-?billion|\border(s)? (from|for|worth|valued)|supply agreement|"
    r"licens(e|ing) agreement|distribution agreement|selected by|department of (defense|energy|war)|\bdod\b|"
    r"u\.s\. (army|navy|air force|government)|\bnasa\b|\bdarpa\b|power purchase agreement|\bppa\b|"
    r"\bwins?\b.{0,40}\b(deal|contract|order|award|tender)|\bdeal\b.{0,30}(worth|valued)"
)
CATALYST_CONTRACT_WEAK_RE = (
    r"partner(s|ship)?\b|collaborat|memorandum of understanding|\bmou\b|letter of intent|\bloi\b|"
    r"strategic alliance|joint venture|integrat(es|ion) with|\bintegration\b|agreement with|pilot (program|deployment)|"
    r"\bgrant\b|funding (from|to|award)|selected (for|to)|accepted into|"
    # v5: a named customer win ("Adds Second OperatorOS Customer"), not "Won't Win This Important Customer".
    r"\b(adds?|signs?|wins?|lands?|secures?|onboards?)\s+(its\s+)?(first|second|third|another|new|major|large|key|"
    r"enterprise|largest|\d[\d,]*)\b.{0,40}\bcustomers?\b|\bcustomer wins?\b"
)
CATALYST_PRODUCT_RE = r"launch(es|ed)?\b|unveil|introduc(es|ed)|patent|commercial(ly)? (launch|availability)|expands? .{0,30}(into|to)"
CATALYST_EARNINGS_STRONG_RE = (
    r"record (revenue|quarter|results|sales|year)|raises (full[- ]year )?(guidance|outlook)|"
    r"(revenue|sales) (up|increase[sd]?|grew|growth of) \d{2,}|\d{2,}(\.\d)?% (yoy |year-over-year )?"
    r"(revenue|sales) (growth|increase)|beats? (estimates|expectations)|turns? profitable|first profitable"
)
CATALYST_EARNINGS_WEAK_RE = (
    r"\beps\b|\bsees (q[1-4]|fy|full[- ]year)|(reports?|announces?|releases?)\b.{0,80}\b(results|revenue|earnings)|"
    r"earnings (estimates|beat|miss)|\bq[1-4]\b.{0,30}\bearnings|(comp|same-store) sales|"
    r"\bposts\b.{0,40}\b(results|earnings|revenue|sales)|(mixed|strong|weak|record|upbeat) (results|quarter)|"
    r"\b(sales|revenue) (drop|rise|fall|gain|jump|grow)s?\b|"
    r"\b(q[1-4]|first|second|third|fourth)"
    r"\b.{0,30}\b(quarter|results)|fiscal (year )?(20\d\d )?results|preliminary (revenue|results)|guidance"
)
CATALYST_FINANCE_POSITIVE_RE = (
    r"buyback|(share|stock) repurchase|special (cash )?dividend|strategic investment|investment (from|by)|"
    r"non-dilutive|debt (free|elimination|extinguish)|eliminat\w*.{0,40}\bdebt\b|"
    r"(pays? (off|down)|retir(es|ed|ing)|extinguish\w*).{0,40}\bdebt\b|(ceo|director|insider|chairman).{0,40}(buys|purchase|"
    r"acquires|accumulates)|regains?.{0,40}complian|uplist|approved (for|to) list|begin(s)? trading on|"
    # v6: insider buying as Benzinga says it ("after CEO and CFO both bought company stock", "open-market share
    # purchases by its CEO and CFO").
    r"\b(ceo|cfo|chief executive|chief financial|insiders?|officers|executives)\b.{0,30}\b(bought|purchased)\b|"
    r"(share|stock) purchases? by (its |the company'?s )?(ceo|cfo|chief|director|insider|chairman|officers|executives)|"
    r"insider (buying|purchases)"
)
CATALYST_THEME_RE = (
    r"bitcoin|\bbtc\b|ethereum|solana|crypto|digital asset|\btoken|treasury (strategy|reserve)|"
    r"\bai\b|artificial intelligence|data cent(er|re)|\bgpu|quantum|drone|rare earth|nuclear|uranium|nvidia|"
    r"stablecoin|blockchain"
)

# EDGAR 8-K items when the text says nothing: item -> (kind, category, strength).
CATALYST_SEC_ITEM_FALLBACK = {
    "2.01": ("catalyst", "merger_acquisition", "strong"),
    "1.01": ("catalyst", "contract_partnership", "weak"),
    "2.02": ("catalyst", "earnings_guidance", "weak"),
    "3.02": ("negative", "offering_dilution", None),
    "3.01": ("negative", "delisting_split", None),
    "5.03": ("routine", "corporate_routine", None),
    "5.02": ("routine", "corporate_routine", None),
    "5.07": ("routine", "corporate_routine", None),
}
# EDGAR forms that are a classification on their own.
CATALYST_SEC_FORM_CLASS = {
    "424B1": ("negative", "offering_dilution", None), "424B3": ("negative", "offering_dilution", None),
    "424B4": ("negative", "offering_dilution", None), "424B5": ("negative", "offering_dilution", None),
    "S-1": ("negative", "offering_dilution", None), "F-1": ("negative", "offering_dilution", None),
    "S-3": ("negative", "offering_dilution", None), "F-3": ("negative", "offering_dilution", None),
    "425": ("routine", "merger_paperwork", None), "S-4": ("routine", "merger_paperwork", None),
    "F-4": ("routine", "merger_paperwork", None), "DEFM14A": ("routine", "merger_paperwork", None),
    "SC TO-T": ("catalyst", "merger_acquisition", "strong"), "SC 14D9": ("catalyst", "merger_acquisition", "strong"),
    "8-A12B": ("routine", "listing_paperwork", None),
    "10-Q": ("routine", "periodic_report", None), "10-K": ("routine", "periodic_report", None),
    "20-F": ("routine", "periodic_report", None),
}


# -- the live catalyst feed (catalysts/feed.py): primary sources recorded as they publish -------
CATALYST_FEED_ENV = "NOVA_CATALYST_FEED"            # "0" turns the feed off
CATALYST_DIR_ENV = "NOVA_CATALYST_DIR"               # shared with the research store's root
CATALYST_DEFAULT_ROOT_WIN = r"F:\Nova\catalysts"     # beside the research store, never inside the capture root
CATALYST_FEED_DB_FILENAME = "catalyst_feed.sqlite3"
CATALYST_FEED_SCHEMA_VERSION = 1
CATALYST_FEED_SQLITE_TIMEOUT_SEC = 30.0
CATALYST_FEED_TICK_SEC = 5.0                         # scheduler tick; each source keeps its own interval
CATALYST_FEED_SPAN_GAP_SEC = 600.0                   # polls further apart than this break a coverage span
CATALYST_FEED_MEMORY_HOURS = 40.0                    # items kept in memory for the live verdict (prior close + today)
CATALYST_FEED_HTTP_TIMEOUT_SEC = 20.0
CATALYST_FEED_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Nova-desk catalyst feed"
CATALYST_FEED_SEC_USER_AGENT_DEFAULT = "NovaDesk catalyst-feed contact@example.com"  # SEC_USER_AGENT in .env overrides
CATALYST_FEED_SEC_MIN_GAP_SEC = 0.15                 # SEC fair access: at most 10 requests / s
CATALYST_FEED_SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
CATALYST_FEED_SEC_TICKERS_TTL_SEC = 12 * 3600.0
CATALYST_FEED_EDGAR_ATOM = (
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type={form}&company=&dateb=&owner=include"
    "&start=0&count=100&output=atom"
)
CATALYST_FEED_EDGAR_FORMS = ("8-K", "6-K", "424B", "S-1", "S-3", "F-1", "F-3", "SC TO-T")
CATALYST_FEED_EDGAR_ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}"
# (source, url, poll seconds). A source whose poll shares no item with its previous poll may have
# missed a burst between the two: its coverage span is closed there and a new one opens.
CATALYST_FEED_RSS = (
    ("globenewswire", "https://rss.globenewswire.com/RssFeed/orgclass/1/feedTitle/"
                      "GlobeNewswire%20-%20News%20about%20Public%20Companies", 45.0),
    ("prnewswire", "https://www.prnewswire.com/rss/news-releases-list.rss", 30.0),
    ("fda", "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml", 300.0),
)
CATALYST_FEED_EDGAR_POLL_SEC = 60.0
# Newsfile publishes only per-industry feeds (last 10 each); these carry the small caps. Polled in turn.
CATALYST_FEED_NEWSFILE_URL = "https://feeds.newsfilecorp.com/industry/{slug}"
CATALYST_FEED_NEWSFILE_INDUSTRIES = (
    "biotechnology", "health", "cannabis", "blockchain", "technology", "computer-hardware", "semiconductors",
    "oil-gas", "energy", "alternative-energy", "aerospace-defence", "telecommunications",
    "banking-financial-services", "agriculture", "precious-metals", "mining-metals", "retail", "real-estate",
)
CATALYST_FEED_NEWSFILE_POLL_SEC = 180.0              # each industry feed; staggered across the interval
# Sources whose unbroken coverage lets the live verdict say "none found" (FDA names drugs, not tickers).
CATALYST_FEED_COVERAGE_SOURCES = ("edgar", "globenewswire", "prnewswire", "newsfile")
# US listings only: "(NASDAQ: ABCD)", "Nasdaq:ANGI", "(NYSE American: XYZ, XYZ.WS)".
CATALYST_TICKER_RE = (
    r"\b(?:NASDAQ|Nasdaq|NasdaqGM|NasdaqCM|NasdaqGS|NYSE(?:\s+American|\s+Arca|\s+MKT)?|OTCQB|OTCQX|OTC\s*Pink|"
    r"OTC(?:\s+Markets)?|Cboe(?:\s+BZX)?|CBOE)\s*[:：]\s*([A-Z]{1,5}(?:\.[A-Z]{1,2})?(?:\s*,\s*[A-Z]{1,5}(?:\.[A-Z]{1,2})?)*)"
)
# Nasdaq halt codes that mean the company's news is still to come (ADR 024 "news pending").
CATALYST_NEWS_PENDING_CODES = ("T1", "T12")
