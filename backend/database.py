"""
Storage layer with two backends:
  - Firestore (production): configure with ONE of:
      * FIREBASE_CREDENTIALS_JSON - the full contents of a Firebase/GCP
        service-account JSON key, pasted as a single env var. This is the
        easiest path on host platforms (Render, Railway, etc.) where you
        can only set env vars, not upload files.
      * GOOGLE_APPLICATION_CREDENTIALS - path to a service-account JSON
        file on disk (standard Google Cloud convention), used if
        FIREBASE_CREDENTIALS_JSON isn't set.
    Optionally set FIRESTORE_PROJECT_ID if it isn't embedded in the
    credentials you provide.
  - Local JSON file (default / demo): no setup required, good for
      development and for running the app during evaluation without
      needing a live database.

Swap is transparent to the rest of the app - always import `trip_store`
and use .save_trip() / .get_trip() / .list_trips().
"""

import os
import json
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any

FIREBASE_CREDENTIALS_JSON = os.getenv("FIREBASE_CREDENTIALS_JSON")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
FIRESTORE_PROJECT_ID = os.getenv("FIRESTORE_PROJECT_ID")
LOCAL_DB_PATH = Path(__file__).parent / "data" / "trips_db.json"

TRIPS_COLLECTION = "trips"


class FirestoreTripStore:
    def __init__(self):
        from google.cloud import firestore

        if FIREBASE_CREDENTIALS_JSON:
            from google.oauth2 import service_account

            info = json.loads(FIREBASE_CREDENTIALS_JSON)
            creds = service_account.Credentials.from_service_account_info(info)
            project_id = FIRESTORE_PROJECT_ID or info.get("project_id")
            self.client = firestore.Client(project=project_id, credentials=creds)
        else:
            # Falls back to GOOGLE_APPLICATION_CREDENTIALS / Application
            # Default Credentials (e.g. when running on Google Cloud itself).
            self.client = firestore.Client(project=FIRESTORE_PROJECT_ID)

        self.collection = self.client.collection(TRIPS_COLLECTION)

    def save_trip(self, trip: Dict[str, Any]) -> str:
        trip_id = trip.get("id") or str(uuid.uuid4())
        trip["id"] = trip_id
        self.collection.document(trip_id).set(trip)
        return trip_id

    def get_trip(self, trip_id: str) -> Optional[Dict[str, Any]]:
        doc = self.collection.document(trip_id).get()
        return doc.to_dict() if doc.exists else None

    def list_trips(self) -> List[Dict[str, Any]]:
        return [doc.to_dict() for doc in self.collection.stream()]


class LocalJsonTripStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("{}")

    def _read_all(self) -> Dict[str, Any]:
        return json.loads(self.path.read_text() or "{}")

    def _write_all(self, data: Dict[str, Any]):
        self.path.write_text(json.dumps(data, indent=2, default=str))

    def save_trip(self, trip: Dict[str, Any]) -> str:
        data = self._read_all()
        trip_id = trip.get("id") or str(uuid.uuid4())
        trip["id"] = trip_id
        data[trip_id] = trip
        self._write_all(data)
        return trip_id

    def get_trip(self, trip_id: str) -> Optional[Dict[str, Any]]:
        return self._read_all().get(trip_id)

    def list_trips(self) -> List[Dict[str, Any]]:
        return list(self._read_all().values())


def get_trip_store():
    if FIREBASE_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS:
        try:
            return FirestoreTripStore()
        except Exception as e:
            print(f"[database] Failed to connect to Firestore, falling back to local storage: {e}")
    return LocalJsonTripStore(LOCAL_DB_PATH)


trip_store = get_trip_store()
