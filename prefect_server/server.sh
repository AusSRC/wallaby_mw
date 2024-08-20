#!/bin/bash
prefect config set PREFECT_API_DATABASE_CONNECTION_URL="postgresql+asyncpg://postgres:gourde-canape-reamer@localhost:5432/prefect"
prefect server start