"""
Management command: devserver

Starts the Django development server and a Celery worker together as
managed subprocesses.  Both are terminated cleanly on Ctrl+C.

Usage:
    python manage.py devserver [--addr 127.0.0.1:8000] [--concurrency 2]
"""

import os
import signal
import subprocess
import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Start the Django dev server and Celery worker together."

    def add_arguments(self, parser):
        parser.add_argument(
            "--addr",
            default="127.0.0.1:8000",
            help="Address for the dev server (default: 127.0.0.1:8000)",
        )
        parser.add_argument(
            "--concurrency",
            default=2,
            type=int,
            help="Number of Celery worker processes (default: 2)",
        )

    def handle(self, *args, **options):
        addr = options["addr"]
        concurrency = options["concurrency"]

        python = sys.executable
        manage = [python, "manage.py"]

        procs = []

        def launch(label, cmd):
            self.stdout.write(self.style.SUCCESS(f"Starting {label}: {' '.join(cmd)}"))
            proc = subprocess.Popen(cmd, env=os.environ.copy())
            procs.append((label, proc))
            return proc

        django_proc  = launch("web server", manage + ["runserver", addr])
        celery_proc  = launch(
            "celery worker",
            [python, "-m", "celery", "-A", "web", "worker",
             "--loglevel=info", f"--concurrency={concurrency}"],
        )

        def _shutdown(signum, frame):
            self.stdout.write("\nShutting down...")
            for label, proc in procs:
                if proc.poll() is None:
                    self.stdout.write(f"  stopping {label} (pid {proc.pid})")
                    proc.terminate()
            for label, proc in procs:
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.stdout.write(f"  force-killing {label}")
                    proc.kill()
            sys.exit(0)

        signal.signal(signal.SIGINT,  _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        # Monitor: if either process dies unexpectedly, shut both down.
        while True:
            for label, proc in procs:
                if proc.poll() is not None:
                    self.stderr.write(
                        self.style.ERROR(
                            f"{label} exited unexpectedly (code {proc.returncode}). "
                            "Shutting down."
                        )
                    )
                    _shutdown(None, None)
            signal.pause()
