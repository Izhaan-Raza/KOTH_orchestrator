import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from engine.db import apply_migrations, get_connection
from api import machines, upload, deploy, setup, accounts, nodes, legacy

load_dotenv()

def require_admin_api_key(x_api_key: str | None = Header(default=None)):
    expected_key = os.environ.get("ADMIN_API_KEY")
    allow_unsafe = os.environ.get("ALLOW_UNSAFE_NO_ADMIN_API_KEY", "false").lower() == "true"
    
    if not expected_key:
        if allow_unsafe:
            return
        raise HTTPException(status_code=500, detail="Server misconfigured: ADMIN_API_KEY not set")
        
    if x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Unauthorized")

@asynccontextmanager
async def lifespan(app: FastAPI):
    db_path = os.environ.get("DB_PATH", "platform.db")
    migrations_dir = os.path.join(os.path.dirname(__file__), "migrations")
    
    # Initialize DB
    apply_migrations(db_path, migrations_dir)
    
    # Ensure upload dir exists
    upload_dir = os.environ.get("UPLOAD_DIR", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    
    yield
    
app = FastAPI(title="KoTH Platform Server", lifespan=lifespan)

# Add routers with dependencies (except for public endpoints handled directly)
app.include_router(machines.router)
app.include_router(setup.router)
app.include_router(upload.router, dependencies=[Depends(require_admin_api_key)])
app.include_router(deploy.router, dependencies=[Depends(require_admin_api_key)])
app.include_router(accounts.router, dependencies=[Depends(require_admin_api_key)])
app.include_router(nodes.router, dependencies=[Depends(require_admin_api_key)])
app.include_router(legacy.router, dependencies=[Depends(require_admin_api_key)])

# UI Setup
static_dir = os.path.join(os.path.dirname(__file__), "static")
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
os.makedirs(static_dir, exist_ok=True)
os.makedirs(os.path.join(static_dir, "css"), exist_ok=True)
os.makedirs(os.path.join(static_dir, "js"), exist_ok=True)
os.makedirs(templates_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)

def is_setup_complete(db_path: str) -> bool:
    try:
        with get_connection(db_path) as conn:
            user = conn.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
            return user is not None
    except Exception:
        return False

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    db_path = os.environ.get("DB_PATH", "platform.db")
    if is_setup_complete(db_path):
        return RedirectResponse(url="/dashboard")
    return RedirectResponse(url="/setup")

@app.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    db_path = os.environ.get("DB_PATH", "platform.db")
    if is_setup_complete(db_path):
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="setup.html")

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    db_path = os.environ.get("DB_PATH", "platform.db")
    if not is_setup_complete(db_path):
        return RedirectResponse(url="/setup")
    return templates.TemplateResponse(request=request, name="dashboard.html")

@app.get("/health")
def health_check():
    return {"status": "ok"}
