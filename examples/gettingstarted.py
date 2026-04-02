#
# Log in, submit a task and retrieve results
#
# This should get you started to develop a script
# for submitting larger jobs. Don't forget to implement
# error handling and a progress bar :)

import time
import json
import requests

#baseurl = "https://databoard.uni-muenster.de"
baseurl = "http://localhost:8000"

#%% Log in

token_resp = requests.post(
    f"{baseurl}/token",
    data={
        "username": "test",
        "password": "tschubid9987",
    }
)

access_token = ""
if token_resp.status_code == 200:
    access_token = token_resp.json()["access_token"]
    print("✅ Logged in")

#%% Submit task

task_resp = requests.post(
    f"{baseurl}/tasks/run",
    json={
        "task": "summarize",
        "input": ["Adele, Rolling in the Deep, 2010"],

        "options": {
            "raw": True,
            "model": "mistral-small",
            "rules": [
                {
                    "category": "pop",
                    "description": "Popular music with catchy melodies and broad appeal"
                },
                {
                    "category": "rock",
                    "description": "Music characterized by strong beats and electric guitars"
                },
                {
                    "category": "classical",
                    "description": "Western art music from the medieval to the modern period"
                },
                {
                    "category": "country",
                    "description": "Music with roots in American folk and western styles"
                },
                {
                    "category": "rb",
                    "description": "Rhythm and Blues featuring soulful vocals and groove-based instrumentation"
                }
            ],
            #"mode": "multi"
        }
    },
    headers={"Authorization": f"Bearer {access_token}"}
)

task_state = "PENDING"
task_id = ""

if task_resp.ok:
    task_result = task_resp.json()

    task_id = task_result['task_id']
    task_state = task_result['state']

    print(f"✅ Submitted task {task_id}")

#%% Poll results

while (task_state == 'PENDING'):
    task_resp = requests.get(
        f"{baseurl}/tasks/run/{task_id}?wait=10",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    task_result = task_resp.json()

    task_id = task_result['task_id']
    task_state = task_result['state']

    if task_state == 'PENDING':
        print(f"⌛ Waiting 10 more seconds")
        time.sleep(10)

print(f"☑️ Task finished with state {task_state}")

#%% Show results

print(json.dumps(task_result, indent=2))

# Optional: print table
#from tabulate import tabulate
#print(tabulate(task_result['result']['answers'], headers="keys", tablefmt="grid"))

