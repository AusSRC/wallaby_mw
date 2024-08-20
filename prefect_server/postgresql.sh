#!/bin/bash

docker run -d --name prefect-postgres -v \
    data:/var/lib/postgresql/data \
    -p 5432:5432 \
    -e POSTGRES_USER=postgres \
    -e POSTGRES_PASSWORD=gourde-canape-reamer \
    -e POSTGRES_DB=prefect \
    postgres:latest