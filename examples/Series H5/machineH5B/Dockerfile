FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# King file
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 644 /root/king.txt && chmod 700 /root

# PrivEsc: www-data can write to /etc/passwd
RUN id -u www-data >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin www-data && \
    chown www-data:www-data /etc/passwd && chmod 666 /etc/passwd

# Bake the vulnerable service configuration into the image so the round is deterministic.
RUN mkdir -p /etc/elasticsearch && \
    printf '%s\n' \
        'cluster.name: koth-elasticsearch' \
        'network.host: 0.0.0.0' \
        'http.port: 9200' \
        'script.allowed_types: inline,stored' \
        'script.allowed_contexts: search,update,aggs' \
        > /etc/elasticsearch/elasticsearch.yml

COPY es-stub.py /opt/es-stub.py
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 9200

CMD ["/start.sh"]
