# Graph Report - C:\Users\aalta\github\Nova\knowledge\obsidian  (2026-07-15)

## Corpus Check
- 4 files · ~0 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 51 nodes · 75 edges · 9 communities (8 shown, 1 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 9 edges (avg confidence: 0.87)
- Token cost: 6,032 input · 1,626 output

## Community Hubs (Navigation)
- Strategy Automation & Safety
- Course Memory & Library
- Nova OS Phases & Readiness
- Warrior Trading Courses
- Active Strategy Selection
- Market Data Providers
- Community 6
- Community 7
- Community 8

## God Nodes (most connected - your core abstractions)
1. `Automation Strategy Backbone` - 9 edges
2. `Nova OS Decision Brain` - 9 edges
3. `Course Index` - 7 edges
4. `Gap and Go Setup` - 7 edges
5. `Active Strategy (Nova)` - 6 edges
6. `Scanner Provider IBKR Primary` - 6 edges
7. `Five Pillars and Gap and Go Spec` - 5 edges
8. `Five Pillars Scoring` - 5 edges
9. `Alpaca Integration Reference` - 5 edges
10. `Automation Roadmap` - 5 edges

## Surprising Connections (you probably didn't know these)
- `Nova OS Status` --references--> `Control Mode Logic`  [EXTRACTED]
  knowledge/obsidian/03-Nova-Decisions/Nova-OS-Status.md → backend/nova_os/control_mode.py
- `Nova OS Status` --references--> `Nova OS Decision Logic`  [EXTRACTED]
  knowledge/obsidian/03-Nova-Decisions/Nova-OS-Status.md → backend/nova_os/decide.py
- `Five Pillars Scoring` --semantically_similar_to--> `Warrior Ross Momentum Model`  [INFERRED] [semantically similar]
  knowledge/obsidian/02-Strategies/Five-Pillars-and-Gap-and-Go-Spec.md → knowledge/obsidian/03-Nova-Decisions/Automation-Strategy-Backbone.md
- `Active Strategy Gap and Go` --semantically_similar_to--> `Gap and Go Setup`  [INFERRED] [semantically similar]
  knowledge/obsidian/03-Nova-Decisions/Active-Strategy.md → knowledge/obsidian/02-Strategies/Five-Pillars-and-Gap-and-Go-Spec.md
- `Course Index` --references--> `BA101 Transcript Index`  [EXTRACTED]
  knowledge/obsidian/01-Courses/Course-Index.md → knowledge/obsidian/01-Courses/Warrior-Trading/BA101-Timestamped-Notes.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Nova Memory Architecture** — knowledge_obsidian_00_system_graphify_knowledge_graph_graphify, knowledge_obsidian_00_system_how_recall_works_recall, knowledge_obsidian_00_system_memory_router_router [EXTRACTED 1.00]
- **Nova OS Decision Stack** — 03_nova_decisions_scanner_provider_ibkr_primary_ibkr_discovery, 03_nova_decisions_nova_os_decision_brain_decide_pipeline, 03_nova_decisions_ibkr_orders_locked_on_live_gateway_ibkr_safety_gates [EXTRACTED 1.00]
- **Gap and Go Strategy Gate Chain** — 02_strategies_five_pillars_and_gap_and_go_spec_five_pillars, 02_strategies_five_pillars_and_gap_and_go_spec_gap_and_go, 03_nova_decisions_active_strategy_gap_and_go [EXTRACTED 1.00]

## Communities (9 total, 1 thin omitted)

### Community 0 - "Strategy Automation & Safety"
Cohesion: 0.27
Nodes (10): Course Index, Pinecone Index nova-warrior-courses, DE101 Transcript Index, DE101 Platform Demos Warrior Sim, Warrior Trading Local Library Inventory, downloads/warrior-trading-* Canonical Roots, LTA Transcript Index, LTA Live Trading Archives (+2 more)

### Community 1 - "Course Memory & Library"
Cohesion: 0.24
Nodes (10): BA101 Transcript Index, BA101 Day Trading The Basics, SS101 Transcript Index, SS101 Strategies and Scaling, Alpaca Integration Reference, Alpaca-Only Features, News Impact Decision Layer, News Impact Classification (+2 more)

### Community 2 - "Nova OS Phases & Readiness"
Cohesion: 0.43
Nodes (7): Candidate Strategies for Nova, Five Pillars Scoring, Gap and Go Setup, Active Strategy (Nova), Active Strategy Gap and Go, Warrior Ross Momentum Model, Nova OS decide() Gate Pipeline

### Community 3 - "Warrior Trading Courses"
Cohesion: 0.47
Nodes (6): Five Pillars and Gap and Go Spec, Signal Only Safety Property, Automation Strategy Backbone, Local Market Data Recorders, L2 SQLite WAL Recorder, Nova OS Decision Brain

### Community 4 - "Active Strategy Selection"
Cohesion: 0.50
Nodes (5): Graphify Knowledge Graph, How Recall Works, Memory Router, Obsidian Vault, Pinecone Vector Store

### Community 5 - "Market Data Providers"
Cohesion: 0.40
Nodes (5): IBKR Orders Locked On Live Gateway, IBKR Safety Gates, Nova OS Control Modes, Nova OS Live Readiness Review, NO-GO for auto_live

### Community 6 - "Community 6"
Cohesion: 0.50
Nodes (4): Automation Roadmap, Nova OS Phases P0-P10, Automation Phases A-F, TraderVue Reporting Parity

### Community 7 - "Community 7"
Cohesion: 0.67
Nodes (3): Control Mode Logic, Nova OS Decision Logic, Nova OS Status

## Knowledge Gaps
- **10 isolated node(s):** `DE101 Platform Demos Warrior Sim`, `LTA Live Trading Archives`, `Nova OS Phases P0-P10`, `L2 SQLite WAL Recorder`, `News Impact Classification` (+5 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Scanner Provider IBKR Primary` connect `Course Memory & Library` to `Warrior Trading Courses`?**
  _High betweenness centrality (0.332) - this node is a cross-community bridge._
- **Why does `Course Index` connect `Strategy Automation & Safety` to `Course Memory & Library`?**
  _High betweenness centrality (0.257) - this node is a cross-community bridge._
- **Why does `Automation Strategy Backbone` connect `Warrior Trading Courses` to `Course Memory & Library`, `Nova OS Phases & Readiness`, `Market Data Providers`, `Community 6`?**
  _High betweenness centrality (0.196) - this node is a cross-community bridge._
- **What connects `DE101 Platform Demos Warrior Sim`, `LTA Live Trading Archives`, `Nova OS Phases P0-P10` to the rest of the system?**
  _10 weakly-connected nodes found - possible documentation gaps or missing edges._