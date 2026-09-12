#
# To create a user account locally, run the following script.
# Make sure to set a strong password for public facing servers.
#
# It is advised to first stop running databoard containers
# to prevent conflicts with the user file.
# In any case, you need to restart the containers to reload the user file.
#

#%% Imports
import os
import requests
from databoard_server.src.users import users

# Provide the admin username and password
# in the environment variables:
# - Create .env file, see .env.default for a blueprint
# - Install python-dotenv:
#   pip install python-dotenv
import dotenv
dotenv.load_dotenv("databoard_server/.env")
baseurl = "http://localhost:8000"

#%% Add a root user

# Init the user management class pointing to your local
# servers user file location
accounts = users.Accounts(
    "databoard_server/" + os.getenv('DATABOARD_USERFILE')
)

accounts.addUser(
        username = os.getenv('DATABOARD_ADMIN_USERNAME'),
        password = os.getenv('DATABOARD_ADMIN_PASSWORD'),
        usertype="admin",
        tokenExpires=False
)

#%% Test whether login succeeds

token_resp = requests.post(
    f"{baseurl}/token",
    data={
        "username": os.getenv('DATABOARD_ADMIN_USERNAME'),
        "password": os.getenv('DATABOARD_ADMIN_PASSWORD'),
    }
)

if token_resp.status_code == 200:
    access_token = token_resp.json()["access_token"]
    print("Login successful")
else:
    access_token = None
    print(f"{token_resp.status_code} {token_resp.reason}")
