<div align="center">

# 🚦 AI Signal OptiSense

### AI-Based Smart Traffic Signal Control System

Dynamic Traffic Signal Optimization using **Python**, **SUMO**, **TraCI**, **HTML**, **CSS**, and **JavaScript**

![Python](https://img.shields.io/badge/Python-3.10-blue?logo=python)
![SUMO](https://img.shields.io/badge/SUMO-Simulator-green)
![TraCI](https://img.shields.io/badge/TraCI-API-orange)
![HTML](https://img.shields.io/badge/HTML-5-red?logo=html5)
![CSS](https://img.shields.io/badge/CSS-3-blue?logo=css3)
![JavaScript](https://img.shields.io/badge/JavaScript-ES6-yellow?logo=javascript)

</div>

---

# 📌 Overview

AI Signal OptiSense is an intelligent traffic management system that dynamically adjusts traffic signal timings according to real-time traffic density. The system also provides emergency vehicle priority to minimize response time and improve road efficiency.

---

# ✨ Features

- 🚦 Dynamic Traffic Signal Allocation
- 🚑 Emergency Vehicle Priority
- 📊 Real-Time Dashboard
- 📈 Performance Comparison
- 🚗 Live Vehicle Monitoring
- 📉 Traffic Density Analysis
- 🔄 Automatic Signal Optimization
- 📁 JSON Metrics Export

---

# 🛠 Technologies

| Technology | Purpose |
|------------|----------|
| Python | Backend |
| SUMO | Traffic Simulation |
| TraCI | Communication with SUMO |
| HTML/CSS | Dashboard UI |
| JavaScript | Live Dashboard |
| JSON | Metrics Storage |

---

# 🏗 System Architecture

```text
SUMO Simulation
       │
       ▼
Traffic Data Collection
       │
       ▼
Python + TraCI Controller
       │
 ┌───────────────┐
 │ Density Check │
 └───────────────┘
       │
       ▼
Signal Allocation
       │
       ▼
Emergency Priority
       │
       ▼
Dashboard
       │
       ▼
Performance Metrics
```

---

# 🔄 Workflow

```text
Start
 ↓
Load SUMO Network
 ↓
Generate Vehicles
 ↓
Collect Traffic Density
 ↓
Emergency Vehicle Detected?
 ↓
Yes → Priority Green
No → Density Based Timing
 ↓
Update Dashboard
 ↓
Store Metrics
 ↓
End
```

---

# 📸 Project Screenshots

## 🔐 Login Page

![Login](screenshots/login.jpeg)

---

## 📊 Live Dashboard

![Dashboard](screenshots/dashboard.jpeg)

---

## 🚗 SUMO Simulation

![Simulation](screenshots/simulation.jpeg)

---

## 📈 Performance Comparison

![Comparison](screenshots/comparison.jpeg)

---

## 📊 Key Performance Metrics

![Metrics](screenshots/metrics.jpeg)

---

# 📊 Results

| Metric | Rule-Based | Fixed |
|---------|-----------:|------:|
| Average Waiting Time | 3.5 sec | 45.2 sec |
| Throughput | 50.6 | 42.8 |
| Congestion Score | 44 | 74 |

---

# 🚀 Installation

```bash
git clone https://github.com/Saritaparte/AI_Siganal_Optisence.git

cd AI_Siganal_Optisence

pip install -r requirements.txt

python run_system.py
```

---

# 👩‍💻 Author

**Sarita Parte**

GitHub:
https://github.com/Saritaparte

LinkedIn:
https://linkedin.com/in/sarita-parte-711455291

---
