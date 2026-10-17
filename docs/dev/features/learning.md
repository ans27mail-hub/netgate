---
title: AI suggestions (learning)
order: 45
updated: v0.7
---
**What it does:** shows “Accept 76% · like 6 you accepted” or “Reject · like 3 you rejected as trader” on Inbox items. It never decides by itself.

## How it works
- `learn.text_of()` builds a text per contact; `hash_vector()` makes a 512-number word-hash vector (or Ollama embeddings when `learn.embed_model` is set).
- `score_items()`: nearest neighbours (K = 15) among the directory's accepted (memberships) and rejected items; the vote gives the suggestion and reason.
- `rescore_group` runs in the background after decisions. **Refresh Suggestions** in the Inbox does it now.
- `training_rows()` exports decisions as JSONL (Developer Tools) for fine-tuning later.

## Files
`app/learn.py`.
