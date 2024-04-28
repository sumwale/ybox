BEGIN {
    printf "\033[37m%s = \033[33m%s, \033[35m%s, \033[36m%s\033[0m\n\n", \
           "Name", "Version", "Required By", "Optional For"
}
/^Name/ { name=$3 }
/^Version/ { version=$3 }
/^Required By/ {
    req_by=$0
    gsub(/^Required By[[:space:]]*:[[:space:]]*/, "", req_by)
}
/^Optional For/ {
    opt_for=$0
    gsub(/^Optional For[[:space:]]*:[[:space:]]*/, "", opt_for)
    printf "\033[37m%s = \033[33m%s", name, version
    if (req_by != "None") {
        if (length(req_by) > 30) req_by = substr(req_by, 0, 30) " ..."
        printf ", \033[35m%s", req_by
    }
    if (opt_for != "None") {
        if (length(opt_for) > 30) opt_for = substr(opt_for, 0, 30) " ..."
        printf ", \033[36m%s", opt_for
    }
    printf "\033[0m\n"
}
