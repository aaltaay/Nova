"""Catalyst classifier tunables (ADR 024) -- one set of rules for the history and the live desk.

Every pattern is matched case-insensitively against a headline (EDGAR: headline plus the opening
of the press release). Order matters and lives in ``catalysts/classify.py``: noise first, then
routine announcements, then dilution, then the positive classes strongest first.
"""
from __future__ import annotations

CATALYST_RULES_VERSION = "catalyst-rules-v3-2026-09-23"

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
CATALYST_WEAK = "weak"

# A news item naming more than this many tickers is a roundup (EDGAR filings are exempt: one filer).
CATALYST_MAX_TICKERS = 3
# Opinion mills: their headlines are never a company's own catalyst.
CATALYST_OPINION_PUBLISHERS = ("the motley fool", "zacks investment research", "zacks", "investorplace")
# Sources ranked for the representative item of a verdict (a filing beats a rewrite of it).
CATALYST_SOURCE_RANK = ("edgar", "alpaca", "finnhub", "massive")
# How much of a press release's opening the classifier reads besides its headline.
CATALYST_SUMMARY_CHARS = 600
# Live desk: symbols per Alpaca request and how often a roster's catalysts are re-read.
CATALYST_LIVE_BATCH = 50
CATALYST_LIVE_TTL_SEC = 120.0

