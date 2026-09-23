"""The catalyst classifier (ADR 024): real headlines from the 2026 history, and the verdict rules."""
from __future__ import annotations

import pytest

from catalysts.classify import classify_item, verdict


def label(title, *args, **kw):
    lb = classify_item(title, *args, **kw)
    return (lb.kind, lb.category, lb.strength)


@pytest.mark.parametrize("title", [
    "12 Health Care Stocks Moving In Wednesday's After-Market Session",
    "Why Did Kustom Entertainment (KUST) Stock Jump Over 11% After Hours?",
    "Linkers Industries (LNKS) Stock Jumps Over 32% After Hours: Here's What Is Going On",
    "Cheetah Net Supply Chain Service (CTNT) Stock Surges Nearly 18% After Hours: What's Going On?",
    "Let's have a look at the top gainers and losers one hour before the close",
    "Which stocks are experiencing notable movement on Monday?",
    "Why Lobo Technologies Shares Are Trading Higher By Around 32%; Here Are 20 Stocks Moving Premarket",
])
def test_movers_lists_are_noise(title):
    assert label(title)[:2] == ("noise", "movers_list")


@pytest.mark.parametrize("title", [
    "ROSEN, A LEADING INVESTOR RIGHTS LAW FIRM, Encourages Nano-X Imaging Ltd. Investors to Secure Counsel Before I",
    "NNOX SHAREHOLDER ALERT: Securities Fraud Lawsuit Filed on Behalf of Nano-X Imaging Ltd. Investors",
    "Bragar Eagel & Squire, P.C Urgently Reminds Verra Mobility Corporation Investors They Have Until August 4th",
    "Fervo Energy Company (FRVO) Faces Investor Scrutiny Amid Post-IPO Transmission Curtailment Revelation - HBSS",
])
def test_law_firm_adverts_are_noise(title):
    assert label(title)[0] == "noise"


def test_opinion_mills_and_roundups_are_noise():
    assert label("Archer Aviation vs. AST SpaceMobile: Which Aerospace Stock Is a Better Buy in 2026?")[0] == "noise"
    assert label("Is Nvidia a Buy Now?", publisher="The Motley Fool")[:2] == ("noise", "opinion")
    assert label("Why This Growth Company Belongs in Your Portfolio", publisher="The Motley Fool")[:2] == ("noise", "opinion")
    assert label("SRx Health Solutions Closes EMJX Acquisition", n_tickers=6)[:2] == ("noise", "roundup")


def test_approves_an_acquisition_is_not_an_fda_approval():
    assert label("Quantum Cyber Approves Acquisition of Equity Stake in SpaceX")[:2] == ("catalyst", "merger_acquisition")


def test_an_earnings_date_is_routine_not_earnings():
    assert label("Studio City Announces Earnings Release Date")[0] == "routine"
    assert label("Acme to Report Second Quarter Results and Host Conference Call on August 12")[0] == "routine"


@pytest.mark.parametrize("title,expected", [
    ("Capricor Receives FDA Approval for Deramiocel in Duchenne Cardiomyopathy", ("catalyst", "fda_regulatory", "strong")),
    ("NorthStrive Biosciences Announces Positive Results from Phase III Program", ("catalyst", "clinical_data", "strong")),
    ("Priority Technology Holdings, Inc. Announces Definitive Agreement with Investor Group to Take Company Private",
     ("catalyst", "merger_acquisition", "strong")),
    ("Titan Mining Selected by the U.S. Army to Establish First-Ever Public-Private Partnership",
     ("catalyst", "contract_partnership", "strong")),
    ("Global Mofy Reports Record Revenue for the Six Months Ended March 31, 2026", ("catalyst", "earnings_guidance", "strong")),
    ("DCX and Whales AI Sign Non-Binding MOU for Strategic Cooperation", ("catalyst", "contract_partnership", "weak")),
    ("Bit Origin Rebrands to SANGRIX as Part of AI Infrastructure Transition", ("catalyst", "theme_pivot", "weak")),
    ("Rumble Closes Acquisition of Northern Data", ("catalyst", "merger_acquisition", "weak")),
])
def test_positive_classes(title, expected):
    assert label(title) == expected


