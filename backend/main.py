from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
STORAGE_DIR = Path(os.getenv("CLEANVILLAGE_DATA_DIR", ROOT))
DATA_FILE = STORAGE_DIR / "data" / "complaints.json"
UPLOADS = STORAGE_DIR / "uploads"
FRONTEND = ROOT / "frontend"
ALLOWED_TYPES = {"image/jpeg": ".jpg", "image/png": ".png"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024
STATUSES = {"Pending", "In Progress", "Resolved"}
ID_PATTERN = re.compile(r"VC\d+", re.IGNORECASE)
COOKIE_NAME = "cleanvillage_admin"
STORE_LOCK = threading.Lock()

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
    temporary = DATA_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(DATA_FILE)


def public_complaint(item: dict) -> dict:
    return {key: value for key, value in item.items() if key not in {"name", "mobile"}}


def stats_for(items: list[dict]) -> dict:
    return {"total": len(items), "pending": sum(item.get("status") == "Pending" for item in items),
            "in_progress": sum(item.get("status") == "In Progress" for item in items),
            "resolved": sum(item.get("status") == "Resolved" for item in items)}


def admin_credentials() -> tuple[str | None, str | None]:
    return os.getenv("ADMIN_USERNAME"), os.getenv("ADMIN_PASSWORD")


def signing_key() -> bytes:
    username, password = admin_credentials()
    return hashlib.sha256(f"{username or ''}:{password or ''}".encode()).digest()


def make_session(username: str) -> str:
    expiry = int((datetime.now(timezone.utc) + timedelta(hours=8)).timestamp())
    encoded = base64.urlsafe_b64encode(f"{username}|{expiry}|{secrets.token_urlsafe(12)}".encode()).decode().rstrip("=")
    signature = hmac.new(signing_key(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def valid_session(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    encoded, signature = token.rsplit(".", 1)
    expected = hmac.new(signing_key(), encoded.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return False
    try:
        username, expiry, _ = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode().split("|", 2)
        configured_username, configured_password = admin_credentials()
        return bool(configured_password) and username == configured_username and int(expiry) > int(datetime.now(timezone.utc).timestamp())
    except (ValueError, UnicodeDecodeError):
        return False


def require_admin(cleanvillage_admin: str | None = Cookie(default=None)) -> None:
    if not valid_session(cleanvillage_admin):
        raise HTTPException(401, "Admin login required.")


def valid_id(complaint_id: str) -> str:
    if not ID_PATTERN.fullmatch(complaint_id.strip()):
        raise HTTPException(404, "Complaint not found.")
    return complaint_id.strip().upper()


@app.on_event("startup")
def on_startup() -> None:
    setup_storage()


@app.post("/complaints", status_code=201)
async def create_complaint(
    name: Annotated[str, Form()], mobile: Annotated[str, Form()], area: Annotated[str, Form()], location: Annotated[str, Form()],
    category: Annotated[str, Form()], description: Annotated[str, Form()], photo: Annotated[UploadFile | None, File()] = None,
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
    with STORE_LOCK:
        complaints = load_complaints()
        highest = max((int(item["id"][2:]) for item in complaints if ID_PATTERN.fullmatch(item.get("id", ""))), default=1000)
        item = {"id": f"VC{highest + 1}", "name": name.strip(), "mobile": mobile.strip(), "area": area.strip(), "location": location.strip(),
                "category": category, "description": description.strip(), "photo": photo_path, "status": "Pending", "created_at": datetime.now().isoformat(timespec="seconds")}
        complaints.append(item)
        save_complaints(complaints)
    return {"id": item["id"], "message": "Complaint submitted successfully."}


@app.get("/complaints")
def get_complaints():
    return [public_complaint(item) for item in reversed(load_complaints())]


@app.get("/complaints/{complaint_id}")
def get_complaint(complaint_id: str):
    complaint_id = valid_id(complaint_id)
    item = next((item for item in load_complaints() if item["id"].upper() == complaint_id), None)
    if not item:
        raise HTTPException(404, "Complaint not found.")
    return public_complaint(item)


@app.get("/stats")
def get_stats():
    return stats_for(load_complaints())


@app.post("/admin/login")
async def admin_login(payload: dict, response: Response):
    username, password = str(payload.get("username", "")), str(payload.get("password", ""))
    configured_username, configured_password = admin_credentials()
    if not configured_username or not configured_password:
        raise HTTPException(503, "Admin login is not configured.")
    if not (secrets.compare_digest(username, configured_username) and secrets.compare_digest(password, configured_password)):
        raise HTTPException(401, "Invalid admin credentials")
    response.set_cookie(COOKIE_NAME, make_session(configured_username), httponly=True, samesite="lax", secure=os.getenv("COOKIE_SECURE", "false").lower() == "true", max_age=28800)
    return {"message": "Login successful."}


@app.post("/admin/logout")
def admin_logout(response: Response):
    response.delete_cookie(COOKIE_NAME, httponly=True, samesite="lax")
    return {"message": "Logged out."}


@app.get("/admin/session")
def admin_session(cleanvillage_admin: str | None = Cookie(default=None)):
    if not valid_session(cleanvillage_admin):
        raise HTTPException(401, "Admin login required.")
    return {"authenticated": True}


@app.get("/admin/complaints")
def admin_complaints(_: None = Depends(require_admin)):
    return list(reversed(load_complaints()))


@app.get("/admin/complaints/{complaint_id}")
def admin_complaint(complaint_id: str, _: None = Depends(require_admin)):
    complaint_id = valid_id(complaint_id)
    item = next((item for item in load_complaints() if item["id"].upper() == complaint_id), None)
    if not item:
        raise HTTPException(404, "Complaint not found.")
    return item


@app.put("/complaints/{complaint_id}")
async def update_complaint(complaint_id: str, payload: dict, _: None = Depends(require_admin)):
    complaint_id = valid_id(complaint_id)
    status = payload.get("status")
    if status not in STATUSES:
        raise HTTPException(422, "Status must be Pending, In Progress, or Resolved.")
    with STORE_LOCK:
        complaints = load_complaints()
        item = next((item for item in complaints if item["id"].upper() == complaint_id), None)
        if not item:
            raise HTTPException(404, "Complaint not found.")
        item["status"] = status
        save_complaints(complaints)
    return public_complaint(item)


@app.get("/admin-login", include_in_schema=False)
def admin_login_page():
    return FileResponse(FRONTEND / "admin-login.html")


@app.get("/admin", include_in_schema=False)
def admin_page():
    return FileResponse(FRONTEND / "admin.html")


app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.get("/{page:path}", include_in_schema=False)
def serve_frontend(page: str):
    file = FRONTEND / Path("index.html" if not page else page).name
    return FileResponse(file if file.exists() and file.suffix == ".html" else FRONTEND / "index.html")
