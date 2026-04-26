#!/usr/bin/env python3
"""
Webmin 1.890 CVE-2019-15107 Simulation
Pre-auth RCE via password reset feature
Runs as root - exploitation drops directly to root shell
"""
import http.server
import subprocess
import urllib.parse
import ssl
import os
import sys

class WebminHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(b'''
<html><head><title>Webmin 1.890</title>
<style>body{background:#336;color:#fff;font-family:sans-serif;padding:2em;}
.login{background:#fff;color:#000;padding:2em;width:300px;margin:auto;}</style>
</head>
<body>
<div class="login">
<h2>Webmin Login</h2>
<form method=POST action=/session_login.cgi>
<p>Username: <input name=user></p>
<p>Password: <input type=password name=pass></p>
<button>Login</button>
</form>
<br><a href="/password_change.cgi">Forgot password?</a>
</div>
</body></html>''')
        elif self.path == '/password_change.cgi':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(b'''
<html><body>
<h2>Password Change</h2>
<form method=POST action=/password_change.cgi>
<p>Username: <input name=user></p>
<p>Old password: <input type=password name=old></p>
<p>New password: <input type=password name=new1></p>
<p>Confirm: <input type=password name=new2></p>
<button>Change Password</button>
</form>
</body></html>''')
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8', errors='ignore')
        params = urllib.parse.parse_qs(body)

        # CVE-2019-15107: 'old' parameter is passed to pam_auth without sanitization
        # Allows command injection via pipe character
        if self.path == '/password_change.cgi':
            old_pass = params.get('old', [''])[0]
            user = params.get('user', ['root'])[0]

            # Vulnerable: command injection in old password field
            if '|' in old_pass or ';' in old_pass or '`' in old_pass:
                # Extract and run the injected command
                cmd = old_pass.split('|', 1)[-1].strip() if '|' in old_pass else old_pass.split(';', 1)[-1].strip()
                try:
                    output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT,
                                                     timeout=10, encoding='utf-8')
                except subprocess.CalledProcessError as e:
                    output = e.output or ''
                except Exception as e:
                    output = str(e)
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(f'<pre>{output}</pre>'.encode())
                return

        self.send_response(302)
        self.send_header('Location', '/')
        self.end_headers()

    def log_message(self, fmt, *args):
        pass

if __name__ == '__main__':
    server = http.server.HTTPServer(('0.0.0.0', 10000), WebminHandler)
    print('Webmin 1.890 stub running on port 10000 (CVE-2019-15107)')
    sys.stdout.flush()
    server.serve_forever()
