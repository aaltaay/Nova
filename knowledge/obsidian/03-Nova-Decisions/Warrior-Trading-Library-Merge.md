---
title: Warrior Trading library merge — single downloads tree
date: 2026-07-14
status: decided
tags: [warrior-trading, memory, downloads]
---

# Decision: One Warrior Trading library under `downloads/`

## Decision

**Keep a single on-disk library under `downloads/warrior-trading-*`.**  
**Do not maintain a parallel copy under `docs/warrior-trading/`.**  
**Obsidian holds inventory + pointers; Pinecone holds searchable slide/course text.**

## Why

A 2026-07-14 dashboard sync dropped ~104 files into `docs/warrior-trading/`. Diff against the existing library showed **68 exact duplicates** (same name + byte size) of slides already in `downloads/warrior-trading-slides/`. Keeping both trees wastes disk and confuses ingest/recall.

## What we do instead

1. Merge only **unique** files into `downloads/warrior-trading-slides/` or `downloads/warrior-trading-resources/`.
2. Delete duplicate trees.
3. Update [[Course-Index]] + [[Warrior-Trading/Local-Library-Inventory]].
4. Ingest **new** PDFs into Pinecone (`nova-warrior-courses` / `warrior-slides`).

## Agent rule

Before downloading Warrior course PDFs again, check `downloads/warrior-trading-slides/` and [[Warrior-Trading/Local-Library-Inventory]] for existing filenames.
