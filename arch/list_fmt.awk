BEGIN {
    COL_NAME = "\033[37m"
    COL_VER = "\033[33m"
    COL_REQ = "\033[35m"
    COL_OPT = "\033[36m"
    COL_RESET = "\033[0m"
    printf "%s%s = %s%s, %s%s, %s%s%s\n\n", COL_NAME, "Name", COL_VER, "Version", \
           COL_REQ, "Required By", COL_OPT, "Optional For", COL_RESET
}
/^Name/ { name = $3 }
/^Version/ { version = $3 }
/^Required By/ {
    req_by = $0
    gsub(/^Required By[[:space:]]*:[[:space:]]*/, "", req_by)
}
/^Optional For/ {
    opt_for = $0
    gsub(/^Optional For[[:space:]]*:[[:space:]]*/, "", opt_for)
    printf "%s%s = %s%s", COL_NAME, name, COL_VER, version
    if (req_by != "None") {
        if (length(req_by) > 30) req_by = substr(req_by, 0, 30) " ..."
        printf ", %s%s", COL_REQ, req_by
    }
    if (opt_for != "None") {
        if (length(opt_for) > 30) opt_for = substr(opt_for, 0, 30) " ..."
        printf ", %s%s", COL_OPT, opt_for
    }
    printf "%s\n", COL_RESET
}
