import os
import uuid
import json
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from engine.registry import get_machine, update_machine_status, record_deployment, stop_deployment
from engine.db import get_connection
from engine.port_manager import reserve_port_with_retry, release_port
from engine.deployer import deploy_to_node, undeploy_from_node

router = APIRouter()

class DeployRequest(BaseModel):
    machine_id: str
    node_host: str
    preferred_port: Optional[int] = None
    node_ssh_user: str = "ubuntu"

def get_db_path() -> str:
    return os.environ.get("DB_PATH", "platform.db")

def _do_deploy(db_path: str, deployment_id: str, machine: dict, req: DeployRequest):
    try:
        # Reserve port
        port = reserve_port_with_retry(db_path, req.node_host, req.preferred_port)
        
        # Deploy
        # Container name format as requested in docs
        container_name = f"koth-{machine['id'][:8]}"
        
        ports = json.loads(machine.get("ports", "[]"))
        if not ports:
            # Fallback for old/uploaded machines without port mapping
            ports = [{"container": 80}]
            
        port_mapping = {port: ports[0]["container"]}
        
        container_id = deploy_to_node(
            node_host=req.node_host,
            ssh_user=req.node_ssh_user,
            ssh_key_path=os.environ.get("SSH_KEY_PATH"),
            image=machine["image_ref"] or machine.get("name").replace(" ", "").lower(),
            container_name=container_name,
            port_mapping=port_mapping,
            king_file=machine["king_file"]
        )
        
        # Record
        record_deployment(db_path, deployment_id, machine["id"], req.node_host, req.node_ssh_user, container_id, port)
        update_machine_status(db_path, machine["id"], "active")
        
    except Exception as e:
        # Mark error
        with get_connection(db_path) as conn:
            conn.execute("UPDATE machines SET status = 'error' WHERE id = ?", (machine["id"],))
            conn.commit()

@router.post("/api/deploy")
def trigger_deploy(req: DeployRequest, background_tasks: BackgroundTasks, db_path: str = Depends(get_db_path)):
    machine = get_machine(db_path, req.machine_id)
    if not machine:
        raise HTTPException(404, "Machine not found")
        
    deployment_id = str(uuid.uuid4())
    update_machine_status(db_path, req.machine_id, "deploying")
    background_tasks.add_task(_do_deploy, db_path, deployment_id, machine, req)
    
    return {"deployment_id": deployment_id, "status": "deploying"}

@router.delete("/api/deploy/{deployment_id}")
def undeploy_machine(deployment_id: str, db_path: str = Depends(get_db_path)):
    with get_connection(db_path) as conn:
        dep = conn.execute("SELECT * FROM deployments WHERE id = ?", (deployment_id,)).fetchone()
        if not dep:
            raise HTTPException(404, "Deployment not found")
            
        dep = dict(dep)
        container_name = f"koth-{dep['machine_id'][:8]}"
        
        try:
            undeploy_from_node(
                node_host=dep["node_host"],
                ssh_user=dep["node_ssh_user"],
                ssh_key_path=os.environ.get("SSH_KEY_PATH"),
                container_name=container_name
            )
        except Exception:
            pass # Continue to clean up DB even if node fails
            
        release_port(db_path, dep["node_host"], dep["host_port"])
        stop_deployment(db_path, deployment_id)
        update_machine_status(db_path, dep["machine_id"], "stopped")
        
    return {"status": "stopped"}
