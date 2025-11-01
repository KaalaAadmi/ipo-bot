from dotenv import dotenv_values
from pymongo import MongoClient
import json
from datetime import datetime

# Load env values
env_vars = dotenv_values(".env")
MONGO_URI = env_vars.get("MONGO_URI")
DB_NAME = env_vars.get("MONGO_DATABASE_NAME", "ipo_bot_db")
COLLECTION_NAME = env_vars.get("MONGO_COLLECTION_NAME", "ipo_status")

if not MONGO_URI:
    raise ValueError("MONGO_URI not found in .env file.")

# Global client and database connection
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

collection.create_index(
    [("LiveIPOName", 1), ("IPOAnalysisTitle", 1)],
    unique=True,
    name="uniq_liveipo_analysis"
)

def upsert_ipo_status(ipo_data: dict) -> dict:
    """
    Inserts or updates a record based on (LiveIPOName, IPOAnalysisTitle).
    """
    ipo_name = ipo_data.get("LiveIPOName")
    analysis_title = ipo_data.get("IPOAnalysisTitle") or "No Analysis Found"
    if not ipo_name:
        print("Error: IPO data missing LiveIPOName for database upsert.")
        return None

    ipo_data["IPOAnalysisTitle"] = analysis_title
    ipo_data["last_updated"] = datetime.utcnow()

    result = collection.update_one(
        {"LiveIPOName": ipo_name, "IPOAnalysisTitle": analysis_title},
        {"$set": ipo_data},
        upsert=True
    )

    if result.upserted_id is not None:
        print(f"DB: Inserted new IPO status for {ipo_name} ({analysis_title}).")
    elif result.modified_count > 0:
        print(f"DB: Updated existing IPO status for {ipo_name} ({analysis_title}).")
    return ipo_data

def get_ipo_db_record_by_keys(ipo_name: str, analysis_title: str) -> dict:
    """
    Retrieve record for a specific (LiveIPOName, IPOAnalysisTitle).
    """
    return collection.find_one({"LiveIPOName": ipo_name, "IPOAnalysisTitle": analysis_title})

def is_ipo_applied(ipo_name: str) -> bool:
    """
    Returns True if any document for this IPO is marked APPLIED.
    """
    return collection.find_one({"LiveIPOName": ipo_name, "AppliedStatus": "APPLIED"}) is not None

def get_ipo_db_record(ipo_name: str) -> dict:
    """
    Backward-compat: returns one record for this IPO (unspecified which).
    Prefer get_ipo_db_record_by_keys.
    """
    return collection.find_one({"LiveIPOName": ipo_name})

def update_ipo_applied_status(ipo_name: str, status: str):
    """
    Updates AppliedStatus for all documents with this LiveIPOName.
    """
    collection.update_many(
        {"LiveIPOName": ipo_name},
        {"$set": {"AppliedStatus": status}}
    )
    print(f"DB: Updated {ipo_name} AppliedStatus to {status}.")