def test_dilution_is_negative_but_ending_an_atm_is_not():
    assert label("Autonomix Medical Enters into $4.9 Million Warrant Inducement Priced at a Premium")[:2] == ("negative", "offering_dilution")
    assert label("Wellchange Holdings Announces Closing of $7.5 Million Public Offering")[:2] == ("negative", "offering_dilution")
    assert label("AmpliTech Announces $10 Million Buyback Program and Terminates At-The-Market Offering")[0] == "catalyst"
    assert label("Acme Receives Nasdaq Minimum Bid Price Notice")[:2] == ("negative", "delisting_split")


def test_edgar_reads_the_release_and_the_items():
    sec = dict(source="edgar")
    assert label("8-K: Material agreement; Regulation FD | Agrees to Acquire Vista Gold", sec_items="1.01,7.01,9.01",
                 form="8-K", **sec)[:2] == ("catalyst", "merger_acquisition")
    # No release attached and only an officer change: routine, whatever the Item text says.
    assert label("8-K: Officer / director change", "Item 5.02 ... entered into an employment agreement with",
                 sec_items="5.02,9.01", form="8-K", **sec)[0] == "routine"
    # The item name "reverse split" is not the company's words.
    assert label("8-K: Charter / bylaws (e.g. reverse split)", "", sec_items="5.03", form="8-K", **sec)[0] == "routine"
    assert label("8-K: Unregistered equity sale", "", sec_items="3.02", form="8-K", **sec)[0] == "negative"
    assert label("424B4", form="424B4", **sec)[:2] == ("negative", "offering_dilution")
    assert label("SC TO-T", form="SC TO-T", **sec) == ("catalyst", "merger_acquisition", "strong")
    assert label("425", form="425", **sec)[:2] == ("routine", "merger_paperwork")  # a deal already announced
    # A filed release no rule places is still the company's own news, never noise.
    assert label("6-K | Lion Group Holding Ltd. Reaffirms Long-Term Commitment", "", form="6-K", **sec)[0] == "catalyst"


def _item(title, ts, source="alpaca", **kw):
    return {"title": title, "published_ts": ts, "source": source, **kw}


def test_verdict_never_reads_past_the_cutoff():
    items = [_item("12 Tech Stocks Moving In Monday's Pre-Market Session", 100),
             _item("Acme Receives FDA Approval for Widget", 300)]
    early = verdict(items, window_start=0, cutoff=200, sources_answered=["alpaca"])
    assert early["verdict"] == "noise_only"
    late = verdict(items, window_start=0, cutoff=300, sources_answered=["alpaca"])
    assert (late["verdict"], late["category"], late["strength"]) == ("catalyst", "fda_regulatory", "strong")
    # The window's open is exclusive too: yesterday's news is not today's catalyst.
    assert verdict(items, window_start=300, cutoff=400, sources_answered=["alpaca"])["verdict"] == "none_found"


def test_nothing_found_needs_a_source_that_answered():
    assert verdict([], window_start=0, cutoff=1, sources_answered=[])["verdict"] == "not_checked"
    assert verdict([], window_start=0, cutoff=1, sources_answered=["edgar"])["verdict"] == "none_found"


def test_the_filing_represents_a_catalyst_over_its_rewrite_and_dilution_is_flagged():
    items = [_item("Acme Receives FDA Approval for Widget", 50, "massive"),
             _item("8-K: Other events | Acme Receives FDA Approval for Widget", 60, "edgar", form="8-K", sec_items="8.01"),
             _item("Acme Announces $5 Million Registered Direct Offering", 70, "alpaca")]
    v = verdict(items, window_start=0, cutoff=100, sources_answered=["edgar", "massive", "alpaca"])
    assert (v["verdict"], v["source"], v["negative_too"], v["n_items"]) == ("catalyst", "edgar", True, 3)


