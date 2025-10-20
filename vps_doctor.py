import subprocess
import requests
import json
from datetime import datetime, timedelta, timezone
import os
import sys

# --- CONFIG ---
LOKI_URL = "http://localhost:3100"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("Error: env variable GEMINI_API_KEY is not set.")
    sys.exit(1)

GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-latest:generateContent?key={GEMINI_API_KEY}"
TIME_RANGE_MINUTES = 15 # How many minutes back to look at the logs

def run_command(command):
    """Execute commands and return string."""
    try:
        # shell=True is necessary for commanda with pipe '|' or wildcard '*', and it's good to be careful
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f"Error executing '{command}': {e.stderr}"

def get_system_snapshot():
    """Collecting system data."""
    print("1. Collecting system data...")
    snapshot = "--- System Snapshot ---\n\n"

    # Use top in "batch mode" (-b) for 1 iteration (-n 1)
    snapshot += "== CPU and Memory Usage (top) ==\n"
    snapshot += run_command("top -b -n 1 | head -n 15") + "\n\n"

    snapshot += "== Memory Usage (free) ==\n"
    snapshot += run_command("free -h") + "\n\n"

    snapshot += "== Disk Usage (df) ==\n"
    snapshot += run_command("df -h") + "\n\n"

    snapshot += "== System Uptime and Load ==\n"
    snapshot += run_command("uptime") + "\n\n"

    return snapshot

def get_loki_logs():
    """Extract logs from Loki for the last N mins."""
    print(f"2. Extract logs from Loki for the last {TIME_RANGE_MINUTES} mins...")

    # Loki expects the time in nano seconds (RFC3339Nano)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=TIME_RANGE_MINUTES)

    # Format the time for Loki
    start_nano = int(start_time.timestamp() * 1e9)
    end_nano = int(end_time.timestamp() * 1e9)

    # This is our log query. `|= ""` wll catch all rows
    log_query = '{job=~"nginx|php_fpm|mysql"}'

    api_endpoint = f"{LOKI_URL}/loki/api/v1/query_range"
    params = {
        'query': log_query,
        'start': str(start_nano),
        'end': str(end_nano),
        'limit': 1000, # Max number of rows
        'direction': 'forward'
    }

    try:
        response = requests.get(api_endpoint, params=params)
        response.raise_for_status()  # Error if the status code is not 2xx
        results = response.json()['data']['result']

        # Make logs readable
        log_entries = []
        # Sort by timestamp
        all_values = sorted([val for res in results for val in res['values']], key=lambda x: x[0])

        for entry in all_values:
            ts = datetime.fromtimestamp(int(entry[0]) / 1e9).strftime('%Y-%m-%d %H:%M:%S')
            log_line = entry[1]
            log_entries.append(f"[{ts}] {log_line}")

        if not log_entries:
            return "No logs for the selected period."

        return "\n".join(log_entries)

    except requests.exceptions.RequestException as e:
        return f"Error connecting to Loki: {e}"
    except (KeyError, IndexError):
        return "Received unexpected responce format from Loki."
# ++++++++++++++++++++++


# --- Main script logic ---
if __name__ == "__main__":
    system_data = get_system_snapshot()

    loki_logs = get_loki_logs()

    print("\n--- Colecting system data ---\n")
    print(system_data)

    print(f"\n--- Logs for the last {TIME_RANGE_MINUTES} minutes ---\n")
    print(loki_logs)
