"""
dashboard_server.py
Serves live_dashboard.html + API endpoints

/api/status           → simulation data
/api/start            → starts rule_based_tls.py as subprocess (launches SUMO)
/api/stop             → stops the simulation subprocess
/api/reset            → reset stats
/api/spawn_emergency  → write spawn_command.json (picked up by rule_based_tls.py)
"""
import os, sys, json, time, subprocess, signal
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from http.server import HTTPServer, SimpleHTTPRequestHandler
from threading import Thread
from urllib.parse import urlparse, parse_qs

DASHBOARD_FILE = 'dashboard_data.json'
COMMAND_FILE   = 'spawn_command.json'
PYTHON         = sys.executable

# Simulation subprocess handle
sim_proc = None

data = {
    'running': False, 'vehicles': 0, 'avg_wait_time': 0.0,
    'traffic_lights': [], 'junction_status': {}, 'vehicle_list': [],
    'step': 0, 'tl_details': {}, 'spawned_emergency': [], 'logs': [],
}


def add_log(msg, t='info'):
    e = {'time': time.strftime('%H:%M:%S'), 'type': t, 'message': msg}
    data['logs'].insert(0, e)
    if len(data['logs']) > 30:
        data['logs'] = data['logs'][:30]
    print(f"[{e['time']}] {msg}")


def merged_data():
    """Merge in-memory data with dashboard_data.json written by rule_based_tls.py"""
    try:
        with open(DASHBOARD_FILE) as f:
            disk = json.load(f)
        # Prefer disk data (written by TLS controller) but keep server logs merged
        merged = dict(disk)
        # Prepend server-side logs that may not be in the file
        all_logs = data['logs'] + merged.get('logs', [])
        seen = set()
        deduped = []
        for lg in all_logs:
            key = (lg['time'], lg['message'])
            if key not in seen:
                seen.add(key)
                deduped.append(lg)
        merged['logs'] = deduped[:30]
        return merged
    except Exception:
        return dict(data)


def write_spawn_cmd(direction, vtype):
    try:
        with open(COMMAND_FILE, 'w') as f:
            json.dump({
                'action': 'spawn_emergency',
                'direction': direction,
                'vtype': vtype,
                'timestamp': time.time()
            }, f)
        return True
    except Exception:
        return False