def test_only_dilution_is_negative():
    v = verdict([_item("Acme Prices $3 Million Public Offering", 5)], window_start=0, cutoff=10, sources_answered=["alpaca"])
    assert v["verdict"] == "negative"


@pytest.mark.parametrize("title,expected", [
    ("Trading Halt: Halted at 7:59:10 a.m. ET - Trading Halt: Halt News Pending", ("noise", "halt_notice")),
    ("What Sparked Sable Offshore's (SOC) 68% After-Hours Stock Surge?", ("noise", "movers_list")),
    ("Sharps Technology Stock Soars Over 50% After $400 Million Solana Treasury Bet", ("noise", "movers_list")),
    ("Roth Capital Maintains Buy on Merlin, Raises Price Target to $25", ("routine", "analyst_action")),
    ("Chardan Capital Initiates Coverage On Purple Biotech with Buy Rating", ("routine", "analyst_action")),
    ("ZeroStack Announces Offering Of 3.5M ZSTK Shares And Warrants To Purchase Up To 36,198,293 Shares",
     ("negative", "offering_dilution")),
    ("Newell Brands Q2 Adj. EPS $0.42 Beats $0.20 Estimate, Sales $1.994B Beat $1.978B Estimate",
     ("catalyst", "earnings_guidance")),
    ("Worksport Regains $1.00 Requirement To Remain Nasdaq Compliant", ("catalyst", "listing_financing")),
    ("Teva And Sanofi Announce Primary Endpoints Met In Phase 2b Trial", ("catalyst", "clinical_data")),
    ("Planet Wins EUR240M Satellite Services Deal, Funded By German Government", ("catalyst", "contract_partnership")),
])
def test_v2_rules_from_the_first_backfill_sample(title, expected):
    assert label(title)[:2] == expected


@pytest.mark.parametrize("title,expected_kind", [
    # A drug is "investigational"; a disease is a "deficiency"; neither is a law firm or a delisting.
    ("Capricor Therapeutics Says FDA Extends PDUFA Target Action Date For Its BLA For Deramiocel, Investigational Cell Therapy",
     "catalyst"),
    ("Wave Life Sciences Achieves First-Ever Therapeutic RNA Editing In Humans For Alpha-1 Antitrypsin Deficiency", "catalyst"),
    ("SeqLL Establishes Agreement With U.S. Department of Justice's Federal Bureau of Investigation", "catalyst"),
    ("Scinai Regains Compliance with Nasdaq Minimum Bid Price Requirement", "catalyst"),
    ("Acme Receives Nasdaq Deficiency Letter", "negative"),
    # Factual results stories from an opinion mill are results; an activist stake is news.
    ("Tivic Health Sales Drop 39 Percent", "catalyst"),
    ("Elliott Reports 9% Stake In E2open Parent Holdings; Believes Securities Are Undervalued", "catalyst"),
    # Why-is-it-moving and market wraps.
    ("Powell Max shares are trading higher after the company announced acquisition plans", "noise"),
    ("BrilliA Inc Soars Over 87% After Hours Following Cash Dividend Announcement", "noise"),
    ("CAPR Stock Sinks As Investors Brace For Imminent FDA Call On Deramiocel", "noise"),
    ("Summit Therapeutics shares rise after partner reports positive Phase III cancer trial results", "noise"),
    ("Crude Oil Gains 1%; US Pending Home Sales Fall In July", "noise"),
    ("Market-Moving News for September 18th", "noise"),
    # Routine, not catalysts.
    ("ZKH Group Limited 2026 Q2 - Results - Earnings Call Presentation", "routine"),
    ("Alaunos Therapeutics Filed Patent Application Identification Of Neoantigen-Reactive T Cell Receptors", "routine"),
    ("Bit Origin Announces Corporate Rebranding To SANGRIX; Changes Trading Symbol From BTOG To SGRX", "routine"),
    ("embecta Announces Quarterly Cash Dividend", "routine"),
    ("Fulcrum Therapeutics Announces Positive Initial Results from Phase 1b Trial and Will Host Conference Call",
     "catalyst"),
])
def test_rules_from_the_labelled_sample(title, expected_kind):
    assert label(title)[0] == expected_kind


