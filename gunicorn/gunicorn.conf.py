import multiprocessing
import os

bind = "0.0.0.0:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 60
keepalive = 5
max_requests = 1000
max_requests_jitter = 50
preload_app = True

# Use stdout/stderr for container logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

proc_name = "medtrack"

pythonpath = "/app"

raw_env = [
    "FLASK_ENV=production",
]

def on_starting(server):
    server.log.info("Starting MedTrack Gunicorn server")

def on_reload(server):
    server.log.info("Reloading MedTrack Gunicorn server")

def worker_int(worker):
    worker.log.info("Worker received INT or QUIT signal")

def pre_fork(server, worker):
    server.log.info(f"Spawning worker {worker.pid}")

def post_fork(server, worker):
    server.log.info(f"Worker {worker.pid} spawned")

def post_worker_init(worker):
    worker.log.info(f"Worker {worker.pid} initialized")

def worker_abort(worker):
    worker.log.info(f"Worker {worker.pid} aborted")

def pre_exec(server):
    server.log.info("Forked child, re-executing")

def when_ready(server):
    server.log.info("Server is ready. Spawning workers")