from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
# Set CLEANVILLAGE_DATA_DIR on a host with persistent storage (for example, a Render Disk).
STORAGE_DIR = Path(os.getenv("CLEANVILLAGE_DATA_DIR", ROOT))
DATA_FILE = STORAGE_DIR / "data" / "complaints.json"
UPLOADS = STORAGE_DIR / "uploads"
FRONTEND = ROOT / "frontend"
ALLOWED_TYPES = {"image/jpeg": ".jpg", "image/png": ".png"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024
STATUSES = {"Pending", "In Progress", "Resolved"}

app = FastAPI(title="CleanVillage API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def setup_storage() -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    UPLOADS.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists() or not DATA_FILE.read_text(encoding="utf-8").strip():
        DATA_FILE.write_text("[]", encoding="utf-8")


def load_complaints() -> list[dict]:
    setup_storage()
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def save_complaints(items: list[dict]) -> None:
    DATA_FILE.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def public_complaint(item: dict) -> dict:
    return {key: value for key, value in item.items() if key not in {"name", "mobile"}}


@app.on_event("startup")
def on_startup() -> None:
    setup_storage()


@app.post("/complaints", status_code=201)
async def create_complaint(
    name: Annotated[str, Form()], mobile: Annotated[str, Form()], area: Annotated[str, Form()],
    location: Annotated[str, Form()], category: Annotated[str, Form()], description: Annotated[str, Form()],
    photo: Annotated[UploadFile | None, File()] = None,
):
    fields = {"Full name": name, "Village / area": area, "Location": location, "Category": category, "Description": description}
    if any(not value.strip() for value in fields.values()):
        raise HTTPException(422, "Please complete every required field.")
    if not re.fullmatch(r"[6-9]\d{9}", mobile.strip()):
        raise HTTPException(422, "Enter a valid 10-digit Indian mobile number.")
    if category not in {"Garbage", "Drainage", "Sanitation", "Dirty Water", "Road Cleanliness", "Other"}:
        raise HTTPException(422, "Choose a valid complaint category.")

    photo_path = None
    if photo and photo.filename:
        if photo.content_type not in ALLOWED_TYPES:
            raise HTTPException(415, "Only JPG, JPEG and PNG images are allowed.")
        contents = await photo.read()
        if len(contents) > MAX_IMAGE_SIZE:
            raise HTTPException(413, "Image must be 5 MB or smaller.")
        filename = f"{uuid4().hex}{ALLOWED_TYPES[photo.content_type]}"
        (UPLOADS / filename).write_bytes(contents)
        photo_path = f"/uploads/{filename}"

    complaints = load_complaints()
    highest = max((int(x["id"][2:]) for x in complaints if re.fullmatch(r"VC\d+", x.get("id", ""))), default=1000)
    item = {"id": f"VC{highest + 1}", "name": name.strip(), "mobile": mobile.strip(), "area": area.strip(),
            "location": location.strip(), "category": category, "description": description.strip(), "photo": photo_path,
            "status": "Pending", "created_at": datetime.now().isoformat(timespec="seconds")}
    complaints.append(item)
    save_complaints(complaints)
    return {"id": item["id"], "message": "Complaint submitted successfully."}


@app.get("/complaints")
def get_complaints():
    return [public_complaint(item) for item in reversed(load_complaints())]


@app.get("/complaints/{complaint_id}")
def get_complaint(complaint_id: str):
    item = next((x for x in load_complaints() if x["id"].lower() == complaint_id.lower()), None)
    if not item:
        raise HTTPException(404, "Complaint not found.")
    return public_complaint(item)


@app.put("/complaints/{complaint_id}")
async def update_complaint(complaint_id: str, payload: dict):
    status = payload.get("status")
    if status not in STATUSES:
        raise HTTPException(422, "Status must be Pending, In Progress, or Resolved.")
    complaints = load_complaints()
    item = next((x for x in complaints if x["id"].lower() == complaint_id.lower()), None)
    if not item:
        raise HTTPException(404, "Complaint not found.")
    item["status"] = status
    save_complaints(complaints)
    return public_complaint(item)


@app.get("/stats")
def get_stats():
    items = load_complaints()
    return {"total": len(items), "pending": sum(x["status"] == "Pending" for x in items),
            "in_progress": sum(x["status"] == "In Progress" for x in items), "resolved": sum(x["status"] == "Resolved" for x in items)}


app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.get("/{page:path}", include_in_schema=False)
def serve_frontend(page: str):
    requested = "index.html" if not page else page
    safe_name = Path(requested).name
    file = FRONTEND / safe_name
    if file.exists() and file.suffix == ".html":
        return FileResponse(file)
    return FileResponse(FRONTEND / "index.html")
