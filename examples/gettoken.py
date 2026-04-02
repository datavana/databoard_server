#
# Get an access token
# The token is saved in access_token and can be used in other scripts
#

import os
import requests

# Provide the admin username and password
# in the environment variables (so that nobody can see it)
# - Create .env file, see .env.default for a blueprint
# - Install python-dotenv:
#   pip install python-dotenv
import dotenv
dotenv.load_dotenv(".env")

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
    print("✅ Logged in")
else:
    access_token = None
    print(f"{token_resp.status_code} {token_resp.reason}")
