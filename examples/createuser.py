#
# Create a new databoard user (requires admin permissions on the server)
#

import os
import requests
from tabulate import tabulate

# Provide the admin username and password
# in the environment variables:
# - Create .env file, see .env.default for a blueprint
# - Install python-dotenv:
#   pip install python-dotenv
import dotenv
dotenv.load_dotenv("databoard_server/.env")

#baseurl = "https://databoard.uni-muenster.de"
baseurl = "http://localhost:8000"

#%% Log in
token_resp = requests.post(
    f"{baseurl}/token",
    data={
        "username": os.getenv('DATABOARD_ADMIN_USERNAME'),
        "password": os.getenv('DATABOARD_ADMIN_PASSWORD'),
    }
)

if token_resp.status_code == 200:
    access_token = token_resp.json()["access_token"]
else:
    access_token = None
    print(f"{token_resp.status_code} {token_resp.reason}")

#%% Get user list

headers = {"Authorization": f"Bearer {access_token}"}
user_resp = requests.get(f"{baseurl}/users", headers=headers)

if user_resp.status_code == 200:
    print(tabulate(user_resp.json(), headers="keys", tablefmt="grid"))
else:
    print(f"{user_resp.status_code} {user_resp.reason}")

#%% Create user

headers = {"Authorization": f"Bearer {access_token}"}

new_user = {
    "username": "alice",
    "password": "mypassword",
    "email": "alice@example.com",
    "fullname": "Alice Doe",
    "usertype": "human",
    "tokenExpires": True
}

user_resp = requests.post(f"{baseurl}/users/add", json=new_user, headers=headers)

if user_resp.status_code == 200:
    print("✅ User created:", user_resp.json())
else:
    print("❌ Failed to create user:", user_resp.status_code, user_resp.json())


#%% Delete user

headers = {"Authorization": f"Bearer {access_token}"}

user_resp = requests.delete(f"{baseurl}/users/delete/alice", headers=headers)

if user_resp.status_code == 200:
    print("✅ User deleted:", user_resp.json())
else:
    print("❌ Failed to delete user:", user_resp.status_code, user_resp.json())
