#!/bin/bash
# Start indiserver and the INDINexus web bridge, and tie the container's fate to both.
#
# indiserver launches every driver with exec(), so a driver has to be an executable
# file. A Python driver written against the INDINexus SDK usually is not: it is a .py
# file copied out of examples/ or bind-mounted from a host that did not set the
# executable bit. So a .py spec is wrapped in a one-line shim that runs it under this
# image's interpreter, where indi_nexus is importable. The interop suite has the same
# problem and solves it the same way (the python_driver fixture in
# tests/interop/conftest.py).
#
# Configuration, all optional:
#   INDI_DRIVERS     space-separated drivers: a name on PATH (indi_simulator_telescope),
#                    a path to an executable, or a path to a .py file.
#   INDI_DRIVER_DIR  a directory whose entries are appended to that list (/drivers).
#   INDI_PORT        the port indiserver listens on (7624).
#   WEB_HOST         the address the bridge binds to (0.0.0.0).
#   WEB_PORT         the port the bridge listens on (8000).
#   WEB_TOKEN        the shared token /ws and /api require. Unset, one is generated
#                    and printed; set it to keep the panel's URL stable across a
#                    `restart: unless-stopped`.
#   WEB_ALLOW_ANONYMOUS  set to any value to serve with no token at all. The
#                    published port is then an unauthenticated control surface for
#                    the instrument, for anything that can reach the host.
#   WEB_ALLOWED_ORIGINS  space-separated browser origins to accept in addition to
#                    the bridge's own, for a front end served from elsewhere.
#
# To run something else entirely - the panel against a hub in another container, say -
# override the container command, which replaces this script.

set -euo pipefail

indi_port="${INDI_PORT:-7624}"
web_host="${WEB_HOST:-0.0.0.0}"
web_port="${WEB_PORT:-8000}"
driver_dir="${INDI_DRIVER_DIR:-/drivers}"

shim_root="$(mktemp -d)"

# A .py file becomes an executable shim; anything else is passed through, because it
# is either a name indiserver will find on PATH or a path that is already executable.
resolve_driver() {
    local spec="$1" index="$2"
    if [[ "$spec" != *.py ]]; then
        printf '%s\n' "$spec"
        return
    fi
    # One directory per shim, so two drivers with the same file name in different
    # places cannot overwrite each other while the shim keeps the driver's own name -
    # which is what indiserver prints in its logs.
    local dir="$shim_root/$index"
    mkdir -p "$dir"
    local shim
    shim="$dir/$(basename "$spec" .py)"
    printf '#!/bin/sh\nexec %q %q\n' "$(command -v python3)" "$spec" >"$shim"
    chmod +x "$shim"
    printf '%s\n' "$shim"
}

# Whether a file is something execlp() could actually run.
#
# The obvious test, `test -x`, does not work here: Docker Desktop's file sharing
# reports every bind-mounted file as executable whatever its mode says, so on a Mac
# host a README in the driver directory would be handed to indiserver, which then
# retries it forever. Reading the first bytes means the same thing on every host. The
# mode is still checked as well, because on a Linux host it is honest, and a driver
# that genuinely needs `chmod +x` is better skipped with a reason than restart-looped.
is_program() {
    local magic
    magic="$(head -c 4 -- "$1" | od -An -v -t x1 | tr -d ' \n')"
    case "$magic" in
        7f454c46) return 0 ;; # ELF: a compiled driver
        2321*) return 0 ;;    # #!: a script naming its own interpreter
        *) return 1 ;;
    esac
}

specs=()
if [[ -n "${INDI_DRIVERS:-}" ]]; then
    # Unquoted on purpose: INDI_DRIVERS is a space-separated list.
    # shellcheck disable=SC2206
    specs=(${INDI_DRIVERS})
fi

if [[ -d "$driver_dir" ]]; then
    while IFS= read -r -d '' entry; do
        if [[ "$entry" == *.py ]] || { [[ -x "$entry" ]] && is_program "$entry"; }; then
            specs+=("$entry")
        else
            echo "indi-nexus: ignoring $entry (not a .py driver, not an executable program)" >&2
        fi
    done < <(find "$driver_dir" -mindepth 1 -maxdepth 1 ! -type d -print0 | sort -z)
fi

if [[ ${#specs[@]} -eq 0 ]]; then
    echo "indi-nexus: no drivers to run. Set INDI_DRIVERS, or mount some into $driver_dir." >&2
    exit 1
fi

drivers=()
index=0
for spec in "${specs[@]}"; do
    drivers+=("$(resolve_driver "$spec" "$index")")
    index=$((index + 1))
done

# The container publishes a port, so WEB_HOST is 0.0.0.0 and /ws - the whole write
# surface, where a frame becomes an INDI new* that moves hardware - is reachable by
# anything that can reach the host. So a token is always passed unless the operator
# has said otherwise, and a generated one is printed rather than being a secret
# nobody can use.
web_args=()
if [[ -n "${WEB_TOKEN:-}" ]]; then
    web_args+=(--token "$WEB_TOKEN")
elif [[ -n "${WEB_ALLOW_ANONYMOUS:-}" ]]; then
    web_args+=(--allow-insecure-bind)
else
    WEB_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
    web_args+=(--token "$WEB_TOKEN")
    echo "indi-nexus: generated a web token. Set WEB_TOKEN to keep it stable across restarts."
fi

if [[ -n "${WEB_ALLOWED_ORIGINS:-}" ]]; then
    # Unquoted on purpose: WEB_ALLOWED_ORIGINS is a space-separated list.
    # shellcheck disable=SC2206
    for origin in ${WEB_ALLOWED_ORIGINS}; do
        web_args+=(--allow-origin "$origin")
    done
fi

echo "indi-nexus: indiserver on :$indi_port with ${specs[*]}"
if [[ -n "${WEB_TOKEN:-}" ]]; then
    echo "indi-nexus: panel on http://localhost:$web_port/?token=$WEB_TOKEN"
else
    echo "indi-nexus: panel on http://localhost:$web_port/ (no token: anyone who can reach this port can drive the instrument)"
fi

# -v gives one line per driver event, which is the only account of why a mounted
# driver failed to start.
indiserver -v -p "$indi_port" "${drivers[@]}" &
hub=$!

indi-nexus serve \
    --host "$web_host" --port "$web_port" \
    --indi-host 127.0.0.1 --indi-port "$indi_port" \
    "${web_args[@]}" &
bridge=$!

stop() {
    # A process that has already exited is the normal case here, not a failure: this
    # runs both on shutdown and after one of the two has died on its own.
    local pid
    for pid in "$@"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill -TERM "$pid"
        fi
    done
}

# shellcheck disable=SC2329 # reached through the trap below, not by a direct call
on_signal() {
    trap - TERM INT
    # Shutting down: a terminated child exits non-zero by definition, and that is not
    # a failure of this script.
    set +e
    stop "$hub" "$bridge"
    wait
    exit 0
}
trap on_signal TERM INT

# Either process ending ends the container, so a driver crash or a wedged bridge
# surfaces as an exit code rather than as half a stack that still answers on :8000.
status=0
wait -n || status=$?
set +e
stop "$hub" "$bridge"
wait
exit "$status"
