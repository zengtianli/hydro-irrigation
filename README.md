        # hydro-irrigation

        **English** | [中文](README_CN.md)

        Daily water balance model for agricultural irrigation — separate calculation for paddy and dryland crops.

        [![Live Demo](https://img.shields.io/badge/Live_Demo-hydro--irrigation.tianlizeng.cloud-blue?style=for-the-badge)](https://hydro-irrigation.tianlizeng.cloud)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-yellow?style=for-the-badge)](https://python.org)
        [![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

        ---

        ---

### Try it now — no install needed

**https://hydro-irrigation.tianlizeng.cloud**

---

![hydro-irrigation demo](docs/screenshots/demo.png)

        ---

        ## What can hydro-irrigation do?

        | Feature | Description |
        |---------|-------------|
        | **Paddy water balance** | Day-by-day rice paddy irrigation demand with ponding depth tracking |
| **Dryland crop model** | Separate soil moisture balance for non-paddy crops |
| **Multi-zone support** | Process multiple irrigation zones in a single run |
| **Batch via ZIP** | Upload multiple input files as a single archive |
| **Excel export** | Per-zone results with daily irrigation schedules |

        ## Install

        ```bash
        git clone https://github.com/zengtianli/hydro-irrigation.git
cd hydro-irrigation
pip install -r requirements.txt
        ```

        ## Quick Start

        ```bash
        streamlit run app.py
        ```

        ## Self-host

```bash
git clone https://github.com/zengtianli/hydro-irrigation.git
cd hydro-irrigation
pip install -r requirements.txt
streamlit run app.py
```

Or use the hosted version: **https://hydro-irrigation.tianlizeng.cloud**

## Requirements

        - Python 3.9+
        - Streamlit 1.36+

        ## License

        MIT