def test_edgar_delisting_notice_and_slides():
    sec = dict(source="edgar", form="8-K")
    assert label("8-K: Delisting notice", "Item 3.01 ... exception to regain compliance ...", sec_items="3.01", **sec)[0] == "negative"
    assert label("8-K: Regulation FD", "Item 7.01 posted an updated investor presentation", sec_items="7.01,9.01", **sec)[0] == "routine"


@pytest.mark.parametrize("title,expected", [
    ("Hello Group Inc. Sponsored ADR (MOMO) Matches Q3 Earnings Estimates", ("catalyst", "earnings_guidance")),
    ("Macy's Posts 1.9% Comp Sales Gain in Q2", ("catalyst", "earnings_guidance")),
    ("Brookfield Confirms Discussions In Relation To A Potential Joint Offer For Grifols' Shares To Delist Them",
     ("catalyst", "merger_acquisition")),
    ("Pearson Received Second 854.2p/Share Proposal; Co. Rejected Second Proposal", ("catalyst", "merger_acquisition")),
    ("DouYu International Holdings Limited Announces Special Cash Dividend", ("catalyst", "listing_financing")),
    ("GraniteShares 2x Long LCID Daily ETF (Nasdaq: LCDL) Fund Delisting - Negative NAV", ("noise", "movers_list")),
])
def test_rules_from_the_labelled_sample_round_two(title, expected):
    assert label(title)[:2] == expected


def test_a_patent_allowance_is_not_a_patent_filing():
    assert label("Evoke Pharma Receives Notice of Allowance for U.S. Patent Application for GIMOTI")[0] == "catalyst"
    assert label("Altamira Files Second Provisional Patent Application for OligoPhore")[0] == "routine"


def test_a_filed_releases_headline_decides_dilution():
    sec = dict(source="edgar", form="8-K")
    assert label("8-K: Results of operations; Officer / director change | ACV Appoints Tim Fox as Chief Financial Officer",
                 "... the convertible notes due 2029 ...", sec_items="2.02,5.02,9.01", **sec)[0] == "routine"
    assert label("8-K: Regulation FD | Group Announces Pricing of $2.2 Million Registered Direct Offering", "",
                 sec_items="7.01,9.01", **sec)[0] == "negative"


@pytest.mark.parametrize("title,expected_kind", [
    ("Build-A-Bear Workshop Stock Gains On Special Cash Dividend, Stock Buyback", "noise"),
    ("BioXcel Therapeutics shares pop after audit of Alzheimer's trial data", "noise"),
    ("Tenax Therapeutics' stock crashes on Phase III trial failure", "noise"),
    ("DoubleVerify (NYSE:DV) Jumps on Nielsen Acquisition and EPS Beat", "noise"),
    ("Sonnet BioTherapeutics Drops 5% Intraday, Rebounds 14% After Hours Amid Delisting Concerns", "noise"),
    ("Dow Jumps Over 700 Points; Pfizer Posts Upbeat Q2 Earnings", "noise"),
    ("Eargo Shares Halted, Pending News", "noise"),
    ("SEC Concludes Investigation Into Xponential Fitness Without Action", "catalyst"),
    ("Seagate To Acquire Intevac; Intevac Shareholders To Receive $4/Share In Cash Plus A Regular Dividend", "catalyst"),
    ("Xos Affirms FY2025 Sales Guidance of $50.200M-$65.800M vs $56.211M Est", "routine"),
    ("Concrete Pumping Board Extends Expiration Date Of Buyback Plan To Nov. 30, 2028", "routine"),
    ("Horizon Quantum Clarifies Certain Information Regarding the Company", "routine"),
    ("AmeriServ Financial Announces New Labor Contract", "routine"),
    ("Jiuzi Announces Continued Advancement Of Its AI Intelligent Imaging And Data Platform", "routine"),
    ("Bone Biologics Reports Progress with NB1 Clinical Program", "routine"),
    ("Acme Reports Third Quarter Results and Provides Business Update", "catalyst"),
])
def test_rules_v3(title, expected_kind):
    assert label(title)[0] == expected_kind


