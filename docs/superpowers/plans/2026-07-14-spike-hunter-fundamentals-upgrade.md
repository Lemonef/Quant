# Spike-Hunter Fundamentals Upgrade — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. This plan edits LLM skill files (prompt engineering), not code — validation is A/B comparison + the verdict ledger, not pytest.

**Goal:** The daily spike-hunter routine actually reads financial statements (annual/10-K, quarterly/10-Q, earnings transcripts via Bigdata MCP + SEC EDGAR) and applies the family-lesson + playbook checks; every verdict carries valuation math; a bear-case pass gates new names; the sell-detector scans balance-sheet leads. Shipped by editing the brain skill file the routine already loads — no cloud-routine prompt changes.

**Architecture:** The routine's prompt (fixed, cloud) says "read `skills/stock-analysis-SKILL.md`". All upgrades land in that file + `docs/daily-report-format-LOCKED.md` (both in `~/SecondBrain`). Drafts live beside the live files until the A/B gate passes.

**Tech Stack:** Markdown skill files in `~/SecondBrain`; A/B validation run in an interactive session with Bigdata MCP + WebFetch.

## Global Constraints

- The live `skills/stock-analysis-SKILL.md` and `docs/daily-report-format-LOCKED.md` are NOT modified until the A/B gate passes and Zen approves.
- New checks must degrade gracefully: filing not fetchable → the row reads `DATA-UNAVAILABLE`, never guessed (house rule).
- Primary sources only: EDGAR/Bigdata filings + transcripts; social/viral content stays banned for statement facts.
- Every new-skill call in the ledger is tagged `v2` so v1-vs-v2 becomes measurable at ≥50 resolved calls.
- Reference sources: brain `atoms/financial-statement-insight-playbook.md` + `atoms/investing-lessons-family-2026-07.md`; queue = Quant `docs/UPGRADE_BACKLOG.md` phase 3.

---

### Task 1: Draft the v2 skill sections

**Files:**
- Create: `~/SecondBrain/skills/stock-analysis-SKILL-v2-draft.md` (copy of live skill + new sections)
- Create: `~/SecondBrain/docs/daily-report-format-LOCKED-v2-draft.md` (copy + new rows)

- [ ] **Step 1:** Copy both live files to their `-v2-draft` names (verbatim copy first — diffs stay reviewable).
- [ ] **Step 2:** Add to the draft skill, as a new top-level section `## STATEMENT FORENSICS (mandatory for every deep-dived name)`:
  - Fetch order: latest 10-K + latest 10-Q via Bigdata `bigdata_search`/EDGAR (Thai names: SET filings, check BOI status + expiry); latest earnings-call transcript if available.
  - The compare-pairs (each rendered as a 🟢/⚠️/🔴 row): OCF vs net income (3y cumulative) · receivables growth vs revenue growth · inventory growth vs sales growth · SG&A trend + any cost line dwarfing net margin · FCF vs net income · debt maturity wall vs cash+OCF · current ratio · cash cycle trend (DSO/DIO/DPO) · share-count creep (already present — keep) · revenue-recognition red flags + policy changes · quarter decomposition (which quarter drives the YoY number; hidden strength AND weakness) · Piotroski F / Beneish M / Altman Z computed from the filing data.
  - Graceful degradation line: any unfetchable input → `DATA-UNAVAILABLE` + retry next run.
- [ ] **Step 3:** Add `## VALUATION MATH (mandatory in every verdict)`: the 1,000-baht test (state the revenue/earnings path that must exist in ~10y for today's price; believable or not, with numbers) + margin of safety (intrinsic-value estimate, method named, discount paid).
- [ ] **Step 4:** Add `## BEAR PASS (gate before 🆕 PROPOSED ADDITIONS)`: a short-seller attack on the thesis using ONLY checkable facts (statement forensics + filings); the report shows attack + survival; a name that fails the attack is logged as DROP with the reason (anti-survivorship: still enters the ledger).
- [ ] **Step 5:** Sharpen the existing SELL-DETECTOR paragraph: enumerate the balance-sheet-leads-price scan for every held name — dilution cadence, debt-wall proximity, OCF/NI divergence, going-concern language, guidance walkbacks — keep the existing PERMANENT-vs-TEMPORARY discrimination and sell-whole-or-hold rule unchanged.
- [ ] **Step 6:** Add to the draft report format: the STATEMENT FORENSICS table between PART 1 and Key Catalysts; the VALUATION MATH lines inside PART 3 Verdict; the BEAR PASS subsection before the ACTION line. Ledger row schema gains a `skill=v2` tag.
- [ ] **Step 7:** Commit the drafts to the vault (push).

### Task 2: A/B validation on three known names

- [ ] **Step 1:** In an interactive session with Bigdata connected, run THREE deep-dives twice each — once following the LIVE skill, once following the v2 DRAFT: LEU (known monster — v2 must still say ENTER-grade and surface the DOE-era statement strengths), RCAT (closed at −22.5% — v2's forensics/bear-pass must flag what v1 missed or at least flag earlier), one current watchlist name (fresh ground).
- [ ] **Step 2:** Produce a side-by-side comparison: rows only v2 caught, verdict changes, time/factual errors either way.
- [ ] **Step 3:** GATE — Zen reviews the side-by-side. Fail → revise drafts, re-run. Pass → Task 3.

### Task 3: Ship + measure

- [ ] **Step 1:** Merge drafts into the live `stock-analysis-SKILL.md` + `daily-report-format-LOCKED.md` (delete drafts), commit + push vault.
- [ ] **Step 2:** Brain pointers (Rule 9): features-log line; scheduled-routines note ("skill v2 live as of <date>, ledger rows tagged v2"); session-log entry.
- [ ] **Step 3:** Next 07:00 run: read the produced spike-scan — verify STATEMENT FORENSICS + VALUATION MATH + BEAR PASS sections rendered and no DATA-UNAVAILABLE flood. Any breakage → revert the skill file (git revert in vault) — instant rollback.
- [ ] **Step 4:** Long-run better-at-monsters metric: at ≥50 resolved v2-tagged calls, compare v1-era vs v2-era ledger hit rates in the scoreboard. This is the empirical answer to "does it actually find monsters better."
