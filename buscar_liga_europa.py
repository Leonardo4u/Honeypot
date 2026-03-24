import sys
import requests
import os
from dotenv import load_dotenv

load_dotenv()

r = requests.get(
    'https://api.the-odds-api.com/v4/sports',
    params={'apiKey': os.getenv('ODDS_API_KEY')}
)

ligas = [l for l in r.json() if 'europa' in l['key'].lower() or 'europa' in l['title'].lower()]
for l in ligas:
    print(l['key'], '—', l['title'])