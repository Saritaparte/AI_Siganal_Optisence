#!/usr/bin/env python3
"""
rule_based_tls.py
Rule-Based Traffic Light System Controller

tlLogic phases (after adding yellow in net file):
  0: West  GREEN   1: West  YELLOW
  2: East  GREEN   3: East  YELLOW
  4: South GREEN   5: South YELLOW
  6: North GREEN   7: North YELLOW
"""
import sys, os, json, time, argparse
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    import traci
except ImportError:
    print("TraCI not found — install SUMO and set SUMO_HOME"); sys.exit(1)

MIN_GREEN       = 8
MAX_GREEN       = 45
EXPORT_INTERVAL = 5
DASHBOARD_FILE  = 'dashboard_data.json'
METRICS_FILE    = 'metrics_rule_based.json'
COMMAND_FILE    = 'spawn_command.json'

SPAWN_ROUTES = {
    'west' : ('west',  'east_out'),
    'east' : ('east',  'west_out'),
    'north': ('north', 'south_out'),
    'south': ('south', 'north_out'),
}

LANES = ['west_0', 'east_0', 'south_0', 'north_0']

# Green phase index → lane
PHASE_LANE  = {0: 'west_0', 2: 'east_0', 4: 'south_0', 6: 'north_0'}
# Lane → green phase index
LANE_PHASE  = {'west_0': 0, 'east_0': 2, 'south_0': 4, 'north_0': 6}
# Even phase indices = green phases
GREEN_PHASES = [0, 2, 4, 6]

em_counter = 0


def ts():
    return time.strftime('%H:%M:%S')


def log(msg, tag='INFO'):
    print(f"[{ts()}][{tag}] {msg}")


def find_cfg():
    for fn in os.listdir('.'):
        if fn.endswith('.sumocfg'):
            return fn
    return None


def is_emergency(vid):
    try:
        if traci.vehicle.getVehicleClass(vid) == 'emergency':
            return True
    except Exception:
        pass
    return any(k in vid.lower() for k in ('ambulance', 'police', 'firebrigade', 'emergency'))


def spawn_emergency(direction, vtype):
    """
    Spawn an emergency vehicle immediately in SUMO.
    The vehicle is visually distinct: bright red color, larger width highlight,
    max speed, and emergency signal priority mode.
    """
    global em_counter
    em_counter += 1

    if direction not in SPAWN_ROUTES:
        direction = 'north'

    from_e, to_e = SPAWN_ROUTES[direction]
    vid = f'em_{vtype}_{direction}_{em_counter}'
    rid = f'em_route_{em_counter}'

    try:
        # Add route
        traci.route.add(rid, [from_e, to_e])

        # Add vehicle with emergency type
        traci.vehicle.add(
            vehID=vid,
            routeID=rid,
            typeID=vtype,
            depart='now',
            departLane='0',
            departPos='0',
            departSpeed='max'
        )

        # --- Visual distinctiveness ---
        # Bright red color so it stands out immediately in SUMO GUI
        traci.vehicle.setColor(vid, (255, 50, 50, 255))

        # Speed mode: ignore all traffic signals and speed limits (emergency)
        # Bit flags: 0b00111 = ignore speed, junction, red lights
        traci.vehicle.setSpeedMode(vid, 7)

        # Max speed override
        traci.vehicle.setMaxSpeed(vid, 30.0)

        # Lane change mode: aggressive (emergency vehicles can change any lane)
        traci.vehicle.setLaneChangMode(vid, 0b1000000000)

        log(f"Spawned {vid}: {from_e} → {to_e} | Color: RED | Speed: 30 m/s", 'SPAWN')
        return vid

    except Exception as e:
        log(f"Spawn failed for {vid}: {e}", 'SPAWN')
        return ''


def read_command():
    """Read and immediately delete spawn_command.json to avoid re-processing."""
    try:
        if not os.path.exists(COMMAND_FILE):
            return None
        with open(COMMAND_FILE) as f:
            cmd = json.load(f)
        os.remove(COMMAND_FILE)
        return cmd
    except Exception:
        return None


