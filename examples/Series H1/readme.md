# 👑 KoTH Orchestrator: Hour 1 (H1 Series)

This module manages the deployment and teardown of the Round 1 machines:

- **H1A** - (PHP/MySQL)
- **H1B** - (Redis/SSH Injection)
- **H1C** - (Command Injection / SUID)

## For development use only 
```bash
./orchestrator_h1.sh build
./orchestrator_h1.sh start
./orchestrator_h1.sh stop
```


## Pre-Event Preparation (CRITICAL)

Do not run the build process live during the event! Docker pulling large Ubuntu images will cause a massive delay. Run the caching command at least 24 hours before game day:

```bash
./orchestrator_h1.sh cache
```
