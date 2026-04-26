#!/usr/bin/env python3
"""
Heartbleed (CVE-2014-0160) Simulation Server
A TLS server that responds to heartbeat requests by leaking session data.
In real Heartbleed, the server leaks up to 64KB of memory containing:
- Session cookies, private keys, passwords in cleartext
"""
import socket
import ssl
import threading
import sys
import os
import struct

# Secret session data that "leaks" via Heartbleed
LEAKED_SESSION_DATA = (
    b"SESSION_ID=KOTH_ADMIN_SESSION_12345; "
    b"auth_token=Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secret; "
    b"ssh_password=web123; "
    b"username=webuser; "
    b"role=operator; "
    b"\x00" * 100  # padding
)

def handle_client(conn, addr):
    """Handle TLS connection with Heartbleed simulation"""
    try:
        data = conn.recv(4096)
        if not data:
            return

        # Detect TLS Heartbeat request (type 0x18 = 24)
        # TLS record: [type(1)] [version(2)] [length(2)] [payload]
        # Heartbeat: [0x18] [0x03 0x02] [len] [0x01] [payload_len_16bit] [padding]
        if len(data) >= 3 and data[0] == 0x18:
            # This is a heartbeat request
            # In real CVE-2014-0160: the requested length > actual payload length
            # Server responds with memory contents
            req_len = struct.unpack('>H', data[6:8])[0] if len(data) >= 8 else 100

            # Simulate memory leak - return session data
            leaked = LEAKED_SESSION_DATA[:req_len]
            heartbeat_response = struct.pack('>BHHB',
                0x18,   # heartbeat type
                0x0302, # TLS 1.1 version
                len(leaked) + 3,
                0x02    # response type
            ) + struct.pack('>H', len(leaked)) + leaked
            conn.send(heartbeat_response)
        else:
            # Regular HTTPS response
            http_response = b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nSet-Cookie: session=KOTH_ADMIN_SESSION_12345; Secure\r\n\r\n"
            http_response += b"<html><body><h1>KoTH Secure Portal</h1><p>OpenSSL 1.0.1e</p></body></html>"
            conn.send(http_response)
    except Exception:
        pass
    finally:
        conn.close()

def main():
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain('/etc/ssl/koth/server.crt', '/etc/ssl/koth/server.key')

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', 443))
        sock.listen(5)
        print("Heartbleed simulation server running on :443")
        sys.stdout.flush()
        while True:
            try:
                conn, addr = sock.accept()
                try:
                    tls_conn = ctx.wrap_socket(conn, server_side=True)
                    t = threading.Thread(target=handle_client, args=(tls_conn, addr))
                    t.daemon = True
                    t.start()
                except ssl.SSLError:
                    # Allow raw socket connections for heartbeat testing
                    t = threading.Thread(target=handle_client, args=(conn, addr))
                    t.daemon = True
                    t.start()
            except Exception:
                pass

if __name__ == '__main__':
    main()
