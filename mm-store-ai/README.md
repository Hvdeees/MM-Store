# MM Store AI: an MCP server that lets AI assistants run a phone shop's back office

Staff at MM Store (a phone and electronics shop in Morocco) can ask an AI assistant, in French, Moroccan Darija or
English, and get answers from the shop's live data:

> *« Combien de coques A55 il reste ? »*  *« Chkoun li ba9i ma khlesch ? »*  *« Karim a payé 1 000 DH en espèces. »*

This project is the bridge: an **MCP server** (Model Context Protocol, the open standard AI apps like Claude use to
call real software) that exposes the [MM Store](../README.md) system as safe, well-described tools.

**Stack:** Python 3.10+ · MCP Python SDK 2.x · httpx (async) · pytest · GitHub Actions

## What the AI can do

| Tool | What it answers | Writes? |
| --- | --- | --- |
| `search_products` | Price, reseller price, stock; by name, brand, IMEI or category as staff say it ("pochettes") | no |
| `imeis_in_stock` | Which phones / computers are in stock, unit by unit | no |
| `lookup_imei` | Warranty / returns: when a device arrived, when and to whom it was sold | no |
| `sales_report` | The day's revenue, margin, payments, money received from resellers | no |
| `best_sellers` | Top products over the last N days | no |
| `resellers_overview` | Who owes the shop money, biggest debts first | no |
| `reseller_unpaid` | What a reseller took and hasn't paid, purchase by purchase, with IMEIs | no |
| `record_reseller_payment` | Records money a reseller paid, **after the person confirms** | yes |
| `confirm_payment` | Second step for apps that can't show confirmation forms | yes |

Plus a ready-made prompt, **"Point de la journée"**, for the manager's daily briefing.

## Engineering highlights

- **The AI can't confirm its own actions.** Before a payment is saved, the server sends a confirmation form straight
  to the person through the app (MCP *elicitation*). The model never sees the form or its answer, and the parameter
  isn't even in the tool's input schema. Apps without forms get a random, single-use code that expires in 5 minutes.
- **Least privilege and an audit trail.** The server uses MM Store's normal API with its own "Assistant IA" account.
  All the store's rules (roles, stock checks, validation) apply to the AI, and every payment it records says "par Assistant IA".
- **Prompt-injection aware.** Product names and notes are returned as data fields, and the server's instructions tell
  the model that tool results are never instructions. The only write path also needs a human confirmation.
- **Asks instead of guessing.** "phone hous" finds Phone House Agadir, but a name matching two shops returns both and
  makes the AI ask the person, because a payment must never land on the wrong account.
- **Errors in plain French, no leaks.** Expected problems ("Action réservée au gérant", "MM Store ne répond pas") reach
  the AI as clear messages. Unexpected crashes are reported only as "Error executing tool", so internals never leak.
- **Works on both MCP protocol generations.** The confirmation flow uses the SDK's resolver system, which asks
  mid-call on older connections and uses the new "input required" round-trip on 2026-07-28 connections. Tests cover both.
- **Tested against the real thing.** The 17 tests run the actual MM Store app in-process (httpx ASGI transport, fresh
  database each time) and talk to the server with the official MCP client. No mocks of the store, no network, no AI model.

## Set it up (macOS / Linux)

1. MM Store running (see its README). In MM Store, **Équipe → Ajouter**: create an account for the assistant
   (role *Gérant* if it should see the sales reports, *Vendeur* otherwise).
2. Install: `bash setup.sh` (or in VS Code: Terminal → Run Task → "Installer l'assistant IA").
   It prints the block to paste into the Claude desktop app's MCP configuration.
3. Restart the Claude app, then ask: *« Fais-moi le point de la journée »*.

Run the tests: `.venv/bin/pytest -v`. The end-to-end demo against a running store: `.venv/bin/python examples/demo.py`.

## Project structure

```
mmstore_ai/
  server.py         the MCP server: tools, safety rules, instructions for the model
  client.py         async client for MM Store's REST API (login, auto re-login, French errors)
  confirmations.py  single-use, expiring codes for apps without confirmation forms
  formatting.py     amounts in DH, Casablanca time, fuzzy name matching
tests/              17 tests: real MM Store in-process + official MCP client
examples/demo.py    runs the server as a subprocess over stdio, like the Claude app does
```

See [GUIDE.md](GUIDE.md) for how everything works and how to rebuild it yourself.
