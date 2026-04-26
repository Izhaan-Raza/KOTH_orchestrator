#!/usr/bin/env python3
import argparse
import httpx
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import sys

import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), "platform", ".env"))

API_BASE = "http://localhost:8000/api"
API_KEY = os.environ.get("ADMIN_API_KEY", "")

console = Console()

def get_client():
    return httpx.Client(base_url=API_BASE, headers={"X-API-Key": API_KEY})

def print_status():
    with get_client() as client:
        try:
            machines = client.get("/machines").json()
            nodes = client.get("/nodes").json()
        except Exception as e:
            console.print(f"[bold red]Failed to connect to platform API: {e}[/bold red]")
            sys.exit(1)

    console.print(Panel("[bold cyan]KoTH Platform v2 - Terminal Control Surface[/bold cyan]", expand=False))

    # Nodes Table
    node_table = Table(title="Infrastructure Nodes", show_header=True, header_style="bold magenta")
    node_table.add_column("ID")
    node_table.add_column("Name")
    node_table.add_column("Host IP")
    node_table.add_column("Status")
    
    for n in nodes:
        node_table.add_row(n["id"][:8], n["name"], n["host_ip"], f"[green]{n['status']}[/green]")
        
    console.print(node_table)
    console.print()
    
    # Machines Table
    machine_table = Table(title="Machine Registry", show_header=True, header_style="bold blue")
    machine_table.add_column("ID")
    machine_table.add_column("Name")
    machine_table.add_column("Difficulty")
    machine_table.add_column("Status")
    machine_table.add_column("Points")
    
    for m in machines:
        status_color = "green" if m["status"] == "running" else ("yellow" if m["status"] == "registered" else "red")
        machine_table.add_row(
            m["id"][:8], 
            m["name"], 
            m["difficulty"], 
            f"[{status_color}]{m['status']}[/{status_color}]",
            str(m["points_per_tick"])
        )
        
    console.print(machine_table)

def deploy_machine(machine_id, node_host):
    console.print(f"[yellow]Triggering deployment of {machine_id} to {node_host}...[/yellow]")
    with get_client() as client:
        res = client.post("/deploy", json={
            "machine_id": machine_id,
            "node_host": node_host,
            "node_ssh_user": "ubuntu"
        })
        if res.status_code in (200, 202):
            console.print("[bold green]Deployment triggered successfully![/bold green]")
        else:
            console.print(f"[bold red]Deployment failed: {res.text}[/bold red]")

def main():
    parser = argparse.ArgumentParser(description="KoTH Platform CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Show platform status")
    
    deploy_parser = subparsers.add_parser("deploy", help="Deploy a machine to a node")
    deploy_parser.add_argument("machine_id", help="The UUID of the machine (or first 8 chars)")
    deploy_parser.add_argument("node_host", help="The IP address of the target node")

    args = parser.parse_args()

    if args.command == "status":
        print_status()
    elif args.command == "deploy":
        deploy_machine(args.machine_id, args.node_host)

if __name__ == "__main__":
    main()
