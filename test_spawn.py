
"""Quick test - spawn emergency vehicle and check if it appears"""
import traci, time

traci.start(['sumo-gui', '-c', 'simple.sumocfg', '--start', '--quit-on-end'])

print("TLS:", traci.trafficlight.getIDList())
print("Edges:", [e for e in traci.edge.getIDList() if not e.startswith(':')])

# Run 5 steps first
for i in range(5):
    traci.simulationStep()

# Try spawn
try:
    traci.route.add('test_route', ['north', 'south_out'])
    traci.vehicle.add(
        vehID='test_ambulance',
        routeID='test_route',
        typeID='ambulance',
        depart='now',
        departLane='0',
        departPos='0',
        departSpeed='max'
    )
    print("Vehicle added successfully")
except Exception as e:
    print(f"Add failed: {e}")

# Run more steps and check
for i in range(10):
    traci.simulationStep()
    vids = traci.vehicle.getIDList()
    print(f"Step {i}: vehicles={vids}")
    if 'test_ambulance' in vids:
        lane = traci.vehicle.getLaneID('test_ambulance')
        vclass = traci.vehicle.getVehicleClass('test_ambulance')
        print(f"  ambulance lane={lane} class={vclass}")

traci.close()
