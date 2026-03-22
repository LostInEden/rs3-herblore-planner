"""
RS3 Herblore Data Fetcher — Supabase version
Fetches recipe data from the RS3 wiki and pushes it to Supabase.

Usage:
    pip install requests supabase
    python fetch_rs3_potions.py
"""
import json, re, time, sys
from collections import defaultdict

try:
    import requests
except ImportError:
    print("Run: pip install requests"); sys.exit(1)

try:
    from supabase import create_client
except ImportError:
    print("Run: pip install supabase"); sys.exit(1)

# ── CONFIG ────────────────────────────────────────────────
SUPABASE_URL = "https://wvqzypwpchvmwbmcmocf.supabase.co"
SUPABASE_KEY = "sb_publishable_LZnQmDIuQ42rbZBqXBvsRg_SLMiBJpW"
WIKI_API     = "https://runescape.wiki/api.php"
HEADERS      = {"User-Agent": "RS3HerborePlanner/1.0 (personal project)"}

RECIPE_CATEGORIES = [
    "standard", "combinations", "juju", "barbarian",
    "bomb", "powerburst", "tar", "primal", "primal_pulp",
    "adrenaline", "burner", "grinding", "coconut",
    "daemonheim", "herb", "unfinished", "juju_herb",
    "juju_unfinished", "daemonheim_herb", "daemonheim_unfinished",
]

UNFINISHED_TO_HERB = {
    "Guam potion (unfinished)":"Guam","Marrentill potion (unfinished)":"Marrentill",
    "Tarromin potion (unfinished)":"Tarromin","Harralander potion (unfinished)":"Harralander",
    "Ranarr potion (unfinished)":"Ranarr weed","Toadflax potion (unfinished)":"Toadflax",
    "Irit potion (unfinished)":"Irit leaf","Avantoe potion (unfinished)":"Avantoe",
    "Kwuarm potion (unfinished)":"Kwuarm","Snapdragon potion (unfinished)":"Snapdragon",
    "Cadantine potion (unfinished)":"Cadantine","Lantadyme potion (unfinished)":"Lantadyme",
    "Dwarf weed potion (unfinished)":"Dwarf weed","Torstol potion (unfinished)":"Torstol",
    "Fellstalk potion (unfinished)":"Fellstalk","Spirit weed potion (unfinished)":"Spirit weed",
    "Arbuck potion (unfinished)":"Arbuck","Bloodweed potion (unfinished)":"Bloodweed",
    "Rogue's purse potion (unfinished)":"Rogue's purse",
    "Wergali potion (unfinished)":"Wergali","Shengo potion (unfinished)":"Shengo",
    "Samaden potion (unfinished)":"Samaden","Ugune potion (unfinished)":"Ugune",
    "Argway potion (unfinished)":"Argway","Erzille potion (unfinished)":"Erzille",
}

ALL_HERB_NAMES = set(UNFINISHED_TO_HERB.values())
CLEAN_TO_HERB = {f"clean {h.lower()}": h for h in ALL_HERB_NAMES}
CLEAN_TO_HERB.update({
    "clean ranarr":"Ranarr weed","clean ranarr weed":"Ranarr weed",
    "clean irit":"Irit leaf","clean irit leaf":"Irit leaf",
    "clean dwarf weed":"Dwarf weed","clean torstol":"Torstol",
    "clean fellstalk":"Fellstalk","clean spirit weed":"Spirit weed",
    "clean arbuck":"Arbuck","clean bloodweed":"Bloodweed",
    "clean avantoe":"Avantoe","clean lantadyme":"Lantadyme",
    "clean cadantine":"Cadantine","clean snapdragon":"Snapdragon",
})

def fetch_module(title):
    print(f"Fetching wiki module: {title}")
    r = requests.get(WIKI_API, params={
        "action":"query","format":"json","prop":"revisions",
        "titles":title,"rvprop":"content","rvslots":"main","formatversion":"2",
    }, headers=HEADERS, timeout=20)
    r.raise_for_status()
    pages = r.json()["query"]["pages"]
    if not pages or not pages[0].get("revisions"): return None
    return pages[0]["revisions"][0]["slots"]["main"]["content"]

def extract_category_block(lua, category):
    m = re.search(rf'p\.{re.escape(category)}\s*=\s*\{{', lua)
    if not m: return None
    start = m.end(); depth, i = 1, start
    while i < len(lua) and depth > 0:
        if lua[i]=='{': depth+=1
        elif lua[i]=='}': depth-=1
        i+=1
    return lua[start:i-1]

def extract_block_at(text, pos):
    depth, i = 1, pos
    while i < len(text) and depth > 0:
        if text[i]=='{': depth+=1
        elif text[i]=='}': depth-=1
        i+=1
    return text[pos:i-1]

def parse_mats_block(mats_text):
    mats = []
    i = 0
    while i < len(mats_text):
        brace = mats_text.find('{', i)
        if brace == -1: break
        entry = extract_block_at(mats_text, brace+1)
        i = brace+len(entry)+2
        name_m = re.search(r'name\s*=\s*"([^"]+)"', entry)
        qty_m  = re.search(r'qty\s*=\s*([\d.]+)', entry)
        if name_m:
            mats.append({"name":name_m.group(1).strip(),"qty":float(qty_m.group(1)) if qty_m else 1.0})
    return mats

