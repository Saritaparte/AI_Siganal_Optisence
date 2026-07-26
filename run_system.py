#!/usr/bin/env python3
"""
run_system.py
Launches ONLY the dashboard server.
The simulation (rule_based_tls.py + SUMO) is started from the
dashboard's START button — no need to run it separately.

Usage:
  python run_system.py
  python run_system.py --port 8080
"""
import os, sys, time, subprocess, signal, threading, argparse

PYTHON = sys.executable


def stream(proc, name):
    try:
        for line in proc.stdout:
            print(f"[{name}] {line.rstrip()}")
    except Exception:
        pass


def main():
    pa = argparse.ArgumentParser(description='AI Signal OptiSense — System Launcher')
    pa.add_argument('--port', type=int, default=8080, help='Dashboard server port (default: 8080)')
    a = pa.parse_args()

    print('\n' + '='*60)
    print('  AI Signal OptiSense — System Launcher')
    print('='*60)
    print(f'  Starting dashboard server on port {a.port}...')
    print('  The simulation will start when you press START in the dashboard.')
    print('='*60 + '\n')

    server_cmd = [PYTHON, 'dashboard_server.py']

    try:
        proc = subprocess.Popen(
            server_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
    except FileNotFoundError:
        print('[ERROR] dashboard_server.py not found in the current directory.')
        print('        Make sure you run this from the project folder.')
        sys.exit(1)

    print(f'[launcher] Dashboard server started (pid={proc.pid})')

    # Stream server output
    threading.Thread(target=stream, args=(proc, 'server'), daemon=True).start()

    # Give server a moment to start, then open browser
    time.sleep(1.5)
    url = f'http://localhost:{a.port}/login.html'
    print(f'\n[launcher] Opening browser → {url}')
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception as e:
        print(f'[launcher] Could not open browser automatically: {e}')
        print(f'[launcher] Please open manually: {url}')

    print('\n[launcher] Press Ctrl-C to stop the server\n')

    def stop(sig=None, frame=None):
        print('\n[launcher] Shutting down...')
        try:
            proc.terminate()
            time.sleep(0.5)
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT,  stop)
    signal.signal(signal.SIGTERM, stop)

    # Keep alive — watch for server exit
    try:
        while True:
            if proc.poll() is not None:
                print(f'[launcher] Server exited (code={proc.returncode})')
                sys.exit(proc.returncode)
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop()


if __name__ == '__main__':
    main()