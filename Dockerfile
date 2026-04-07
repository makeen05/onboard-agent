# Dockerfile
#
# A Dockerfile is a recipe for building a Docker "image" — a snapshot of an
# operating system with your code and dependencies baked in. Docker Compose
# uses this to build the "api" and "worker" containers.
#
# Each line is an instruction: FROM picks the base OS, COPY copies files in,
# RUN executes shell commands during the build, CMD is the default startup command.

FROM python:3.12-slim
# python:3.12-slim = a minimal Linux image with Python 3.12 already installed.
# "slim" means fewer pre-installed packages → smaller image size.

WORKDIR /app
# All subsequent commands run relative to /app inside the container.
# Think of it like "cd /app" that persists.

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Install Python dependencies first (before copying our code).
# Why this order? Docker caches each layer. If requirements.txt hasn't changed,
# Docker skips re-installing packages even when our code changes — much faster rebuilds.

COPY . .
# Copy everything else (our actual code) into /app.

ENV PYTHONPATH=/app
# Tell Python to look for modules starting from /app.
# This means "import api.main" works from anywhere inside the container.
