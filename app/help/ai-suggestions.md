---
title: AI suggestions and learning
section: Directories & searching
order: 50
summary: How “AI suggests …%” works, and training data
---
Every **accept** and **reject** is saved with the company's details at that moment and your reason.

When a new company arrives in the Inbox, NetGate compares it with the companies you accepted into the same directory and the ones you rejected for it. The closest ones “vote”:
- *Online retailers 94% · like 23 you accepted* — it looks like ones you accepted.
- *Reject 71% · like 6 you rejected as private seller* — it looks like ones you rejected, mostly for that reason.
- *not enough decisions yet* — fewer than 3 decisions for this directory.

The more you decide (with reasons), the better the suggestions. Suggestions never decide on their own.

## Better comparisons (optional)
By default companies are compared by their words. For comparisons that understand meaning, pull an *embedding model* on the AI server (e.g. `ollama pull nomic-embed-text` on the iMac) and enter its name in Settings → AI servers → *Learning from your decisions*.

## Training data
People with *Training-data export* can download all decisions (Developer tools → Training data) as chat-style examples, ready for fine-tuning a model later on a GPU PC.
