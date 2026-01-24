import time
import os
import json
import schedule
from ExtensionCls.MongoDB import MongoDB
from bson import json_util
from datetime import datetime
from pymongo import MongoClient

# ===== CONFIG =====
entrylog_file="backup_entry.json"
config_file="configs.json"

with open(config_file, 'r', encoding='utf-8') as file:
    configs = json.load(file)

MONGO_URI = configs['server']['uri']
DB_NAME = configs['server']['db_name']
BACKUP_FILE = "./backup.json"
# ==================

def backup_collection():
    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        vehicles = db["EmployeeParking"]
        data = list(vehicles.find({}))

        tmp_file = "cache_collection.json.tmp"

        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, default=json_util.default, ensure_ascii=False)

        os.replace(tmp_file, "cache_collection.json")

        print(f"? Backup OK [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")

    except Exception as e:
        print(f"? Backup loii: {e}")

# ===== L?CH BACKUP =====
schedule.every().day.at("13:36").do(backup_collection)
schedule.every().day.at("17:00").do(backup_collection)

print("?? Backup scheduler dang chay (06:00 & 00:00)...")

# ===== LOOP CH?Y N?N =====
while True:
    schedule.run_pending()
    time.sleep(1)
