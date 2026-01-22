# Server socket
bind = "0.0.0.0:8000"
backlog = 2048

# Worker processes
workers = 1    
worker_class = "sync"
timeout = 30
keepalive = 2

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"