def test_a_catalyst_with_its_financing_stays_a_catalyst_and_flags_dilution():
    lb = classify_item("Werewolf and Ambros Announce Merger Agreement and Concurrent Oversubscribed $150 Million Private Placement")
    assert (lb.kind, lb.category, lb.dilution) == ("catalyst", "merger_acquisition", True)
    v = verdict([_item(lb and "Werewolf and Ambros Announce Merger Agreement and Concurrent $150 Million Private Placement", 5)],
                window_start=0, cutoff=10, sources_answered=["alpaca"])
    assert v["verdict"] == "catalyst" and v["negative_too"] is True


def test_an_edgar_cover_page_is_not_a_headline():
    lb = classify_item("6-K | (Translation of registrant's name into English) Second Floor North", "", source="edgar", form="6-K")
    assert lb.kind == "routine"


@pytest.mark.parametrize("title,expected_kind", [
    ("Silo Pharma Submits Pre-Investigational New Drug Application to FDA for SPC-15", "routine"),
    ("XORTX Outlines Anticipated FDA IND Submission For XRx-026 Gout Program", "routine"),
    ("FDA Conditionally Accepts Acurx Pharmaceuticals' Brand Name CIFBEZY", "routine"),
    ("First Wave BioPharma Reaches Enrollment Target for Phase 2 SPAN Trial", "routine"),
    ("Bone Biologics CEO Issues Letter to Stockholders Highlighting Company Update", "routine"),
    ("EXCLUSIVE: OLB CEO Ronny Yakov Says Co. Will Have Capacity For Added $1.1M In Monthly Sales", "routine"),
    ("Emergent BioSolutions Announces Strategic Operational Changes to Stabilize Financial Position", "routine"),
    ("Ardelyx Announces Amendment of Debt Financing Agreement with SLR Capital Partners", "routine"),
    ("Holdings Inc. Expands its Strategic Vision into the Enterprise", "routine"),
    ("Silo Pharma Announces Filing of Patent for Treatment of Alzheimer's", "routine"),
    ("Why Cathie Wood Favorite Ginkgo Bioworks Is Surging After Hours", "noise"),
    ("Lucid Stock Rebounds After EV Maker Denies Bankruptcy Report", "noise"),
    ("Wall Street Week Ahead", "noise"),
    ("Triterras Announces Audit Committee Investigation Has Concluded Allegations Lack Support", "catalyst"),
    ("Some Breather For Novavax, Inks Multibillion-Dollar Deal With Sanofi And Erases Going Concern Doubts", "catalyst"),
    ("Velo3D Earnings Call Highlights: Revenue Surges 52% as Backlog Doubles", "catalyst"),
    ("Intermex Posts Mixed Results in Q2", "catalyst"),
    ("Affimed Presents Updated Clinical Data from Phase 1/2 Study at AACR Annual Meeting", "catalyst"),
    ("Linkers Industries Stock Jumps Over 32% After Hours: Here's What Is Going On", "noise"),
])
def test_rules_v4(title, expected_kind):
    assert label(title)[0] == expected_kind


_MOVERS_URL = "https://www.benzinga.com/trading-ideas/movers/26/09/61946086/story"


