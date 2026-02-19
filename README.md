# JMV-DAS Infrastructure Secure

JMV-DAS is a Qt-based acquisition and visualization application for ExploreX-based DAS systems.

It provides:

* Real-time data acquisition via vendor C API (ctypes wrapper)
* Multi-line block handling
* Waterfall visualization (grayscale)
* Basic acquisition parameter control
* Linux deployment support

---

## 1. Project Structure

```
JMV-DAS/
├── app/                 # Qt GUI application
│   └── main.py
├── backend/             # Hardware interface and acquisition logic
│   ├── acquisition.py
│   ├── pyexplorex.py    # ctypes wrapper for vendor C library
│   └── linux/           # Vendor shared libraries (.so)
├── scripts/             # Deployment helpers
├── requirements.txt
└── README.md
```

---

## 2. Requirements

### OS

Ubuntu 22.04 (recommended)

### Python

Python 3.10+

### System Dependencies (required for Qt)

```bash
sudo apt update
sudo apt install -y \
  python3.10-venv \
  python3-pip \
  libxcb-cursor0 \
  libxcb1 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
  libxcb-randr0 libxcb-render-util0 libxcb-shape0 \
  libxcb-xinerama0 libxkbcommon-x11-0 \
  libxrender1 libxi6 libxext6 libx11-6 \
  libgl1 \
  libtbb12
```

> `libtbb12` is required by the vendor library.

---

## 3. Installation

Clone repository:

```bash
git clone https://github.com/Enlitech/JMV-DAS.git
cd JMV-DAS
```

Create virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 4. Run

```bash
./scripts/run.sh
```

or manually:

```bash
source .venv/bin/activate
python -m app.main
```

---

## 5. Features

### Acquisition

* Uses ExploreX vendor C API (`libexplorex_c.so`)
* Float32 block-based callback
* Multi-line block handling
* Thread-safe queue between C callback and UI thread

### Visualization

* Grayscale waterfall rendering
* Real-time scrolling
* Robust percentile-based scaling
* 30 FPS UI refresh limit

---

## 6. Current Status

✔ Hardware connection validated
✔ Real data acquisition confirmed
✔ Multi-line block reshape implemented
✔ Vendor dependency resolved (`libtbb12`)
✔ Remote deployment via GitHub verified

---

## 7. Notes

* The application currently prioritizes **stability and real-time visualization**.
* Advanced DSP, filtering, and event detection are not yet implemented.
* The GUI parameters must match the device configuration.
* Large block sizes may produce high CPU usage depending on scan rate.

---

## 8. Known Vendor Library Dependencies

Use:

```bash
ldd backend/linux/libexplorex_c.so
```

to verify runtime dependencies.

---

## 9. Development Workflow

### Local Development

```
git add .
git commit -m "message"
git push
```

### Remote Machine

```
git pull
./scripts/run.sh
```

---

## 10. Next Steps (Planned)

* Parameter binding between UI and device
* Data decimation for UI performance optimization
* Log-scale visualization option
* Event detection overlay
* Packaging (AppImage or PyInstaller)

---

© JMV-DAS – Infrastructure Secure Platform