def parse_entry_methods(entry_text):
    recipes_m = re.search(r'\brecipes\s*=\s*\{', entry_text)
    if recipes_m:
        recipes_block = extract_block_at(entry_text, recipes_m.end())
        methods = []
        i = 0
        while i < len(recipes_block):
            brace = recipes_block.find('{', i)
            if brace == -1: break
            sub = extract_block_at(recipes_block, brace+1)
            i = brace+len(sub)+2
            method_m = re.search(r'method\s*=\s*"([^"]+)"', sub)
            lvl_m    = re.search(r'\blevel\s*=\s*(\d+)', sub)
            xp_m     = re.search(r'\bxp\s*=\s*\{?\s*([\d.]+)', sub)
            mats_m   = re.search(r'\bmats\s*=\s*\{', sub)
            mats = []
            if mats_m:
                mats = parse_mats_block(extract_block_at(sub, mats_m.end()))
            if mats:
                methods.append({
                    "method": method_m.group(1) if method_m else "Default",
                    "level":  int(lvl_m.group(1)) if lvl_m else None,
                    "xp":     float(xp_m.group(1)) if xp_m else None,
                    "mats":   mats,
                })
        return methods
    mats_m = re.search(r'\bmats\s*=\s*\{', entry_text)
    if mats_m:
        mats = parse_mats_block(extract_block_at(entry_text, mats_m.end()))
        if mats: return [{"method":"Default","level":None,"xp":None,"mats":mats}]
    return []

def extract_recipes_from_block(block, category):
    recipes = []
    i = 0
    while i < len(block):
        key_start = block.find('["', i)
        if key_start == -1: break
        key_end = block.find('"]', key_start+2)
        if key_end == -1: break
        name = block[key_start+2:key_end]
        i = key_end+2
        eq = block.find('=', i)
        if eq == -1: break
        if not block[eq+1:eq+10].lstrip().startswith('{'):
            i = eq+1; continue
        brace = block.find('{', eq)
        if brace == -1: break
        entry_text = extract_block_at(block, brace+1)
        i = brace+len(entry_text)+2
        lvl_m = re.search(r'\blevel\s*=\s*(\d+)', entry_text)
        xp_m  = re.search(r'\bxp\s*=\s*\{?\s*([\d.]+)', entry_text)
        level = int(lvl_m.group(1)) if lvl_m else 0
        xp    = float(xp_m.group(1)) if xp_m else 0.0
        methods = parse_entry_methods(entry_text)
        primary = methods[0] if methods else None
        if primary:
            if primary["level"] is not None: level = primary["level"]
            if primary["xp"]    is not None: xp    = primary["xp"]
        recipes.append({
            "name":name,"category":category,"level":level,"xp":xp,
            "methods":methods,"mats":primary["mats"] if primary else [],
            "all_methods":methods,
        })
    return recipes

def classify_mat(name):
    n = name.lower()
    if "potion (unfinished)" in n: return "unfinished"
    if n in CLEAN_TO_HERB: return "clean_herb"
    if re.search(r'\(\d\)', name): return "potion_input"
    return "secondary"

def classify_tier(name, category):
    n = name.lower()
    if category in ("herb","juju_herb","daemonheim_herb","burner"): return "herb_cleaning"
    if category in ("unfinished","juju_unfinished","daemonheim_unfinished"): return "unfinished"
    if category == "combinations":
        if "elder overload" in n: return "elder_overload"
        if "supreme overload" in n: return "supreme_overload"
        if any(x in n for x in ["holy overload","aggroverload","overload salve","searing overload"]): return "overload_variant"
        return "combination"
    if category == "juju": return "juju"
    if category == "bomb": return "bomb"
    if category == "powerburst": return "powerburst"
    if category == "barbarian": return "barbarian"
    if category in ("tar","grinding","coconut","primal","primal_pulp","adrenaline"): return category
    if category == "daemonheim": return "daemonheim"
    if "elder overload" in n: return "elder_overload"
    if "supreme overload" in n: return "supreme_overload"
    if "overload" in n: return "overload"
    if "extreme" in n: return "extreme"
    if "super" in n: return "super"
    return "basic"

def structure_recipe(r):
    herb=None; secondaries=[]; potion_inputs=[]; direct_herbs=[]
    for mat in r["mats"]:
        t = classify_mat(mat["name"])
        if t=="unfinished":
            herb_name = UNFINISHED_TO_HERB.get(mat["name"]) or re.sub(r'\s*potion\s*\(unfinished\)','',mat["name"],flags=re.I).strip()
            herb = {"name":herb_name,"unfinished":mat["name"],"qty":mat["qty"]}
        elif t=="clean_herb":
            herb_name = CLEAN_TO_HERB.get(mat["name"].lower(), mat["name"])
            direct_herbs.append({"name":herb_name,"qty":mat["qty"]})
        elif t=="potion_input":
            potion_inputs.append({"name":mat["name"],"qty":mat["qty"]})
        else:
            secondaries.append({"name":mat["name"],"qty":mat["qty"]})
    return {
        "name":r["name"],"category":r["category"],
        "tier":classify_tier(r["name"],r["category"]),
        "level":r["level"],"xp":r["xp"],
        "herb":herb,"direct_herbs":direct_herbs,
        "secondaries":secondaries,"potion_inputs":potion_inputs,
        "has_alt_methods":len(r["all_methods"])>1,
    }

