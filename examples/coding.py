#
# Submit jobs to the databoard service
#

import time
import requests

#baseurl = "https://databoard.uni-muenster.de"
baseurl = "http://localhost:8000"

# First, get an access token, see gettoken.py
#access_token = "XXXX"

#%% Define task

taskData = {
  "task": "coding",
  "input": ["How is it going?", "Hello", "Sure!"],

  "options": {
      "rules": [
          {"category":"A","description":"A question", "example":"Why?"},
          {"category":"B","description":"An answer", "example":"Yes!"}
      ],
      "mode": "multi"
  }
}

#%% Submit task
resp = requests.post(
    f"{baseurl}/tasks/run",
    json=taskData,
    headers = {"Authorization": f"Bearer {access_token}"}
)

if resp.ok:
    taskResult = resp.json()
    task_id = taskResult['task_id']
    print(taskResult)
else:
    taskResult = resp.json()
    task_id = None
    print("❌ Failed to submit job:", resp.status_code, taskResult)

#%% Get results

taskState = 'PENDING'
while (taskState == 'PENDING'):
    resp = requests.get(
        f"{baseurl}/tasks/run/{task_id}",
        json=taskData,
        headers={"Authorization": f"Bearer {access_token}"}
    )
    taskResult = resp.json()
    taskState = taskResult['state']
    if taskState == 'PENDING':
        time.sleep(1)

print(taskResult)