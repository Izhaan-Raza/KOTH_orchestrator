FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    rsync \
    cron \
    && rm -rf /var/lib/apt/lists/*

# King file
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 644 /root/king.txt && chmod 700 /root

# Create a low-priv user
RUN useradd -m -s /bin/bash rsyncuser && echo 'rsyncuser:rsync123' | chpasswd

# RSync exposed module - anonymous write lands directly in the PATH hijack directory.
RUN mkdir -p /opt/tools && chmod 777 /opt/tools
COPY rsyncd.conf /etc/rsyncd.conf

# PrivEsc: Root script runs ls from a PATH that includes the rsync-writable directory.
RUN printf '#!/bin/bash\nls /opt/tools/\n' > /opt/tools/run-report.sh && \
    chmod 755 /opt/tools/run-report.sh

# Root cron calls run-report.sh which calls 'ls' without full path
RUN echo "* * * * * root PATH=/opt/tools:/tmp:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin /opt/tools/run-report.sh > /tmp/report.txt 2>&1" >> /etc/crontab

EXPOSE 873

CMD ["/bin/bash", "-c", "service cron start && rsync --daemon --no-detach --config=/etc/rsyncd.conf"]