def stream_proc(proc, name):
    """Stream subprocess stdout to console."""
    try:
        for line in proc.stdout:
            print(f"[{name}] {line.rstrip()}")
    except Exception:
        pass


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        qs     = parse_qs(parsed.query)

        # Root → login
        if path in ('/', '', '/dashboard'):
            path = '/login.html'

        # Serve static files
        if path.endswith(('.html', '.css', '.json', '.js')):
            fname = path.lstrip('/')
            if os.path.exists(fname):
                with open(fname, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                ctype = ('application/json' if fname.endswith('.json')
                         else 'text/css' if fname.endswith('.css')
                         else 'text/html')
                self.send_header('Content-type', ctype)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(content)
                return
            # File not found → fall through to 404-style empty JSON

        # API endpoints
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        resp = {}
        if path == '/api/status':
            resp = merged_data()

        elif path == '/api/start':
            resp = start_sim()

        elif path == '/api/stop':
            resp = stop_sim()

        elif path == '/api/reset':
            reset_sim()
            resp = {'status': 'reset'}

        elif path == '/api/spawn_emergency':
            direction = qs.get('direction', ['north'])[0]
            vtype     = qs.get('vtype',     ['ambulance'])[0]
            # Check sim is running before spawning
            current = merged_data()
            if not current.get('running', False):
                resp = {'status': 'error', 'message': 'Simulation is not running. Start it first!'}
            elif write_spawn_cmd(direction, vtype):
                add_log(f"[AMBULANCE] Spawn command: {vtype} from {direction}", 'error')
                resp = {'status': 'ok', 'message': f'{vtype} spawning from {direction}'}
            else:
                resp = {'status': 'error', 'message': 'Failed to write spawn command'}
        else:
            resp = {'error': 'Unknown endpoint'}

        self.wfile.write(json.dumps(resp, indent=2).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

    def log_message(self, *a):
        pass  # Suppress per-request logs


def start_sim():
    global sim_proc

    # Already running?
    if sim_proc and sim_proc.poll() is None:
        add_log('Simulation already running', 'warning')
        return {'status': 'already_running', 'message': 'Simulation is already running'}

    cfg = _find_cfg()
    if not cfg:
        msg = 'simple.sumocfg not found in working directory'
        add_log(msg, 'error')
        return {'status': 'error', 'message': msg}

    # Remove stale dashboard_data so old state doesn't linger
    try:
        if os.path.exists(DASHBOARD_FILE):
            os.remove(DASHBOARD_FILE)
    except Exception:
        pass

    cmd = [PYTHON, 'rule_based_tls.py', '--gui', '--config', cfg, '--steps', '3600']
    try:
        sim_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        # Stream output to console in background
        Thread(target=stream_proc, args=(sim_proc, 'TLS'), daemon=True).start()
        # Monitor process to update running state
        Thread(target=_monitor_proc, daemon=True).start()

        add_log(f'[OK] Started: rule_based_tls.py (pid={sim_proc.pid})', 'success')
        return {'status': 'started', 'message': f'SUMO simulation launched (pid={sim_proc.pid})'}
    except Exception as e:
        msg = f'Failed to start simulation: {e}'
        add_log(msg, 'error')
        return {'status': 'error', 'message': msg}


def _monitor_proc():
    """Watch the simulation process; update data when it exits."""
    global sim_proc
    if sim_proc:
        sim_proc.wait()
        add_log('Simulation process ended', 'warning')
        # Update dashboard_data.json running flag
        try:
            with open(DASHBOARD_FILE) as f:
                d = json.load(f)
            d['running'] = False
            with open(DASHBOARD_FILE, 'w') as f:
                json.dump(d, f, indent=2)
        except Exception:
            pass


def stop_sim():
    global sim_proc
    if sim_proc and sim_proc.poll() is None:
        try:
            sim_proc.terminate()
            time.sleep(0.5)
            if sim_proc.poll() is None:
                sim_proc.kill()
        except Exception as e:
            add_log(f'Stop error: {e}', 'error')
        add_log('Simulation stopped by user', 'warning')
    else:
        add_log('No simulation running', 'warning')
    return {'status': 'stopped'}


def reset_sim():
    data.update({
        'vehicles': 0, 'avg_wait_time': 0.0, 'step': 0,
        'vehicle_list': [], 'junction_status': {}, 'tl_details': {},
        'spawned_emergency': []
    })
    # Reset dashboard file too
    try:
        with open(DASHBOARD_FILE, 'w') as f:
            json.dump({'running': False, 'vehicles': 0, 'avg_wait_time': 0.0,
                       'step': 0, 'traffic_lights': [], 'junction_status': {},
                       'vehicle_list': [], 'tl_details': {}, 'spawned_emergency': [],
                       'logs': []}, f, indent=2)
    except Exception:
        pass
    add_log('Stats reset', 'info')


def _find_cfg():
    for fn in os.listdir('.'):
        if fn.endswith('.sumocfg'):
            return fn
    return None


def run_server(port=8080):
    httpd = HTTPServer(('', port), Handler)
    url = f"http://localhost:{port}/login.html"
    print(f"\n{'='*60}")
    print(f"  AI Signal OptiSense — Dashboard Server")
    print(f"{'='*60}")
    print(f"  Open in browser: {url}")
    print(f"  Press Ctrl-C to stop")
    print(f"{'='*60}\n")
    add_log('Dashboard server started', 'success')

    # Try to open browser automatically
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        stop_sim()
        print('\n[Server] Stopped.')


if __name__ == '__main__':
    run_server(8080)