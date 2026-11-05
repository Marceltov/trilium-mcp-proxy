---
status: accepted
date: 2026-11-05
decision-makers: Marcel Bruckner
---

# Re-save notes written through the MCP tools, so Trilium records their links

## Context and Problem Statement

Trilium's MCP write tools (`create_note`, `set_note_content`, `append_to_note`, `edit_note_content`)
store a note's content without running Trilium's link scan (`saveLinks()`). The note's links are in its
content but it has no `internalLink` relations, so backlinks, the note map and `~internalLink` searches
miss them. In an LLM-maintained wiki almost every page is written this way: a lint run found 67 pages
listed as orphans that all had incoming links. Trilium's editor save and ETAPI's content PUT do scan.
How do notes written through the proxy get their links before Trilium's tools are fixed?

## Considered Options

* **Fix it in Trilium only** and wait for a release. The fix is a pull request upstream, but until it
  ships, every write adds to the backlog.
* **A periodic backfill** that re-saves all notes. It fixes the past, but links are wrong until the
  next run, and it rewrites notes nobody touched.
* **The proxy re-saves each note it sees written:** after a write tool succeeds, read the note's content
  and write it back unchanged through ETAPI, with the client's token, before answering.

## Decision Outcome

Chosen: **the proxy re-saves each written note**. It's a narrow exception to ADR 0001's "forward
unchanged": requests and results stay exactly Trilium's; the proxy only makes one extra ETAPI round trip
for the four write tools and holds back their (small) answer until it's done, so the client's next
call sees the links. It stays harmless once Trilium scans links itself (the PUT then changes nothing),
and can be removed after that release.

### Consequences

* Good, because notes written through the proxy get their backlinks and note-map edges right away.
* Good, because the tools' requests and results are untouched: clients see exactly Trilium's tools.
* Bad, because write tool answers no longer stream; they're small, so this costs only the round trip.
* Bad, because an edit made in another client between the read and the write-back would be overwritten.
  The window is the few milliseconds of one ETAPI round trip.
* Neutral, because notes written before this change, or directly against Trilium's `/mcp`, still lack
  their links until they're saved again.
