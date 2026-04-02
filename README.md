# Databoard Server

The repository contains the server component of the Databoard Service.

## Getting started locally

1. Configure the environment:  
   If you want to work with UniGPT, 
   copy the `.env.default` file to `.env` and 
   provide the URL and access token in this file.

    The server imports the databoard core package.
    Therefore, it is important to follow the databoard folder structure as described in 
    the databoard meta package. The server containers use the parent folder
    as build context and import the databoard_core package from the folder. 
    Alternatively, adjust the Dockerfiles. 

2. Fire up the containers:  
   ```
   docker compose up -d
   ```
   
3. Download models:  
   If you want to use Ollama, install it:
   ```
   docker exec -it db_ollama ollama pull llama3.2
   ```
4. Open http://localhost 


For trouble shooting, see the logs of the containers.

## Optional containers

In addition to the Ollama API, you can start the Ollama Web UI:
```
docker compose up -d --scale webui=1
```

Ollama Web UI:  http://localhost:8282/  
Ollama API: http://localhost:11434/


The repository also contains a Qdrant container:
```
docker compose up -d --scale qdrant=1
```

You will find the Qdrant dashboard on http://localhost:6333/dashboard
Examples for importing data into Qdrant can be found in the databoard_core repository.


## The application

### Components

The databoard frontend is implemented using FastAPI,
see `src/app.py` for the implementation. The frontend

The frontend creates jobs using Celery. 
Worker processes running in a dedicated celery container
are responsible for processing the jobs.
See `src/jobs/worker.py` for the implementation. 

Celery is configured to use the rabbitmq service 
as message broker and the file system (see the data/.jobs folder) as task backend.

### Folder structure

- src: The main application folder for the API and the web interface.
- container: Docker files for the containers of the server app.
- examples: Contains examples how to use the databoard server.
- data: Folder used by the server to store job input, output and other temporary data.
  Make sure to ignore the data in .gitignore. 


- src/jobs: Implementation of the job system.
- src/static: Static assets for the web interface.
- src/templates: Templates for the web interface
- src/users: User management classes.

## User management

You can use the users/add, users/disable and users/delete API endpoints for user management.
Make sure to configure the DATABOARD_SECRET_KEY in the environment variables
as it is used for hashing. See the examples folder how to create user accounts.

User management is simple: All accounts are saved in data/.users/users.json.

```
{
  "root": {
    "username": "root",
    "fullname": "Root User",
    "email": ""
    "usertype": "root",
    "password": "HASHEDPASSWORD",
    "tokenVersion": 1,
    "tokenExpires": true,
    "disabled": false
  }
}
```

# Deployment

The databoard_deploy repository contains the Kubernetes resources
to deploy the databoard service to https://databoard.uni-muenster.de.
