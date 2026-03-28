# 🌾 Hydro Irrigation — Irrigation Water Demand

[![GitHub stars](https://img.shields.io/github/stars/zengtianli/hydro-irrigation)](https://github.com/zengtianli/hydro-irrigation)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.36+-FF4B4B.svg)](https://streamlit.io)
[![Live Demo](https://img.shields.io/badge/Live%20Demo-hydro--irrigation.tianlizeng.cloud-brightgreen)](https://hydro-irrigation.tianlizeng.cloud)

Paddy and dryland irrigation water demand calculator using daily water balance model.

![screenshot](docs/screenshot.png)

## Features

- **Paddy + dryland models** — separate water balance for rice paddies and dry crops
- **Daily time step** — day-by-day irrigation demand with rainfall and evaporation inputs
- **Multi-zone support** — calculate demand across multiple irrigation zones
- **ZIP upload** — batch upload all input TXT files as a single archive
- **Excel export** — download combined results with per-zone breakdowns

## Quick Start

```bash
git clone https://github.com/zengtianli/hydro-irrigation.git
cd hydro-irrigation
pip install -r requirements.txt
streamlit run app.py
```

## Deploy (VPS)

```bash
git clone https://github.com/zengtianli/hydro-irrigation.git
cd hydro-irrigation
pip install -r requirements.txt
nohup streamlit run app.py --server.port 8505 --server.headless true &
```

## Hydro Toolkit Plugin

This project is a plugin for [Hydro Toolkit](https://github.com/zengtianli/hydro-toolkit) and can also run standalone. Install it in the Toolkit by pasting this repo URL in the Plugin Manager. You can also **[try it online](https://hydro-irrigation.tianlizeng.cloud)** — no install needed.

## License

MIT
