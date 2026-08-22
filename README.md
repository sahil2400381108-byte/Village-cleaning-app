# CleanVillage — Village Cleanliness Complaint System

## Start

```powershell
cd D:\Jagruti\JagrutiAPP
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000. API documentation is at http://127.0.0.1:8000/docs.

## API

- `POST /complaints` — submit a multipart complaint
- `GET /complaints` — public complaint list (private mobile/name omitted)
- `GET /complaints/{id}` — track one complaint
- `PUT /complaints/{id}` — protected admin status update
- `GET /stats` — dashboard counts
- `POST /admin/login` — creates an authenticated admin session
- `POST /admin/logout` and `GET /admin/session` — session controls
- `GET /admin/complaints` and `GET /admin/complaints/{id}` — protected full complaint details

Data is held in `data/complaints.json`; uploaded images are in `uploads/`. JSON storage is ideal for this small local demo, but it is not suitable for high traffic, concurrent updates, or production-scale records.

## Deploy on Render

1. Create a GitHub repository and push this project to it.
2. In Render, choose **New → Blueprint**, connect the GitHub repository, then select `render.yaml`.
3. Click **Apply**. Once the deploy finishes, Render gives you a public `onrender.com` URL.

The included configuration uses Render's free web-service plan. Its filesystem is temporary, so complaints and images are reset when the app deploys or restarts. For persistent JSON and uploads, use a paid Render service with a persistent disk mounted at `/opt/render/project/src/storage`, and add the environment variable `CLEANVILLAGE_DATA_DIR=/opt/render/project/src/storage`.

## Admin login

The admin dashboard is available at `/admin`, with login at `/admin-login`. Passwords are not included in frontend files or Git.

For local development, set credentials before starting the server:

```powershell
$env:ADMIN_USERNAME = "your-admin-username"
$env:ADMIN_PASSWORD = "a-long-unique-password"
uvicorn backend.main:app --reload
```

For Render, open the **cleanvillage** service, select **Environment**, and add these values:

- `ADMIN_USERNAME` — your chosen administrator username
- `ADMIN_PASSWORD` — a strong unique password
- `COOKIE_SECURE` — `true` (required for HTTPS production sessions)

Save changes and let Render redeploy. The credentials remain private Render environment variables and are never returned by the API.
