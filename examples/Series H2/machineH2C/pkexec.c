#include <stdlib.h>
#include <unistd.h>

int main(int argc, char *argv[]) {
    setgid(0);
    setuid(0);
    if (argc > 1) {
        execvp(argv[1], &argv[1]);
    }
    execl("/bin/bash", "bash", "-p", NULL);
    return 0;
}
