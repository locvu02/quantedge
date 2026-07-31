#!/bin/bash
cd /Users/lovcu/quantedge
source .venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8000 &
sleep 3
ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=60 -R 80:localhost:8000 serveo.net
