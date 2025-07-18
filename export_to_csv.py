import csv
from pymongo import MongoClient

# Connect to MongoDB
MONGO_URI = "mongodb+srv://sahana:sahana-123@cluster0.hl7kiqb.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client["movies_db"]
collection = db["movies"]

# Fetch all documents (you can also use a query here)
documents = list(collection.find({}, {"_id": 0}))  # Exclude MongoDB _id field

# Set CSV file name
csv_file = "movies_export.csv"

# Check if documents are not empty
if documents:
    # Get headers from keys of first document
    headers = documents[0].keys()

    # Write to CSV
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(documents)

    print(f"✅ Exported {len(documents)} records to '{csv_file}'")
else:
    print("⚠️ No data found in collection.")
