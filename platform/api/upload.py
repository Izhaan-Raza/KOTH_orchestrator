import os
import shutil
import uuid
import yaml
from typing import Annotated
from fastapi import APIRouter, UploadFile, File, HTTPException
from engine.registry import register_machine
from engine.normalizer import normalize_compose

router = APIRouter()

UPLOAD_DIR = "uploads"
MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB

def sanitize_filename(filename: str | None) -> str:
    if not filename:
        raise HTTPException(422, "Asset filename is required")
    name = os.path.basename(filename)
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    if not all(c in allowed for c in name):
        raise HTTPException(422, f"Filename '{name}' contains invalid characters")
    if name in ("", ".", ".."):
        raise HTTPException(422, "Invalid filename")
    return name

def validate_machine_spec(spec: dict):
    if not spec.get("name") or len(spec["name"]) > 64:
        raise HTTPException(422, "Invalid or missing name")
    if spec.get("difficulty") not in ("easy", "medium", "hard", "insane"):
        raise HTTPException(422, "Invalid difficulty")
    points = spec.get("points_per_tick", 10)
    if not isinstance(points, int) or points < 1:
        raise HTTPException(422, "points_per_tick must be >= 1")
    king_file = spec.get("king_file", "/root/king.txt")
    if not king_file.startswith("/"):
        raise HTTPException(422, "king_file must be absolute path")
        
    source_count = sum(1 for k in ("image", "dockerfile", "compose_file") if spec.get(k))
    if source_count != 1:
        raise HTTPException(422, "Exactly one of image, dockerfile, compose_file must be provided")

import zipfile

@router.post("/api/machines/upload")
async def upload_machine(
    archive: UploadFile = File(description="ZIP archive containing koth-machine.yaml and build context")
):
    if not archive.filename.endswith(".zip"):
        raise HTTPException(422, "Upload must be a .zip archive")
        
    machine_id = str(uuid.uuid4())
    machine_dir = os.path.join(UPLOAD_DIR, machine_id)
    os.makedirs(machine_dir, exist_ok=True)
    
    zip_path = os.path.join(machine_dir, "upload.zip")
    with open(zip_path, "wb") as f:
        shutil.copyfileobj(archive.file, f)
        
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(machine_dir)
    except zipfile.BadZipFile:
        shutil.rmtree(machine_dir)
        raise HTTPException(422, "Invalid or corrupted zip archive")
        
    os.remove(zip_path)
    
    yaml_path = os.path.join(machine_dir, "koth-machine.yaml")
    if not os.path.exists(yaml_path):
        shutil.rmtree(machine_dir)
        raise HTTPException(422, "Archive must contain koth-machine.yaml at its root")
        
    try:
        with open(yaml_path, "r") as f:
            spec = yaml.safe_load(f)
    except yaml.YAMLError as e:
        shutil.rmtree(machine_dir)
        raise HTTPException(422, f"Invalid YAML: {e}")
        
    try:
        validate_machine_spec(spec)
    except HTTPException as e:
        shutil.rmtree(machine_dir)
        raise e
        
    if spec.get("compose_file"):
        compose_path = os.path.join(machine_dir, spec["compose_file"])
        if not os.path.exists(compose_path):
            shutil.rmtree(machine_dir)
            raise HTTPException(422, f"Compose file {spec['compose_file']} not found in archive")
        try:
            compose_info = normalize_compose(compose_path)
            spec["image"] = compose_info["image"]
            spec["ports"] = compose_info["ports"]
        except Exception as e:
            shutil.rmtree(machine_dir)
            raise HTTPException(422, f"Invalid compose file: {e}")
            
    # Set the build_context to the extracted directory so the engine can build it
    spec["build_context"] = machine_dir
            
    db_path = os.environ.get("DB_PATH", "platform.db")
    register_machine(db_path, machine_id, spec)
    
    return {"machine_id": machine_id, "status": "registered"}
