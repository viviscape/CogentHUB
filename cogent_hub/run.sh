#!/usr/bin/with-contenv bashio
# Entrypoint for the Cogent Hub Connector add-on.
# Options are read by the Python app directly from /data/options.json; this script
# just ensures the s6/bashio environment (incl. SUPERVISOR_TOKEN) is in place and
# surfaces the configured log level to the Home Assistant add-on log.

bashio::log.info "Starting Cogent Hub Connector..."
export LOG_LEVEL="$(bashio::config 'log_level')"

cd /usr/src
exec python3 -m app.main
