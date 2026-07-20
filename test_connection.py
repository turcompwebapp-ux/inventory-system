import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
client = gspread.authorize(creds)

sheet = client.open("inventorydata")
worksheet = sheet.worksheet("inventorydata")  # ← fixed tab name

data = worksheet.get_all_records()
print(f"✅ Connected! Found {len(data)} rows.")
print("First row sample:", data[0])