# -- noise ---------------------------------------------------------------------------------------
CATALYST_LAW_FIRM_RE = (
    r"\b(announces|launches|opens|continues|commences)\b.{0,40}\binvestigation\b|investigation on behalf|"
    r"investigation of (possible|potential)|investigating (whether|claims|potential|possible)|class action|securities fraud|"
    r"lead plaintiff|shareholder(s)? (alert|rights|reminder)|investor(s)? (alert|who (have )?lost|reminder)|"
    r"reminds? (investors|shareholders)|(lead plaintiff|filing|class action) deadline|deadline to (file|join|contact)|"
    r"rosen law|pomerantz|levi & korsinsky|bragar|hagens berman|faruqi|kessler topaz|glancy|bronstein|"
    r"schall law|gross law|kirby mcinerney|robbins llp|halper sadeh|block & leviton|johnson fistel|"
    r"encouraged to contact|secure counsel|losses? in (excess|of)|investor scrutiny|\bhbss\b"
)
CATALYST_MOVERS_RE = (
    r"\bwhy\b.{0,80}\b(shares?|stock)\b|what'?s going on|here'?s why|here'?s what|what you should know|"
    r"\b(shares?|stock)\s+(is\s+)?(jumps?|soars?|surges?|spikes?|rall(y|ies)|plunges?|tumbles?|skyrockets?|"
    r"trending|trading (higher|lower)|higher|lower|rockets?|climbs?|sinks?)\b.{0,60}\b(after hours|premarket|"
    r"pre-market|what|why|here|details|today)|stocks? (moving|to watch|making (big )?moves|on the move|in motion)|"
    r"top (gainers|losers|movers)|(premarket|pre-market|mid-?day|after-?hours) (gainers|movers|session)|"
    r"gapping|notable movement|which stocks|stock market today|market (wrap|update|recap)|"
    r"(gainers|losers) (and|&) (losers|gainers)|movers|penny stocks|what sparked|stock surge|"
    r"\b(shares?|stock) (is )?(soars?|jumps?|surges?|spikes?|plunges?|rockets?|skyrockets?|rall(y|ies)|tumbles?|"
    r"sinks?|climbs?|doubles?|triples?) (over |nearly |about |more than |almost )?\d+%|"
    r"\b(soars?|jumps?|surges?|spikes?|rockets?|skyrockets?|plunges?|tumbles?) (over |nearly |about |more than |almost )?\d+%|"
    r"\b(shares?|stock) (are|is) (trading|moving) (higher|lower)|\bshares? (up|down) \d+%|"
    r"\b(shares?|stock) (spikes?|jumps?|soars?|surges?|rises?|falls?|slides?|drops?|sinks?|plunges?|tumbles?|"
    r"rockets?) (higher|lower|after|on|as|following)|market-moving news|^(crude|oil|gold|nasdaq futures|"
    r"dow futures|s&p 500 futures|stock futures|us stocks)\b|futures (indicate|point|signal)|pending home sales|"
    r"jobless claims|drawing investor attention|\b(etf|etn)\b|\b\dx (long|short)\b|"
    r"\b(stock|shares?)\b.{0,15}\b(gains?|pops?|rall(y|ies)|crash(es)?|jumps?|surges?|soars?|sinks?|slumps?|dips?|"
    r"climbs?|rises?|falls?|drops?|plunges?|tumbles?|spikes?|slides?|moves? (higher|lower))\b.{0,12}\b(on|after|as|amid|"
    r"following)\b|\b(jumps|soars|surges|slumps|pops|rallies|crashes|tumbles|plunges) on\b|"
    r"\b(drops|rises|rebounds|gains|falls) \d+(\.\d+)?%|^(dow|s&p 500|nasdaq|stocks)\b.{0,20}\b(jumps|falls|rises|"
    r"slides|gains|drops|rall(y|ies))|deal dispatch|biotech pulse|^watching\b"
)
# Exchange halt notices: the halt is not the news (the news, if any, follows as its own item).
CATALYST_HALT_RE = r"^trading halt|halt news pending|halted at \d|quotation resumption|luld pause|halted,? (pending|news)|news pending"
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
    r"investor (conference|day)|annual (general )?meeting|results of (the )?annual|earnings release date|"
    r"(appoints|names|welcomes|announces the appointment of) .{0,60}(director|officer|board|ceo|cfo|president)|"
    r"(resign|retire)(s|ment)|annual report|notification of|form 20-f filing|earnings call (presentation|transcript)|"
    r"call transcript|(files?|filed|submits?|submitted) .{0,40}patent application|provisional patent|\bcro agreement|"
    r"planned .{0,30}(submission|filing)|plans to (submit|file)|quarterly (cash )?dividend|regular (quarterly )?dividend|"
    r"report of independent registered|disclaimer|investor presentation|corporate presentation|"
    r"\b(affirms|reaffirms|reiterates|maintains) .{0,30}guidance|extends? .{0,40}(expiration|term|maturity)|"
    r"\bclarif(ies|ication)\b|responds to (market|unusual)|labor (contract|agreement)|collective bargaining"
)
# Fluff: a release that announces motion, not an event ("reports progress", "continued advancement").
# Judged after strong catalysts and before weak ones; a results release is never fluff.
CATALYST_FLUFF_RE = (
    r"(reports|provides|announces|shares) (continued |further |recent )?(progress|advancement|momentum)|"
    r"continued advancement|continues? to (strengthen|advance|expand|build)|\badvances\b|\bdrive\b.{0,40}target|"
    r"revamped website|unveils? .{0,20}approach|new dawn|compliance-driven"
)
# EDGAR cover-page lines a headline extractor can mistake for a release title.
CATALYST_SEC_COVER_RE = (
    r"name of registrant|translation of registrant|exact name|specified in its charter|^n/?a$|"
    r"^\(?address|principal executive offices"
)
# A rebrand or ticker change is routine unless it names a theme pivot (AI, crypto ...).
CATALYST_REBRAND_RE = r"rebrand\w*|name change|chang\w+ (its )?(trading )?symbol|ticker change"
# -- negative -----------------------------------------------------------------------------------
CATALYST_OFFERING_RE = (
    r"(public|registered direct|underwritten|best[- ]efforts|follow-on|secondary)\s+offering|"
    r"private placement|pricing of|prices? .{0,60}offering|proposed offering|warrant (inducement|exercise)|"
    r"at[- ]the[- ]market|\batm\b (program|offering|facility|agreement)|equity line|"
    r"securities purchase agreement|shelf registration|convertible (notes?|preferred|debentures?)|"
    r"placement agent|underwriting agreement|announces? (an? |its )?offering|offering of [\d.,]+ ?(m|k|million)?\b|"
    r"shares and warrants|\bwarrants? to purchase"
)
CATALYST_OFFERING_ENDED_RE = r"terminat\w*.{0,40}(at[- ]the[- ]market|\batm\b|equity line|offering)"
CATALYST_DELISTING_RE = (
    r"delist|(nasdaq|nyse|listing|bid price|equity).{0,40}deficiency|deficiency (letter|notice)|"
    r"notice of non-?compliance|minimum bid price (notice|deficiency)|"
    r"reverse (stock |share )?split|going concern|bankruptcy|chapter 11"
)
# -- positive, strongest first ------------------------------------------------------------------
CATALYST_FDA_STRONG_RE = (
    r"(fda|ema|european commission|health canada|nmpa|pmda|mhra)\b.{0,60}(approv|clear(s|ed|ance)|authori[sz])|"
    r"(approv\w*|clear(s|ed|ance)|authori[sz]\w*)\b.{0,40}\b(fda|ema|health canada|nmpa|pmda|mhra)\b|"
    r"510\(k\) clearance|marketing authori[sz]ation|\bce mark\b|emergency use authori[sz]ation"
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
    r"(?<!labor )(?<!employment )\bcontract\b|\baward(ed|s)?\b|purchase order|\border(s)? (from|for|worth|valued)|supply agreement|"
    r"licens(e|ing) agreement|distribution agreement|selected by|department of (defense|energy|war)|\bdod\b|"
    r"u\.s\. (army|navy|air force|government)|\bnasa\b|\bdarpa\b|power purchase agreement|\bppa\b|"
    r"\bwins?\b.{0,40}\b(deal|contract|order|award|tender)|\bdeal\b.{0,30}(worth|valued)"
)
CATALYST_CONTRACT_WEAK_RE = (
    r"partner(s|ship)?\b|collaborat|memorandum of understanding|\bmou\b|letter of intent|\bloi\b|"
    r"strategic alliance|joint venture|integrat(es|ion) with|\bintegration\b|agreement with|pilot (program|deployment)|"
    r"\bgrant\b|funding (from|to|award)|selected (for|to)|accepted into"
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
    r"\b(sales|revenue) (drop|rise|fall|gain|jump|grow)s?\b|"
    r"\b(q[1-4]|first|second|third|fourth)"
    r"\b.{0,30}\b(quarter|results)|fiscal (year )?(20\d\d )?results|preliminary (revenue|results)|guidance"
)
CATALYST_FINANCE_POSITIVE_RE = (
    r"buyback|(share|stock) repurchase|special (cash )?dividend|strategic investment|investment (from|by)|"
    r"non-dilutive|debt (free|elimination|extinguish)|(ceo|director|insider|chairman).{0,40}(buys|purchase|"
    r"acquires|accumulates)|regains?.{0,40}complian|uplist|approved (for|to) list|begin(s)? trading on"
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
    "8-A12B": ("catalyst", "listing_financing", "weak"),
    "10-Q": ("routine", "periodic_report", None), "10-K": ("routine", "periodic_report", None),
    "20-F": ("routine", "periodic_report", None),
}