def build_chain_map(potions):
    def norm(n): return re.sub(r'\s*\(\d\)\s*$','',n).strip().lower()
    name_lookup = {norm(p["name"]):p["name"] for p in potions}
    used_by = defaultdict(list)
    for p in potions:
        for inp in p["potion_inputs"]:
            canonical = name_lookup.get(norm(inp["name"]), inp["name"])
            used_by[canonical].append(p["name"])
    return dict(used_by)

def build_herb_to_potions(potions):
    SKIP = {"herb_cleaning","unfinished","tar","grinding","coconut","primal","primal_pulp","adrenaline","daemonheim","barbarian"}
    direct = defaultdict(set); indirect = defaultdict(set)
    for p in potions:
        if p["tier"] in SKIP: continue
        if p["herb"]: direct[p["herb"]["name"]].add(p["name"])
        for dh in p["direct_herbs"]: direct[dh["name"]].add(p["name"])
    pot_map = {p["name"]:p for p in potions}
    def norm(n): return re.sub(r'\s*\(\d\)\s*$','',n).strip()
    norm_to_name = {norm(p["name"]):p["name"] for p in potions}
    def get_herbs(pot_name, visited=None):
        if visited is None: visited=set()
        if pot_name in visited: return set()
        visited.add(pot_name); herbs=set()
        p = pot_map.get(pot_name)
        if not p: return herbs
        if p["herb"]: herbs.add(p["herb"]["name"])
        for dh in p["direct_herbs"]: herbs.add(dh["name"])
        for inp in p["potion_inputs"]:
            inp_c = norm_to_name.get(norm(inp["name"]), inp["name"])
            herbs |= get_herbs(inp_c, visited)
        return herbs
    for p in potions:
        if p["tier"] in SKIP: continue
        all_herbs = get_herbs(p["name"])
        for herb in all_herbs:
            if p["name"] not in direct.get(herb,set()):
                indirect[herb].add(p["name"])
    all_herbs = set(direct.keys())|set(indirect.keys())
    return {h:{"direct":sorted(direct.get(h,set())),"indirect":sorted(indirect.get(h,set()))} for h in sorted(all_herbs)}

def main():
    print("="*60)
    print("RS3 Herblore Fetcher — Supabase Push")
    print("="*60)

    # 1. Fetch from wiki
    lua = fetch_module("Module:Skill calc/Herblore/data")
    if not lua: print("ERROR: Could not fetch wiki module"); sys.exit(1)
    print(f"Got {len(lua):,} chars from wiki\n")

    all_raw=[]; seen=set()
    for cat in RECIPE_CATEGORIES:
        block = extract_category_block(lua, cat)
        if not block: continue
        recipes = extract_recipes_from_block(block, cat)
        new = [r for r in recipes if r["name"] not in seen]
        for r in new: seen.add(r["name"])
        print(f"  [{cat:<25}] {len(recipes):>3} entries, {len(new):>3} new")
        all_raw.extend(new)

    potions = [structure_recipe(r) for r in all_raw]
    potions = [p for p in potions if p["level"]>0]
    potions.sort(key=lambda p:(p["level"],p["name"]))

    # Filter for app (remove cleaning/unfinished/tar etc)
    SKIP_TIERS = {"herb_cleaning","unfinished","tar","grinding","coconut","primal_pulp","burner"}
    slim_potions = [p for p in potions if p["tier"] not in SKIP_TIERS]

    chain_map      = build_chain_map(slim_potions)
    herb_to_potions = build_herb_to_potions(slim_potions)

    payload = {
        "meta": {
            "source":  "RuneScape Wiki — Module:Skill calc/Herblore/data",
            "fetched": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total":   len(slim_potions),
        },
        "herb_to_potions": herb_to_potions,
        "chain_map":       chain_map,
        "potions":         slim_potions,
    }

    print(f"\nTotal potions for app: {len(slim_potions)}")
    print(f"Herbs mapped: {len(herb_to_potions)}")

    # 2. Push to Supabase
    print("\nConnecting to Supabase...")
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Upsert into rs3_potions table (single row with all data as JSON)
    print("Pushing data to rs3_potions table...")
    result = sb.table("rs3_potions").upsert({
        "id":         1,
        "data":       payload,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }).execute()

    print(f"✅ Done! Data pushed to Supabase.")
    print(f"\nSummary:")
    print(f"  Potions:  {len(slim_potions)}")
    print(f"  Herbs:    {len(herb_to_potions)}")
    print(f"  Chains:   {sum(len(v) for v in chain_map.values())}")
    print(f"\nRe-run this script any time Jagex adds new potions.")

if __name__ == "__main__":
    main()
