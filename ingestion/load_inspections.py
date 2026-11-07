import requests  # library for calling web APIs

# Chicago Food Inspections endpoint
URL = "https://data.cityofchicago.org/resource/4ijn-s7e5.json"

# Ask for the 1,000 most recent inspections
params = {
    "$limit": 1000,
    "$order": "inspection_date DESC",
}

response = requests.get(URL, params=params, timeout=30)
response.raise_for_status()  # stop with an error if the API call failed

rows = response.json()  # turn the JSON text into a list of Python dicts

print(f"Rows returned: {len(rows)}")
print("First record:")
print(rows[0])

import json
from pathlib import Path
from datetime import date

out_dir = Path("data/raw")
out_dir.mkdir(parents=True, exist_ok=True)
out_file = out_dir / f"inspections_{date.today()}.json"
out_file.write_text(json.dumps(rows, indent=2))
print(f"Saved to {out_file}")
