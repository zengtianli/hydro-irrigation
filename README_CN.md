# 🌾 灌溉需水

[![GitHub stars](https://img.shields.io/github/stars/zengtianli/hydro-irrigation)](https://github.com/zengtianli/hydro-irrigation)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.36+-FF4B4B.svg)](https://streamlit.io)

水稻 + 旱地灌溉需水量计算工具，基于逐日水平衡模型。

![screenshot](docs/screenshot.png)

## 功能特点

- **水稻 + 旱地模型** — 分别计算水田和旱地的水量平衡
- **逐日计算** — 基于降雨和蒸发数据的逐日灌溉需水
- **多分区支持** — 跨多个灌区分区计算
- **ZIP 上传** — 将所有 TXT 输入文件打包上传
- **Excel 导出** — 下载含分区明细的汇总结果

## 快速开始

```bash
git clone https://github.com/zengtianli/hydro-irrigation.git
cd hydro-irrigation
pip install -r requirements.txt
streamlit run app.py
```

## 部署（VPS）

```bash
git clone https://github.com/zengtianli/hydro-irrigation.git
cd hydro-irrigation
pip install -r requirements.txt
nohup streamlit run app.py --server.port 8505 --server.headless true &
```

## Hydro Toolkit 插件

本项目是 [Hydro Toolkit](https://github.com/zengtianli/hydro-toolkit) 的插件，也可独立运行。在 Toolkit 的插件管理页面粘贴本仓库 URL 即可安装。

## 许可证

MIT