@pytest.mark.parametrize("title,kw,expected", [
    # The top gainers of 2026-09-23 (operator report: "still just seeing garbage").
    ("6-K | Circle Decarbonize Technology Limited Announces 1-for-6 Share Consolidation to Become Effective on "
     "October 7, 2026", {"source": "edgar", "form": "6-K"}, ("negative", "delisting_split")),
    ("8-K: Regulation FD | Beneficient Announces Strategy to Eliminate HCLP Debt and Heppner Equity Interests",
     {"source": "edgar", "form": "8-K", "sec_items": "7.01,9.01"}, ("catalyst", "listing_financing")),
    ("Surf Air Mobility Adds Second OperatorOS Customer With SkyDance Air",
     {"n_tickers": 2, "url": _MOVERS_URL}, ("catalyst", "contract_partnership")),
    ("Dow Falls 100 Points; General Mills Posts Upbeat Q1 Earnings", {"n_tickers": 7}, ("noise", "movers_list")),
    ("BullFrog AI Stock Surges Wednesday: What's Happening?", {"n_tickers": 1, "url": _MOVERS_URL},
     ("noise", "movers_list")),
    # A movers-section article with no named event stays a movers list; a halt notice stays a halt notice.
    ("Will Palantir, Pfizer And Oracle Stocks Continue Higher In This Trend?", {"n_tickers": 3, "url": _MOVERS_URL},
     ("noise", "movers_list")),
    ("Digital World Acquisition Shares Halted On Circuit Breaker To Upside; Up 110%", {"url": _MOVERS_URL},
     ("noise", "halt_notice")),
    ("Hoth Therapeutics Shares Resume Trading, Continue Higher", {}, ("noise", "halt_notice")),
    ("Workhorse Lands Order For 100 EV Vans From Purolator", {"url": _MOVERS_URL}, ("catalyst", "contract_partnership")),
    # "wh-at the market" is not an at-the-market offering; a forward split is not a reverse split.
    ("Can ChargePoint and Blink Charging Beat the Market?", {"publisher": "The Motley Fool"}, ("noise", "opinion")),
    ("Today's Tesla Buzz: What The Market Is Watching", {}, ("catalyst", "company_news")),
    ("Acme Announces 3-for-1 Stock Split", {}, ("catalyst", "company_news")),
    ("Eshallgo Announces 1 for 16 Share Consolidation", {}, ("negative", "delisting_split")),
    ("These 2 Stocks Likely Won't Win This Important Customer Anytime Soon", {"publisher": "The Motley Fool"},
     ("noise", "opinion")),
])
def test_rules_v5(title, kw, expected):
    assert label(title, **kw)[:2] == expected


def test_a_regulation_fd_deck_with_no_named_event_is_still_slides():
    lb = classify_item("8-K: Regulation FD | Technologies. Improved Outcomes. Forward Looking Statements Notice", "",
                       source="edgar", form="8-K", sec_items="7.01,9.01")
    assert (lb.kind, lb.category) == ("routine", "presentation")


# -- v6: the operator's second news report (2026-09-23: "most stocks don't have news, and they are moving") --

@pytest.mark.parametrize("title,summary,expected", [
    # Benzinga's one-ticker "what's going on" pieces name the cause in their summary.
    ("Beneficient Stock Skyrockets Wednesday: What's Going On?",
     "Beneficient is surging Wednesday after the company unveiled a plan to eliminate contested debt and preferred "
     "equity tied to its former CEO.", ("catalyst", "listing_financing")),
    ("BullFrog AI Holdings Stock Climbs Over 24% Pre-Market: Here's What You Need to Know",
     "BullFrog AI Holdings shares jumped over 24% in pre-market trading Wednesday after CEO and CFO both bought "
     "company stock.", ("catalyst", "listing_financing")),
    ("BullFrog AI Stock Surges Wednesday: What's Happening?",
     "BullFrog AI Holdings is trading higher Wednesday after SEC filings revealed substantial open-market share "
     "purchases by its CEO and CFO.", ("catalyst", "listing_financing")),
    ("Why Is Singularity Future Tech Stock Soaring Today?",
     "Singularity Future Technology shares surged nearly 35% after the company priced a $5 million registered direct "
     "offering to institutional investors.", ("negative", "offering_dilution")),
    ("Ming Shing Group (MSW) Stock Surges Over 200% After Hours: What's Going On?",
     "Ming Shing Group Holdings shares soared 203.62% after hours after completing its $110 million graphene "
     "acquisition.", ("catalyst", "merger_acquisition")),
    # No cause, a stated "no news", someone else's news, or only a routine reading: still a movers list.
    ("BullFrog AI Stock Surges Wednesday: What's Happening?", "", ("noise", "movers_list")),
    ("Acme Stock Is Soaring: What's Going On?",
     "Acme shares are trading higher Tuesday. There is no company-specific news after the close.",
     ("noise", "movers_list")),
    ("Acme Stock Is Soaring: What's Going On?",
     "Acme shares are trading higher in sympathy with Beta after Beta received FDA approval.", ("noise", "movers_list")),
    ("Why Target Hospitality Shares Are Shooting Higher Today",
     "Shares are trading higher after the workforce lodging company's board met.", ("noise", "movers_list")),
    ("Lucid Stock Rebounds After EV Maker Denies Bankruptcy Report: 'Completely False'",
     "Lucid Group shares are bouncing back Wednesday after the company pushed back against a report claiming it was "
     "considering going private or filing for Chapter 11 bankruptcy protection.", ("noise", "movers_list")),
    # "Days after" dates something else; an analyst piece is not the company's news.
    ("Chegg Shares Dip On Analyst Warnings About Subscriber Numbers",
     "Shares of Chegg were falling on Monday, just days after the company announced a $150 million buyback.",
     ("noise", "movers_list")),
])
def test_a_one_ticker_rewrite_is_judged_by_the_cause_it_names(title, summary, expected):
    assert label(title, summary, n_tickers=1, url=_MOVERS_URL)[:2] == expected


