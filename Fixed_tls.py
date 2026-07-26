#!/usr/bin/env python3
"""
fixed_tls.py - Fixed/Static timing traffic light system (Existing System)
Each phase gets a FIXED green time of 30 seconds regardless of traffic density.
This simulates traditional traffic light systems for comparison.
"""
import sys, os, json, time, argparse
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    import traci
except ImportError:
    print("TraCI not found"); sys.exit(1)

FIXED_GREEN    = 30       # Fixed green time - traditional system
YELLOW_TIME    = 3
DASHBOARD_FILE = 'dashboard_data.json'
METRICS_FILE   = 'metrics_fixed.json'

LANES = ['west_0', 'east_0', 'south_0', 'north_0']
PHASE_LANE = {0: 'west_0', 2: 'east_0', 4: 'south_0', 6: 'north_0'}
GREEN_PHASES = [0, 2, 4, 6]

def ts(): return time.strftime('%H:%M:%S')
def log(msg, tag='INFO'): print(f"[{ts()}][{tag}] {msg}")

def find_cfg():
    for fn in os.listdir('.'):
        if fn.endswith('.sumocfg'): return fn
    return None

class FixedRunner:
    def __init__(self, cfg, gui):
        self.cfg  = cfg
        self.gui  = gui
        self.step = 0
        self.phase = 0
        self.timer = 0
        self.n_phases = 8

        # Metrics
        self.metrics = {
            'total_wait_time': 0.0,
            'wait_samples': 0,
            'total_vehicles_completed': 0,
            'wait_time_history': [],
            'throughput_history': [],
            'congestion_history': [],
            'phase_green_counts': {0:0, 2:0, 4:0, 6:0},
        }
        self.data = {
            'running': False, 'vehicles': 0, 'avg_wait_time': 0.0,
            'step': 0, 'traffic_lights': ['J0'], 'junction_status': {},
            'vehicle_list': [], 'tl_details': {}, 'spawned_emergency': [], 'logs': [],
        }

    def log(self, msg, t='info'):
        e = {'time': ts(), 'type': t, 'message': msg}
        self.data['logs'].insert(0, e)
        if len(self.data['logs']) > 30: self.data['logs'] = self.data['logs'][:30]
        log(msg)

    def save(self):
        try:
            with open(DASHBOARD_FILE, 'w') as f: json.dump(self.data, f, indent=2)
        except: pass

    def control_step(self):
        """Fixed timing - no density calculation, just rotate every FIXED_GREEN steps"""
        self.timer += 1
        cur_ph = traci.trafficlight.getPhase('J0')

        if cur_ph % 2 == 0:  # GREEN
            self.metrics['phase_green_counts'][cur_ph] = \
                self.metrics['phase_green_counts'].get(cur_ph, 0) + 1
            if self.timer >= FIXED_GREEN:
                traci.trafficlight.setPhase('J0', cur_ph + 1)
                self.timer = 0
        else:  # YELLOW
            if self.timer >= YELLOW_TIME:
                next_g = GREEN_PHASES[(GREEN_PHASES.index(cur_ph - 1) + 1) % 4]
                traci.trafficlight.setPhase('J0', next_g)
                self.phase = next_g
                self.timer = 0
                log(f"Fixed Phase {next_g} ({PHASE_LANE.get(next_g)}) = {FIXED_GREEN}s (fixed)")

    def collect_metrics(self):
        vids = traci.vehicle.getIDList()
        waits = []
        for vid in vids:
            try: waits.append(traci.vehicle.getWaitingTime(vid))
            except: pass
        if waits:
            avg = sum(waits) / len(waits)
            self.metrics['total_wait_time'] += avg
            self.metrics['wait_samples'] += 1
            self.data['avg_wait_time'] = round(avg, 1)

        try:
            self.metrics['total_vehicles_completed'] += traci.simulation.getArrivedNumber()
        except: pass

        self.data['vehicles'] = len(vids)
        self.data['step'] = self.step

        if self.step % 50 == 0:
            avg_w = round(self.metrics['total_wait_time'] / max(self.metrics['wait_samples'],1), 2)
            cong = min(100, int((len(vids)/250)*100))
            self.metrics['wait_time_history'].append({'step': self.step, 'avg_wait': avg_w})
            self.metrics['throughput_history'].append({'step': self.step, 'vehicles': self.metrics['total_vehicles_completed']})
            self.metrics['congestion_history'].append({'step': self.step, 'score': cong})

        cnt = sum(traci.lane.getLastStepVehicleNumber(l) for l in LANES)
        self.data['junction_status'] = {'J0': {
            'vehicles': cnt,
            'emergency': False,
            'status': 'congested' if cnt>15 else ('active' if cnt>8 else 'clear')
        }}

    def get_final_metrics(self):
        ws = self.metrics['wait_samples']
        avg_wait = round(self.metrics['total_wait_time'] / max(ws,1), 2)
        throughput_rate = round(self.metrics['total_vehicles_completed'] / max(self.step,1) * 100, 2)
        phase_eff = {}
        lanes = {0:'West', 2:'East', 4:'South', 6:'North'}
        total_green_steps = sum(self.metrics['phase_green_counts'].values())
        for ph, lane in lanes.items():
            gc = self.metrics['phase_green_counts'].get(ph, 0)
            phase_eff[lane] = round((gc / max(total_green_steps,1)) * 100, 1)
        cong_hist = self.metrics['congestion_history']
        avg_cong = round(sum(c['score'] for c in cong_hist) / max(len(cong_hist),1), 1)
        return {
            'system_type': 'fixed',
            'avg_wait_time': avg_wait,
            'total_vehicles_completed': self.metrics['total_vehicles_completed'],
            'throughput_per_100_steps': throughput_rate,
            'phase_efficiency': phase_eff,
            'emergency_count': 0,
            'avg_emergency_response_steps': 0,
            'avg_congestion_score': avg_cong,
            'wait_time_history': self.metrics['wait_time_history'],
            'throughput_history': self.metrics['throughput_history'],
            'congestion_history': self.metrics['congestion_history'],
            'total_steps': self.step,
            'timestamp': ts(),
            'fixed_green_time': FIXED_GREEN,
        }

    def run(self, max_steps=3600):
        sumo = 'sumo-gui' if self.gui else 'sumo'
        traci.start([sumo, '-c', self.cfg, '--start', '--quit-on-end', '--delay', '30'])
        self.data['running'] = True
        traci.trafficlight.setPhase('J0', 0)
        self.log(f"Fixed TLS started | Green={FIXED_GREEN}s per phase", 'success')
        self.save()
        try:
            while self.step < max_steps and traci.simulation.getMinExpectedNumber() > 0:
                traci.simulationStep()
                self.step += 1
                self.control_step()
                self.collect_metrics()
                if self.step % 5 == 0: self.save()
                if self.step % 100 == 0:
                    avg_w = round(self.metrics['total_wait_time'] / max(self.metrics['wait_samples'],1), 2)
                    self.log(f"Step {self.step} | Veh:{self.data['vehicles']} | Wait:{avg_w}s")
        except KeyboardInterrupt:
            self.log("Stopped", 'warning')
        except Exception as e:
            self.log(f"Error: {e}", 'error')
            import traceback; traceback.print_exc()
        finally:
            self.data['running'] = False
            self.save()
            try:
                metrics_out = self.get_final_metrics()
                with open(METRICS_FILE, 'w') as f:
                    json.dump(metrics_out, f, indent=2)
                log(f"Fixed metrics saved to {METRICS_FILE}")
            except Exception as me:
                log(f"Metrics save error: {me}")
            try: traci.close()
            except: pass

def main():
    p = argparse.ArgumentParser()
    p.add_argument('-c','--config', default=None)
    p.add_argument('--gui', action='store_true')
    p.add_argument('--steps', type=int, default=3600)
    a = p.parse_args()
    cfg = a.config or find_cfg()
    if not cfg: print("No .sumocfg found"); sys.exit(1)
    print(f"\n[FIXED] Fixed Timing TLS | Config: {cfg} | Green={FIXED_GREEN}s\n")
    FixedRunner(cfg, a.gui).run(a.steps)

if __name__ == '__main__': main()