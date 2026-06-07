"""Snapshot what the bot sees right now: per-coin regime, breakout distance, open positions."""
import json
from pathlib import Path
import paper_bot as b

HERE=Path(__file__).parent
st=json.loads((HERE/"state.json").read_text()) if (HERE/"state.json").exists() else {"coins":{}}
print(f"{'coin':9s} {'price':>11s} {'>MA200':>7s} {'ADX':>5s} {'55-high':>11s} {'to brk%':>8s} {'pos':>6s}")
for c in b.COINS:
    try: df=b.fetch(c)
    except Exception as e: print(f"{c:9s} fetch fail"); continue
    atr,adx,ma,donHi,donLo=b.indicators(df)
    i=len(df)-2
    price=df.c.iloc[i]; brk=donHi.iloc[i-1]
    above = price>ma.iloc[i]
    tobrk = (brk/price-1)*100
    pos=st["coins"].get(c,{}).get("units",0)
    held = "LONG" if pos>0 else "-"
    print(f"{c:9s} {price:>11.4f} {('yes' if above else 'no'):>7s} {adx.iloc[i]:>5.1f} {brk:>11.4f} {tobrk:>7.2f}% {held:>6s}")
eq=st.get("equity","?")
print(f"\nequity: ${eq}  last_run: {st.get('last_run','-')}")
