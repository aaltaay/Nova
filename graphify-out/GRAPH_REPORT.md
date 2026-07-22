# Graph Report - knowledge/obsidian  (2026-07-16)

## Corpus Check
- Corpus is ~21,476 words - fits in a single context window. You may not need a graph.

## Summary
- 45 nodes · 31 edges · 20 communities (5 shown, 15 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 1 edges (avg confidence: 0.9)
- Token cost: 49,736 input · 4,330 output

## Community Hubs (Navigation)
- Five Pillars Spec
- Memory & Graphify
- Skills & Reference
- Course Index
- Warrior Site Map
- Warrior Library
- Candidate Strategies
- Strategy Backbone
- Alpaca Integration
- IBKR Orders Lock
- Local Recorders
- News Impact Layer
- Roadmap & Status
- TraderVue Reports
- Library Merge
- Warrior Courses
- Warrior Courses
- Warrior Courses
- Warrior Courses
- Archive Restore

## God Nodes (most connected - your core abstractions)
1. `Automation Strategy Backbone` - 5 edges
2. `Nova OS Status` - 5 edges
3. `Five Pillars and Gap and Go Spec` - 4 edges
4. `Nova Roadmap Status` - 4 edges
5. `How Recall Works` - 3 edges
6. `Nova OS Decision Brain` - 3 edges
7. `Five Pillars Scoring` - 2 edges
8. `Gap and Go Setup` - 2 edges
9. `Graphify Knowledge Graph` - 2 edges
10. `Active Strategy` - 2 edges

## Surprising Connections (you probably didn't know these)
- `Nova OS Archive Restore Runbook` --references--> `restore_day_to_temp`  [INFERRED]
  03-Nova-Decisions/Nova-OS-Archive-Restore-Runbook.md → backend/archive/restore.py
- `Five Pillars and Gap and Go Spec` --references--> `Automation Strategy Backbone`  [EXTRACTED]
  C:/Users/aalta/github/Nova/knowledge/obsidian/02-Strategies/Five-Pillars-and-Gap-and-Go-Spec.md → knowledge/obsidian/03-Nova-Decisions/Automation-Strategy-Backbone.md
- `Automation Roadmap` --references--> `Nova OS Status`  [EXTRACTED]
  knowledge/obsidian/03-Nova-Decisions/Automation-Roadmap.md → knowledge/obsidian/03-Nova-Decisions/Nova-OS-Status.md
- `Active Strategy` --references--> `Automation Strategy Backbone`  [EXTRACTED]
  knowledge/obsidian/03-Nova-Decisions/Active-Strategy.md → knowledge/obsidian/03-Nova-Decisions/Automation-Strategy-Backbone.md
- `Automation Roadmap` --references--> `Automation Strategy Backbone`  [EXTRACTED]
  knowledge/obsidian/03-Nova-Decisions/Automation-Roadmap.md → knowledge/obsidian/03-Nova-Decisions/Automation-Strategy-Backbone.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Warrior Trading Curriculum** — warrior_trading_course_ba101, warrior_trading_course_ss101, warrior_trading_course_lta, warrior_trading_course_de101 [EXTRACTED 1.00]
- **Nova OS Archive Restore & Replay Flow** — 03_nova_decisions_nova_os_archive_restore_runbook, backend_archive_restore_restore_day_to_temp, tools_nova_os_replay, nova_os_decide [EXTRACTED 0.95]
- **Gap and Go Strategy Gate Chain** — 02_strategies_five_pillars_and_gap_and_go_spec_five_pillars, 02_strategies_five_pillars_and_gap_and_go_spec_gap_and_go, 03_nova_decisions_active_strategy_gap_and_go [EXTRACTED 1.00]
- **Nova Memory Architecture** — pinecone_index, obsidian_vault, graphify_out [EXTRACTED 1.00]
- **Nova OS Core Logic** — knowledge_obsidian_03_nova_decisions_nova_os_decision_brain, knowledge_obsidian_03_nova_decisions_automation_strategy_backbone, knowledge_obsidian_03_nova_decisions_active_strategy [INFERRED 0.90]
- **Warrior Trading Knowledge Base** — knowledge_obsidian_01_courses_course_index, knowledge_obsidian_01_courses_warrior_trading_authenticated_site_map, knowledge_obsidian_01_courses_warrior_trading_local_library_inventory [EXTRACTED 1.00]

## Communities (20 total, 15 thin omitted)

### Community 3 - "Five Pillars Spec"
Cohesion: 0.67
Nodes (4): Five Pillars and Gap and Go Spec, Five Pillars Scoring, Gap and Go Setup, Signal Only Safety Property

### Community 0 - "Memory & Graphify"
Cohesion: 0.33
Nodes (6): Graphify Knowledge Graph, How Recall Works, Memory Router, Pinecone Vector Index, Obsidian Knowledge Base, Graphify Output

### Community 2 - "Strategy Backbone"
Cohesion: 0.50
Nodes (5): Active Strategy, Automation Roadmap, Automation Strategy Backbone, Nova OS Decision Brain, Scanner Provider IBKR Primary

### Community 1 - "Roadmap & Status"
Cohesion: 0.40
Nodes (6): Nova OS Live Readiness Review, Nova OS Status, Nova Roadmap Status, Productization Decision, Security Status, Nova OS Decision Engine

### Community 4 - "Archive Restore"
Cohesion: 0.50
Nodes (3): Nova OS Archive Restore Runbook, restore_day_to_temp, nova_os.decide

## Knowledge Gaps
- **26 isolated node(s):** `Memory Router`, `Reference Repos`, `Skills Library`, `Course Index`, `Warrior Trading Authenticated Site Map` (+21 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **15 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Automation Strategy Backbone` connect `Strategy Backbone` to `Five Pillars Spec`?**
  _High betweenness centrality (0.053) - this node is a cross-community bridge._
- **Why does `Nova OS Status` connect `Roadmap & Status` to `Strategy Backbone`?**
  _High betweenness centrality (0.052) - this node is a cross-community bridge._
- **Why does `Five Pillars and Gap and Go Spec` connect `Five Pillars Spec` to `Strategy Backbone`?**
  _High betweenness centrality (0.037) - this node is a cross-community bridge._
- **What connects `Memory Router`, `Reference Repos`, `Skills Library` to the rest of the system?**
  _26 weakly-connected nodes found - possible documentation gaps or missing edges._