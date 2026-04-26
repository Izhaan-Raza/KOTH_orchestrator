#!/usr/bin/env python3
"""
Elasticsearch 6.x Dynamic Scripting RCE Simulation
CVE-2014-3120 / CVE-2015-1427 (Groovy sandbox bypass)
Also simulates unauthenticated search API for scripting RCE
"""
import json
import subprocess
import http.server
import sys

FAKE_DATA = {
    "indices": ["users", "products", "logs"],
    "users": [
        {"id": 1, "username": "admin", "email": "admin@koth.local",
         "password_hash": "$2b$12$KothHashedPassword"},
        {"id": 2, "username": "alice", "email": "alice@koth.local",
         "password_hash": "$2b$12$AnotherHash"}
    ]
}

class ESHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        if self.path == '/':
            resp = {"name": "koth-node", "cluster_name": "elasticsearch",
                    "version": {"number": "6.8.23"}, "tagline": "You Know, for Search"}
        elif self.path.startswith('/_cat/indices'):
            resp = [{"index": i, "docs.count": "100"} for i in FAKE_DATA["indices"]]
        elif '/users/_search' in self.path or '/users/_doc' in self.path:
            resp = {"hits": {"hits": [{"_source": u} for u in FAKE_DATA["users"]]}}
        else:
            resp = {"status": 200}
        self.wfile.write(json.dumps(resp).encode())

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8', errors='ignore')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()

        # Simulate Groovy scripting RCE
        if '"script"' in body:
            try:
                data = json.loads(body)
                # Extract script - look for exec patterns
                script = str(data.get('script', data.get('query', {}).get('filtered', {}).get('filter', {}).get('script', {}).get('script', '')))
                # Simple RCE simulation via Runtime.exec equivalent
                if 'Runtime' in script or 'exec' in script or 'cmd' in script:
                    # Extract command from Groovy-style exec
                    import re
                    cmd_match = re.search(r'exec\(["\'](.+?)["\']\)', script)
                    if cmd_match:
                        cmd = cmd_match.group(1)
                        output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, timeout=10).decode()
                        self.wfile.write(json.dumps({"hits": {"hits": [{"_source": {"output": output}}]}}).encode())
                        return
            except Exception as e:
                pass

        self.wfile.write(json.dumps({"acknowledged": True}).encode())

    def log_message(self, fmt, *args):
        pass

if __name__ == '__main__':
    server = http.server.HTTPServer(('0.0.0.0', 9200), ESHandler)
    print('Elasticsearch 6.x stub running on port 9200')
    sys.stdout.flush()
    server.serve_forever()