@pytest.mark.parametrize("title,n_tickers", [
    # One company's cause must never be pinned on every name a list carries (Finnhub gives no ticker count).
    ("Why Worthington Enterprises Shares Are Trading Higher By Around 16%; Here Are 20 Stocks Moving Premarket", None),
    ("Market-Moving News for October 21st", None),
    ("12 Health Care Stocks Moving In Wednesday's Pre-Market Session", 12),
])
def test_a_list_gives_no_ticker_its_first_names_cause(title, n_tickers):
    summary = "Worthington shares are trading higher after the company reported better-than-expected Q1 results."
    assert label(title, summary, n_tickers=n_tickers)[:2] == ("noise", "movers_list")


@pytest.mark.parametrize("title,kw,expected", [
    # ChartMill screens, filed by Finnhub under every ticker they list; its one-company recaps are rewrites.
    ("Let's take a look at the stocks that are in motion in today's session.", {"publisher": "ChartMill"},
     ("noise", "movers_list")),
    ("Unusual volume stocks in Wednesday's session", {"publisher": "ChartMill"}, ("noise", "movers_list")),
    ("Top stock movements in today's session.", {"publisher": "ChartMill"}, ("noise", "movers_list")),
    ("Pagaya Technologies (NASDAQ:PGY) Soars After Q1 Earnings Beat and Raised Guidance", {"publisher": "ChartMill"},
     ("catalyst", "earnings_guidance")),
    # Movers lists the v5 rules let through as company news.
    ("Why Did SOC, HTZ, COSM Stocks Tumble To 52-Week Lows?", {}, ("noise", "movers_list")),
    ("These stocks are moving in today's after hours session", {}, ("noise", "movers_list")),
    ("Nasdaq Surges 200 Points; Nvidia Posts Upbeat Q2 Results", {}, ("noise", "movers_list")),
    # CPOP's 6-K: the extractor caught the cover-page address, and the filing is a registered direct offering.
    ("6-K | Room 1207-08, No. 2488 Huandao East Road Huli District, Xiamen City, Fujian Province",
     {"source": "edgar", "form": "6-K", "summary": "Securities Purchase Agreement dated September 22, 2026 for "
      "665,000 Class A ordinary shares in a registered direct offering"}, ("negative", "offering_dilution")),
    # An appointment is routine, even with "the" left out.
    ("OKYO Pharma Announces Appointment of William A. Clementi as Chief Operating Officer", {},
     ("routine", "corporate_routine")),
    ("Utebzi (tebipenem pivoxil) approved in the US for adults with complicated urinary tract infections", {},
     ("catalyst", "fda_regulatory")),
])
def test_rules_v6(title, kw, expected):
    summary = kw.pop("summary", None)
    assert label(title, summary, **kw)[:2] == expected
