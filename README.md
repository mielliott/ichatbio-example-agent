# ichatbio-example-agent

A template for making new iChatBio agents.

## Quickstart

*Requires python 3.10 or higher*

Set up your development environment:

```bash
pip3 install uv
uv sync
source .venv/bin/activate
```

Run the server:

```bash
uvicorn --app-dir src agent:create_app --factory --reload --host "0.0.0.0" --port 9999
```

You can also run the agent server as a Docker container:

```bash
docker compose up --build
```

If everything worked, you should be able to find your agent card at http://localhost:9999/.well-known/agent.json.
