# Graph Report - .  (2026-07-15)

## Corpus Check
- Corpus is ~13,163 words - fits in a single context window. You may not need a graph.

## Summary
- 52 nodes · 92 edges · 6 communities
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 11 edges (avg confidence: 0.88)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Strategy Automation & Safety|Strategy Automation & Safety]]
- [[_COMMUNITY_Course Memory & Library|Course Memory & Library]]
- [[_COMMUNITY_Nova OS Phases & Readiness|Nova OS Phases & Readiness]]
- [[_COMMUNITY_Warrior Trading Courses|Warrior Trading Courses]]
- [[_COMMUNITY_Active Strategy Selection|Active Strategy Selection]]
- [[_COMMUNITY_Market Data Providers|Market Data Providers]]

## God Nodes (most connected - your core abstractions)
1. `Nova OS Decision Brain` - 10 edges
2. `Memory Router` - 9 edges
3. `Automation Strategy Backbone` - 9 edges
4. `Course Index` - 8 edges
5. `Gap and Go Setup` - 8 edges
6. `Active Strategy (Nova)` - 8 edges
7. `Nova OS Status` - 7 edges
8. `Scanner Provider IBKR Primary` - 7 edges
9. `Warrior Trading Local Library Inventory` - 6 edges
10. `Automation Roadmap` - 6 edges

## Surprising Connections (you probably didn't know these)
- `Recall Router` --semantically_similar_to--> `Memory Router`  [INFERRED] [semantically similar]
  knowledge/obsidian/00-System/How-Recall-Works.md → knowledge/obsidian/00-System/Memory-Router.md
- `Five Pillars Scoring` --semantically_similar_to--> `Warrior Ross Momentum Model`  [INFERRED] [semantically similar]
  knowledge/obsidian/02-Strategies/Five-Pillars-and-Gap-and-Go-Spec.md → knowledge/obsidian/03-Nova-Decisions/Automation-Strategy-Backbone.md
- `Active Strategy Gap and Go` --semantically_similar_to--> `Gap and Go Setup`  [INFERRED] [semantically similar]
  knowledge/obsidian/03-Nova-Decisions/Active-Strategy.md → knowledge/obsidian/02-Strategies/Five-Pillars-and-Gap-and-Go-Spec.md
- `Pinecone Index nova-warrior-courses` --semantically_similar_to--> `Pinecone Course Memory`  [INFERRED] [semantically similar]
  knowledge/obsidian/01-Courses/Course-Index.md → knowledge/obsidian/00-System/How-Recall-Works.md
- `Memory Router` --references--> `Scanner Provider IBKR Primary`  [INFERRED]
  knowledge/obsidian/00-System/Memory-Router.md → knowledge/obsidian/03-Nova-Decisions/Scanner-Provider-IBKR-Primary.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Dual Memory Recall System** — 00_system_how_recall_works_pinecone, 00_system_how_recall_works_obsidian, 00_system_how_recall_works_recall_router [EXTRACTED 1.00]
- **Nova OS Decision Stack** — 03_nova_decisions_scanner_provider_ibkr_primary_ibkr_discovery, 03_nova_decisions_nova_os_decision_brain_decide_pipeline, 03_nova_decisions_ibkr_orders_locked_on_live_gateway_ibkr_safety_gates [EXTRACTED 1.00]
- **Gap and Go Strategy Gate Chain** — 02_strategies_five_pillars_and_gap_and_go_spec_five_pillars, 02_strategies_five_pillars_and_gap_and_go_spec_gap_and_go, 03_nova_decisions_active_strategy_gap_and_go [EXTRACTED 1.00]

## Communities (6 total, 0 thin omitted)

### Community 0 - "Strategy Automation & Safety"
Cohesion: 0.29
Nodes (11): Five Pillars and Gap and Go Spec, Five Pillars Scoring, Signal Only Safety Property, Automation Strategy Backbone, Warrior Ross Momentum Model, IBKR Orders Locked On Live Gateway, IBKR Safety Gates, Local Market Data Recorders (+3 more)

### Community 1 - "Course Memory & Library"
Cohesion: 0.27
Nodes (10): How Recall Works (Pinecone + Obsidian), Obsidian Decision Vault, Official LMS Captions, Pinecone Course Memory, Recall Router, Pinecone Index nova-warrior-courses, Warrior Trading Library Merge, Single downloads/ Library Decision (+2 more)

### Community 2 - "Nova OS Phases & Readiness"
Cohesion: 0.24
Nodes (10): Automation Roadmap, Nova OS Phases P0-P10, Automation Phases A-F, Nova OS Archive Restore Runbook, Nova OS Control Modes, Nova OS Live Readiness Review, NO-GO for auto_live, Nova OS Status (+2 more)

### Community 3 - "Warrior Trading Courses"
Cohesion: 0.22
Nodes (9): Course Index, BA101 Transcript Index, BA101 Day Trading The Basics, DE101 Transcript Index, DE101 Platform Demos Warrior Sim, LTA Transcript Index, LTA Live Trading Archives, SS101 Transcript Index (+1 more)

### Community 4 - "Active Strategy Selection"
Cohesion: 0.67
Nodes (6): Memory Router, Trust Order for Automation Advice, Candidate Strategies for Nova, Gap and Go Setup, Active Strategy (Nova), Active Strategy Gap and Go

### Community 5 - "Market Data Providers"
Cohesion: 0.47
Nodes (6): Alpaca Integration Reference, Alpaca-Only Features, News Impact Decision Layer, News Impact Classification, Scanner Provider IBKR Primary, IBKR Scanner Discovery

## Knowledge Gaps
- **9 isolated node(s):** `Obsidian Decision Vault`, `Official LMS Captions`, `DE101 Platform Demos Warrior Sim`, `LTA Live Trading Archives`, `L2 SQLite WAL Recorder` (+4 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Memory Router` connect `Active Strategy Selection` to `Course Memory & Library`, `Warrior Trading Courses`, `Market Data Providers`?**
  _High betweenness centrality (0.413) - this node is a cross-community bridge._
- **Why does `Scanner Provider IBKR Primary` connect `Market Data Providers` to `Strategy Automation & Safety`, `Warrior Trading Courses`, `Active Strategy Selection`?**
  _High betweenness centrality (0.260) - this node is a cross-community bridge._
- **Why does `Nova OS Decision Brain` connect `Strategy Automation & Safety` to `Nova OS Phases & Readiness`, `Active Strategy Selection`, `Market Data Providers`?**
  _High betweenness centrality (0.240) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `Memory Router` (e.g. with `Recall Router` and `Scanner Provider IBKR Primary`) actually correct?**
  _`Memory Router` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Obsidian Decision Vault`, `Official LMS Captions`, `DE101 Platform Demos Warrior Sim` to the rest of the system?**
  _10 weakly-connected nodes found - possible documentation gaps or missing edges._