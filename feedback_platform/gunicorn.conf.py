import multiprocessing

bind = "0.0.0.0:10000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "gthread"
threads = 4
timeout = 60
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"
forwarded_allow_ips = "*"
secure_scheme_headers = {
    "X-FORWARDED-PROTO": "https",
}

