# RS3 Herblore Planner

A RuneScape 3 herblore planning tool. Enter your herb and secondary ingredient quantities to see every potion you can make, full crafting chains, XP values, and XP rankings.

## Stack
- **Frontend**: Vanilla HTML/CSS/JS — single `index.html`
- **Backend**: Supabase (potion data + user stock persistence)
- **Deployment**: Vercel (auto-deploys on push to main)
- **Data source**: RS3 Wiki — `Module:Skill calc/Herblore/data`

## Setup

### 1. Update potion data
```bash
pip install requests supabase
python fetch_rs3_potions.py
```
This pulls fresh data from the RS3 wiki and pushes it to Supabase.

### 2. Deploy
Push to GitHub — Vercel auto-deploys.

## Data refresh
Re-run `fetch_rs3_potions.py` any time Jagex adds new potions.
