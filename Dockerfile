# syntax=docker/dockerfile:1

# Use the official Python image as the base image
FROM python:3.11

# Set the working directory to /app
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

RUN python -m venv venv && . venv/bin/activate && pip install --upgrade pip && pip install wheel && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Run the main.py script
CMD ["python", "main.py"]
