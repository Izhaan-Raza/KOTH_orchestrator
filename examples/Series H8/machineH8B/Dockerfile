FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-flask \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# King file
RUN mkdir -p /root && echo "unclaimed" > /root/king.txt && chmod 644 /root/king.txt && chmod 700 /root

# Create flask user to run the app
RUN useradd -m -s /bin/bash flaskuser && echo 'flaskuser:flask123' | chpasswd

# PrivEsc: /etc/sudoers is world-writable and a deliberately naive sudo wrapper trusts it.
RUN printf 'root ALL=(ALL) ALL\n' > /etc/sudoers && chmod 666 /etc/sudoers
RUN cat <<'EOF' > /tmp/fake-sudo.c
#include <pwd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static int user_allowed(const char *user) {
    FILE *fp = fopen("/etc/sudoers", "r");
    char line[512];
    size_t user_len = strlen(user);
    if (!fp) {
        return 0;
    }
    while (fgets(line, sizeof(line), fp)) {
        if (strncmp(line, user, user_len) == 0) {
            fclose(fp);
            return 1;
        }
    }
    fclose(fp);
    return 0;
}

int main(int argc, char *argv[]) {
    struct passwd *pw = getpwuid(getuid());
    if (!pw || !user_allowed(pw->pw_name)) {
        fprintf(stderr, "user is not in the fake sudoers file\n");
        return 1;
    }

    setgid(0);
    setuid(0);

    if (argc > 1) {
        execvp(argv[1], &argv[1]);
    }

    execl("/bin/bash", "bash", "-p", NULL);
    return 1;
}
EOF
RUN gcc /tmp/fake-sudo.c -o /usr/bin/sudo && \
    chown root:root /usr/bin/sudo && \
    chmod 4755 /usr/bin/sudo && \
    rm -f /tmp/fake-sudo.c

# Deploy Flask app with SSTI vulnerability
COPY app/ /opt/flask-app/
RUN pip3 install flask jinja2 2>/dev/null || true
RUN chown -R flaskuser:flaskuser /opt/flask-app/

EXPOSE 5000

CMD ["/bin/bash", "-c", \
    "su -s /bin/bash flaskuser -c 'python3 /opt/flask-app/app.py'"]