class TLSController:
    def __init__(self, tl_id):
        self.id     = tl_id
        logic       = traci.trafficlight.getCompleteRedYellowGreenDefinition(tl_id)[0]
        self.phases = logic.phases
        self.n      = len(self.phases)

        self.phase   = 0
        self.timer   = 0
        self.green_t = MIN_GREEN
        self.em_on   = False
        self.em_ph   = -1

        self.lane_signal = {l: 'red' for l in LANES}
        self.lane_green  = {l: 0     for l in LANES}
        self.lane_alloc  = {l: 0     for l in LANES}

        traci.trafficlight.setPhase(self.id, 0)
        log(f"TLS {tl_id} ready: {self.n} phases")

    def density_green(self, green_phase):
        gl = PHASE_LANE.get(green_phase)
        if not gl:
            return MIN_GREEN
        gc = traci.lane.getLastStepVehicleNumber(gl)
        tc = sum(traci.lane.getLastStepVehicleNumber(l) for l in LANES)
        if tc == 0:
            return MIN_GREEN
        return max(MIN_GREEN, min(MAX_GREEN, int(MIN_GREEN + (gc / tc) * (MAX_GREEN - MIN_GREEN))))

    def find_emergency(self):
        for vid in traci.vehicle.getIDList():
            if not is_emergency(vid):
                continue
            try:
                lane = traci.vehicle.getLaneID(vid)
                ph = LANE_PHASE.get(lane)
                if ph is not None:
                    return True, ph
                edge = traci.vehicle.getRoadID(vid)
                ph = LANE_PHASE.get(edge + '_0')
                if ph is not None:
                    return True, ph
            except Exception:
                pass
        return False, -1

    def update_lane_display(self):
        try:
            state = traci.trafficlight.getRedYellowGreenState(self.id)
        except Exception:
            return
        for lane in LANES:
            lph = LANE_PHASE.get(lane, -1)
            if lph < 0:
                continue
            char_idx = (lph // 2) * 4
            ch = state[char_idx].upper() if char_idx < len(state) else 'R'
            if ch == 'G':
                self.lane_signal[lane] = 'green'
                self.lane_green[lane] += 1
                self.lane_alloc[lane]  = self.green_t
            elif ch == 'Y':
                self.lane_signal[lane] = 'yellow'
                self.lane_alloc[lane]  = 0
            else:
                self.lane_signal[lane] = 'red'
                self.lane_alloc[lane]  = 0

    def next_green_phase(self):
        idx = GREEN_PHASES.index(self.phase) if self.phase in GREEN_PHASES else 0
        return GREEN_PHASES[(idx + 1) % len(GREEN_PHASES)]

    def step(self):
        em, em_ph = self.find_emergency()

        if em and not self.em_on:
            log(f"EMERGENCY → {PHASE_LANE.get(em_ph)} GREEN", 'EMRG')
            self.em_on = True
            self.em_ph = em_ph
            yellow_ph = self.phase + 1
            if yellow_ph < self.n:
                traci.trafficlight.setPhase(self.id, yellow_ph)
            self.timer = 0
            self.update_lane_display()
            return

        if self.em_on:
            self.timer += 1
            cur_ph = traci.trafficlight.getPhase(self.id)

            if cur_ph % 2 == 1:  # yellow phase
                if self.timer >= 3:
                    traci.trafficlight.setPhase(self.id, self.em_ph)
                    self.phase = self.em_ph
                    self.timer = 0
                    log(f"Emergency GREEN: {PHASE_LANE.get(self.em_ph)}", 'EMRG')
            else:  # emergency green running
                still, _ = self.find_emergency()
                if not still or self.timer >= MAX_GREEN:
                    log("Emergency cleared — resuming normal cycle", 'EMRG')
                    self.em_on = False
                    traci.trafficlight.setPhase(self.id, self.em_ph + 1)
                    self.phase = self.em_ph
                    self.timer = 0

            self.update_lane_display()
            return

        # Normal rule-based control
        self.timer += 1
        cur_ph = traci.trafficlight.getPhase(self.id)

        if cur_ph % 2 == 0:  # GREEN phase
            if self.timer >= self.green_t:
                traci.trafficlight.setPhase(self.id, cur_ph + 1)
                self.timer = 0
        else:  # YELLOW phase
            if self.timer >= 3:
                next_g = self.next_green_phase()
                self.phase   = next_g
                self.green_t = self.density_green(next_g)
                traci.trafficlight.setPhase(self.id, next_g)
                self.timer = 0
                log(f"Phase {next_g} ({PHASE_LANE.get(next_g)}) Green={self.green_t}s")

        self.update_lane_display()

    def dashboard(self):
        cur_ph = traci.trafficlight.getPhase(self.id)
        is_yellow = cur_ph % 2 == 1
        return {
            'tl_id':            self.id,
            'current_phase':    cur_ph,
            'phase_state':      'YELLOW' if is_yellow else ('EMERGENCY_GREEN' if self.em_on else 'GREEN'),
            'green_duration':   self.green_t,
            'emergency_active': self.em_on,
            'lanes': [{
                'lane_id':    l,
                'vehicles':   traci.lane.getLastStepVehicleNumber(l),
                'signal':     self.lane_signal[l],
                'green_time': self.lane_green[l],
                'green_alloc': self.lane_alloc[l],
            } for l in LANES],
        }


class Runner:
    def __init__(self, cfg, gui):
        self.cfg  = cfg
        self.gui  = gui
        self.ctrls = {}
        self.step  = 0
        self.em_spawned = []
        self.data = {
            'running': False, 'vehicles': 0, 'avg_wait_time': 0.0,
            'step': 0, 'traffic_lights': [], 'junction_status': {},
            'vehicle_list': [], 'tl_details': {},
            'spawned_emergency': [], 'logs': [],
        }
        # Performance metrics
        self.metrics = {
            'total_wait_time': 0.0,
            'wait_samples': 0,
            'total_vehicles_completed': 0,
            'phase_green_counts': {0:0, 2:0, 4:0, 6:0},
            'wait_time_history': [],
            'throughput_history': [],
            'congestion_history': [],
            'emergency_events': [],
        }
        self._em_spawn_step = {}

    def log(self, msg, t='info'):
        e = {'time': ts(), 'type': t, 'message': msg}
        self.data['logs'].insert(0, e)
        if len(self.data['logs']) > 30:
            self.data['logs'] = self.data['logs'][:30]
        log(msg)

    def save(self):
        try:
            with open(DASHBOARD_FILE, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception:
            pass

    def collect(self):
        vids = traci.vehicle.getIDList()
        self.data['vehicles'] = len(vids)
        wt, vl = [], []
        for vid in vids[:10]:
            try:
                w = traci.vehicle.getWaitingTime(vid)
                wt.append(w)
                em = is_emergency(vid)
                vl.append({'id': vid, 'wait_time': round(w, 1), 'emergency': em})
            except Exception:
                pass
        self.data['avg_wait_time'] = round(sum(wt) / len(wt), 1) if wt else 0.0
        self.data['vehicle_list']  = vl

        js = {}
        for tid, ctrl in self.ctrls.items():
            cnt = sum(traci.lane.getLastStepVehicleNumber(l) for l in LANES)
            js[tid] = {
                'vehicles': cnt,
                'emergency': ctrl.em_on,
                'status': 'congested' if cnt > 15 else ('active' if cnt > 8 else 'clear')
            }
        self.data['junction_status'] = js
        self.data['tl_details'] = {tid: c.dashboard() for tid, c in self.ctrls.items()}
        active = set(traci.vehicle.getIDList())
        self.em_spawned = [v for v in self.em_spawned if v in active]
        self.data['spawned_emergency'] = self.em_spawned
        self._update_metrics()

    def _update_metrics(self):
        vids = traci.vehicle.getIDList()
        waits = []
        for vid in vids:
            try: waits.append(traci.vehicle.getWaitingTime(vid))
            except: pass
        if waits:
            self.metrics['total_wait_time'] += sum(waits)/len(waits)
            self.metrics['wait_samples'] += 1
        try:
            self.metrics['total_vehicles_completed'] += traci.simulation.getArrivedNumber()
        except: pass
        # Record history every 50 steps
        if self.step % 50 == 0:
            avg_w = round(self.metrics['total_wait_time'] / max(self.metrics['wait_samples'],1), 2)
            cong  = min(100, int((len(vids)/250)*100))
            self.metrics['wait_time_history'].append({'step': self.step, 'avg_wait': avg_w})
            self.metrics['throughput_history'].append({'step': self.step, 'vehicles': self.metrics['total_vehicles_completed']})
            self.metrics['congestion_history'].append({'step': self.step, 'score': cong})
        # Phase counts
        for tid, ctrl in self.ctrls.items():
            try:
                ph = traci.trafficlight.getPhase(tid)
                if ph in self.metrics['phase_green_counts'] and ph % 2 == 0:
                    self.metrics['phase_green_counts'][ph] += 1
            except: pass
        # Emergency tracking
        for vid in vids:
            if is_emergency(vid) and vid not in self._em_spawn_step:
                self._em_spawn_step[vid] = self.step
        for vid in list(self._em_spawn_step.keys()):
            if vid not in set(vids):
                spawn_s = self._em_spawn_step.pop(vid)
                self.metrics['emergency_events'].append({
                    'vehicle': vid,
                    'spawn_step': spawn_s,
                    'clear_step': self.step,
                    'response_steps': self.step - spawn_s
                })

    def get_final_metrics(self):
        ws = self.metrics['wait_samples']
        avg_wait = round(self.metrics['total_wait_time'] / max(ws,1), 2)
        throughput_rate = round(self.metrics['total_vehicles_completed'] / max(self.step,1) * 100, 2)
        lanes = {0:'West', 2:'East', 4:'South', 6:'North'}
        total_g = sum(self.metrics['phase_green_counts'].values())
        phase_eff = {lane: round(self.metrics['phase_green_counts'].get(ph,0)/max(total_g,1)*100,1) for ph,lane in lanes.items()}
        em_events = self.metrics['emergency_events']
        avg_em = round(sum(e['response_steps'] for e in em_events)/len(em_events),1) if em_events else 0
        cong_h = self.metrics['congestion_history']
        avg_cong = round(sum(c['score'] for c in cong_h)/max(len(cong_h),1),1)
        return {
            'system_type': 'rule_based',
            'avg_wait_time': avg_wait,
            'total_vehicles_completed': self.metrics['total_vehicles_completed'],
            'throughput_per_100_steps': throughput_rate,
            'phase_efficiency': phase_eff,
            'emergency_count': len(em_events),
            'avg_emergency_response_steps': avg_em,
            'avg_congestion_score': avg_cong,
            'wait_time_history': self.metrics['wait_time_history'],
            'throughput_history': self.metrics['throughput_history'],
            'congestion_history': self.metrics['congestion_history'],
            'total_steps': self.step,
            'timestamp': ts(),
        }

    def handle_cmd(self):
        """Check for spawn command written by dashboard_server.py and execute immediately."""
        cmd = read_command()
        if not cmd:
            return
        if cmd.get('action') == 'spawn_emergency':
            direction = cmd.get('direction', 'north')
            vtype     = cmd.get('vtype', 'ambulance')
            vid = spawn_emergency(direction, vtype)
            if vid:
                self.em_spawned.append(vid)
                self.log(f"[AMBULANCE] {vtype} from {direction} → priority GREEN", 'error')
            else:
                self.log(f"[FAIL] Spawn failed for {vtype} from {direction}", 'error')

    def apply_emergency_visuals(self):
        """
        Every step: keep emergency vehicles visually distinct.
        Flash red↔white every 2 steps so they are unmissable in SUMO GUI.
        """
        for v in list(traci.vehicle.getIDList()):
            try:
                if is_emergency(v):
                    # Flash: red on even steps, bright white on odd steps
                    if self.step % 4 < 2:
                        traci.vehicle.setColor(v, (255, 30, 30, 255))   # bright red
                    else:
                        traci.vehicle.setColor(v, (255, 255, 255, 255)) # white flash
                    # Ensure speed priority is always applied
                    traci.vehicle.setSpeedMode(v, 7)
                    traci.vehicle.setMaxSpeed(v, 30.0)
            except Exception:
                pass

    def run(self, max_steps=3600):
        sumo = 'sumo-gui' if self.gui else 'sumo'
        traci.start([sumo, '-c', self.cfg, '--start', '--quit-on-end', '--delay', '30'])

        tls = traci.trafficlight.getIDList()
        self.data['traffic_lights'] = list(tls)
        self.data['running']        = True

        for tid in tls:
            self.ctrls[tid] = TLSController(tid)

        self.log(f"[OK] Started: {len(tls)} TLS", 'success')
        self.save()

        try:
            while self.step < max_steps and traci.simulation.getMinExpectedNumber() > 0:
                # 1. Handle spawn commands from dashboard FIRST (immediate response)
                self.handle_cmd()

                # 2. Advance simulation one step
                traci.simulationStep()
                self.step += 1
                self.data['step'] = self.step

                # 3. Apply emergency vehicle visuals (flashing red/white)
                self.apply_emergency_visuals()

                # 4. Run TLS controllers
                for c in self.ctrls.values():
                    c.step()

                # 5. Collect data for dashboard
                self.collect()

                # 6. Export to JSON every N steps
                if self.step % EXPORT_INTERVAL == 0:
                    self.save()

                # 7. Periodic log
                if self.step % 100 == 0:
                    self.log(
                        f"Step {self.step} | Veh:{self.data['vehicles']} | Wait:{self.data['avg_wait_time']}s"
                    )

        except KeyboardInterrupt:
            self.log("Stopped by user", 'warning')
        except Exception as e:
            self.log(f"Runtime error: {e}", 'error')
            import traceback; traceback.print_exc()
        finally:
            self.data['running'] = False
            self.save()
            # Save performance metrics
            try:
                metrics_out = self.get_final_metrics()
                with open(METRICS_FILE, 'w') as f:
                    json.dump(metrics_out, f, indent=2)
                log(f"Metrics saved → {METRICS_FILE}", "INFO")
            except Exception as me:
                log(f"Metrics save error: {me}", "ERROR")
            try:
                traci.close()
            except Exception:
                pass


def main():
    p = argparse.ArgumentParser(description='Rule-Based TLS Controller')
    p.add_argument('-c', '--config', default=None, help='.sumocfg file path')
    p.add_argument('--gui',   action='store_true', help='Run SUMO with GUI')
    p.add_argument('--steps', type=int, default=3600, help='Max simulation steps')
    a = p.parse_args()

    cfg = a.config or find_cfg()
    if not cfg:
        print("No .sumocfg file found in current directory")
        sys.exit(1)

    print(f"\n[TLS] Rule-Based TLS Controller | Config: {cfg} | GUI: {a.gui}\n")
    Runner(cfg, a.gui).run(a.steps)


if __name__ == '__main__':
    main()