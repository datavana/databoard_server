Data folder for the server. 

- .cache: Stores results of LLM calls to avoid unnecessary calls during development. You can safely delete the cache, it will be recreated when needed.
- .jobs: The server creates a subfolder for each job in this folder. The input and output of the jobs are stored in these folders. You can safely delete the job folders, but make sure to stop the server before doing so.
- .users: The user management system stores the user data in this folder. Don't touch!
- .logs: The server logs are stored in this folder. You can safely delete the logs, but make sure to stop the server before doing so.
