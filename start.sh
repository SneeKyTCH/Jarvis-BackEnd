#!/bin/bash
cd jarvis-backend
uvicorn app.main:app --host 0.0.0.0 --port $PORT
