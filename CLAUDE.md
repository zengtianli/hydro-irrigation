# hydro-irrigation — 农业灌溉日水量平衡计算工具

## Quick Reference

| 项目 | 路径/值 |
|------|---------|
| 入口 | `app.py` (Streamlit) |
| 核心计算 | `src/irrigation/main.py` |
| 公共模块 | `src/common/` |
| 样例数据 | `data/sample/` |
| 线上 URL | https://hydro-irrigation.tianlizeng.cloud |
| Streamlit 配置 | `.streamlit/config.toml` |

## 常用命令

```bash
# 本地启动
cd /Users/tianli/Dev/hydro-irrigation
streamlit run app.py

# 依赖安装
pip install -r requirements.txt

# 直接跑核心计算（不走 UI）
python3 src/irrigation/main.py
```

## 项目结构

```
app.py                  # Streamlit 入口，UI 层
src/
  irrigation/           # 水量平衡核心逻辑
    main.py             # 计算入口
  common/               # 公共工具（数据读取、Excel 导出等）
data/
  sample/               # 样例输入文件（ZIP/Excel）
.streamlit/
  config.toml           # 端口、主题配置
```

## 功能说明

| 模块 | 说明 |
|------|------|
| 水稻模型 | 逐日水量平衡，追踪田间蓄水深度 |
| 旱地模型 | 独立土壤水分平衡，适用于非水稻作物 |
| 多分区 | 单次运行处理多个灌区 |
| ZIP 批量 | 多份输入文件打包上传 |
| Excel 导出 | 按分区输出逐日灌溉计划 |

## 部署

无外部 API 依赖，无需凭证。线上版跑在 VPS (`ssh root@104.218.100.67`)，Nginx 反代 + Cloudflare Access。

```bash
# VPS 上重启服务（若为 systemd 管理）
ssh root@104.218.100.67
systemctl restart hydro-irrigation
