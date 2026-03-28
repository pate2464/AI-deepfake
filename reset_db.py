"""Reset the fraud detector database and (optionally) uploaded files.

Usage:
    python reset_db.py          # Reset DB only, keep uploads
    python reset_db.py --all    # Reset DB + delete uploaded images
"""

import glob
import os
import sys

DB_PATHS = [
    os.path.join(os.path.dirname(__file__), "fraud_detector.db"),
    os.path.join(os.path.dirname(__file__), "backend", "fraud_detector.db"),
]

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "backend", "uploads")


def reset_db():
    removed = 0
    for db in DB_PATHS:
        if os.path.exists(db):
            os.remove(db)
            print(f"  Deleted: {db}")
            removed += 1
    # Also remove WAL/SHM journal files
    for db in DB_PATHS:
        for suffix in ("-wal", "-shm", "-journal"):
            journal = db + suffix
            if os.path.exists(journal):
                os.remove(journal)
                print(f"  Deleted: {journal}")
    if removed == 0:
        print("  No database files found — already clean.")
    else:
        print(f"  Removed {removed} database file(s).")


def reset_uploads():
    if not os.path.isdir(UPLOAD_DIR):
        print("  Upload directory does not exist — nothing to clean.")
        return
    files = glob.glob(os.path.join(UPLOAD_DIR, "*"))
    count = 0
    for f in files:
        if os.path.isfile(f):
            os.remove(f)
            count += 1
    print(f"  Removed {count} uploaded file(s) from {UPLOAD_DIR}")


def main():
    clean_all = "--all" in sys.argv

    print("=" * 50)
    print("  AI Fraud Detector — Database Reset")
    print("=" * 50)

    print("\n[1/2] Resetting database...")
    reset_db()

    if clean_all:
        print("\n[2/2] Cleaning uploaded images...")
        reset_uploads()
    else:
        print("\n[2/2] Uploads preserved (use --all to delete them too)")

    print("\nDone! Restart the backend server to recreate fresh tables.")
    print("  The server auto-creates tables on startup via init_db().")


if __name__ == "__main__":
    main()
