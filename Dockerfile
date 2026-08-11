FROM python:3.12-slim
WORKDIR /app

# Install requirements
RUN apt-get update && apt-get -y install procps
COPY pyproject.toml .
RUN pip install --upgrade pip
RUN pip install .
