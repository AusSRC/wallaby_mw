FROM python:3.8-slim
WORKDIR /app

# Install requirements
RUN apt-get update && apt-get -y install procps
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy all files
COPY . /app