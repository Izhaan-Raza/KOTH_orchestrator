import yaml  # always safe_load

def normalize_compose(compose_path: str) -> dict:
    with open(compose_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
        
    services = data.get("services", {})
    if not services:
        raise ValueError("compose_file has no services defined")
        
    first_service = next(iter(services.values()))
    image = first_service.get("image")
    ports = []
    
    for p in first_service.get("ports", []):
        # docker-compose short syntax: "8080:80"
        if isinstance(p, str) and ":" in p:
            host, container = p.split(":", 1)
            ports.append({"host": int(host), "container": int(container)})
            
    return {"image": image, "ports": ports}
