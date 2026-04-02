
# Ollama

Getting started and background info:  

- https://github.com/open-webui/open-webui und https://docs.openwebui.com/ 
- https://github.com/ollama/ollama und https://hub.docker.com/r/ollama/ollama


Download model and start chat (small model with 2GB):
```
docker exec -it db_ollama ollama run llama3.2
```

Just download to use it in the web ui or via the API (larger model with 4.7GB) :
```
docker exec -it db_ollama ollama pull llama3
```

Model list: https://ollama.com/library

Notice the note: You should have at least 8 GB of RAM available to run the 7B models, 
16 GB to run the 13B models, and 32 GB to run the 33B models.

That means: Running on a GPU might fail due to isnufficient memory.

Try out the 3B models first.

# Interfaces

- Ollama API: http://localhost:11434/
- Web UI: http://localhost:8282/
- Python: See https://github.com/ollama/ollama-python

# GPU usage

See installation of Nvidia toolkit at https://hub.docker.com/r/ollama/ollama

Then check whether GPUs are accessible:

```
docker run --rm --gpus all nvidia/cuda:12.6.2-cudnn-runtime-ubuntu24.04 nvidia-smi
```

