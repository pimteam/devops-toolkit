import subprocess
import requests
import json
import os
import sys
from datetime import datetime, timedelta, timezone

# --- CONFIGURATION ---
LOKI_URL = "http://localhost:3100"

# Read the key from the environment variable
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("Error: The environment variable GEMINI_API_KEY is not set.")
    print("Please set it before running the script: export GEMINI_API_KEY='your_key'")
    sys.exit(1)

GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key= {GEMINI_API_KEY}"
TIME_RANGE_MINUTES = 15

def run_command(command):
    """Executes a system command and returns the result as a string."""
    try:
        result = subprocess.run(
            command, shell=True, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f"Error executing '{command}': {e.stderr}"

def get_system_snapshot():
    """Collects real-time system data."""
    print("1. Collecting real-time system data...")
    snapshot = "--- System Snapshot --- (as of " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + ")\n\n"
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
    """Downloads logs from Loki for the last N minutes."""
    print(f"2. Downloading logs from Loki for the last {TIME_RANGE_MINUTES} minutes...")
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=TIME_RANGE_MINUTES)
    start_nano = int(start_time.timestamp() * 1e9)
    end_nano = int(end_time.timestamp() * 1e9)
    log_query = '{job=~"nginx|php_fpm|mysql"}'
    api_endpoint = f"{LOKI_URL}/loki/api/v1/query_range"
    params = {'query': log_query, 'start': str(start_nano), 'end': str(end_nano), 'limit': 1000, 'direction': 'forward'}

    try:
        response = requests.get(api_endpoint, params=params)
        response.raise_for_status()
        results = response.json()['data']['result']
        all_values = sorted([val for res in results for val in res['values']], key=lambda x: x[0])
        log_entries = [f"[{datetime.fromtimestamp(int(entry[0]) / 1e9).strftime('%Y-%m-%d %H:%M:%S')}] {entry[1]}" for entry in all_values]

        if not log_entries:
            return "--- Logs ---\n\nNo logs found for the selected period."

        return "--- Logs ---\n\n" + "\n".join(log_entries)
    except requests.exceptions.RequestException as e:
        return f"Error connecting to Loki: {e}"
    except (KeyError, IndexError):
        return "Unexpected response format received from Loki."

# +++ NEW FUNCTION FOR AI ANALYSIS +++
def analyze_with_ai(system_data, loki_logs, user_specific):
    """Sends the collected data to an AI model for analysis."""
    print("3. Sending data to AI for analysis... (may take up to 3 minutes)")

    # This is the "magic" - Prompt Engineering!
    prompt = f"""
You are an expert DevOps assistant called "VPS-Doctor". Your task is to analyze system data and logs from a Linux server running a WordPress site (LEMP stack).

Here are the data you need to analyze:

{system_data}

{loki_logs}

--- YOUR TASK ---
Analyze the above data in several steps:
1. **Status Summary:** Write 1-2 sentences about the general state of the server. Is there high load, low memory, or other obvious issues?
2. **Identified Issues:** Review the logs and system data for anomalies, errors, warnings, slow queries, or unusual values. List them. If there are no issues, state it clearly.
3. **Recommendations:** For each identified issue, give a specific, actionable recommendation on what to do. For example: "The PHP error in 'some-plugin' suggests a plugin issue. Try temporarily disabling it." or "The high CPU load comes from process 'X', check what it's doing."
4. **Format the response** with Markdown for better readability.
5. **Ignore the following: requests to /aacn-forum-log/endpoint.php - this is legitimate, we know about it and it's fine.
6. **We already have PHP-FPM slow log, MySQL slow log, and Fail2Ban in place. Skip those obvious recommendations.
7. **We usually request your help when the server is overloaded. Pay special attention to high-load indications and to what might be causing the high load.

{user_specific}
"""

    headers = {'Content-Type': 'application/json'}
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

    try:
        response = requests.post(GEMINI_API_URL, headers=headers, json=data, timeout=180)
        response.raise_for_status()

        # Decode the response from Gemini
        result = response.json()
        analysis = result['candidates'][0]['content']['parts'][0]['text']
        return analysis
    except requests.exceptions.RequestException as e:
        return f"Error connecting to AI API: {e}"
    except (KeyError, IndexError) as e:
        return f"Error: Unexpected response format received from AI. {e}\n\nResponse:\n{response.text}"
# +++++++++++++++++++++++++++++++++++++


# --- FINAL MAIN LOGIC ---
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="VPS-Doctor: AI-powered server diagnostics tool.")
    parser.add_argument(
        '--user',
        type=str,
        default='Rob',
        help="Specify the user for tailored AI responses. 'Bob' for technical/admin, 'Rob' for knowledgeable but not the server admin."
    )
    args = parser.parse_args()

    # Step 1: Collect data
    system_data = get_system_snapshot()

    # Step 2: Download logs
    loki_logs = get_loki_logs()

    user_specific = ""
    if args.user.lower() == 'bob':
        #print(f"User is Bob. Generating a detailed, technical analysis.")
        user_specific = """
--- User Context ---
The user is 'Bob', the server administrator. He is technically proficient.
Provide a detailed, technical, and in-depth analysis. Include specific command examples if relevant. Do not oversimplify the explanations.
"""
    else: # This covers Rob and any other default case
        #print(f"User is Rob. Generating a slightly less technical, high-level analysis.")
        user_specific = """
--- User Context ---
The user is 'Rob', a technically literate site owner but not a server administrator.
Provide a clear, concise, and slightly less technical analysis. Focus on the 'what' and 'why' of the problem and the recommended actions. Avoid overly complex jargon where possible, but keep the core technical details. Make the recommendations easy to understand and follow.
"""

    # Step 3: Send everything for analysis
    ai_analysis = analyze_with_ai(system_data, loki_logs, user_specific)

    # Step 4: Show the result!
    print("\n======================================")
    print("    🩺 V P S - D O C T O R 🩺")
    print("======================================")
    print("\n--- AI Analysis and Recommendations ---\n")
    print(ai_analysis)
