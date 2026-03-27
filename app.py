#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
灌溉需水模型 - Streamlit Web 界面

启动方式：streamlit run app.py
"""
import io
import streamlit as st
import pandas as pd
import sys
import zipfile
import tempfile
from pathlib import Path

# 项目目录
REPO_ROOT = Path(__file__).resolve().parent
DATA_SAMPLE_DIR = REPO_ROOT / 'data' / 'sample'
DATA_OUTPUT_DIR = REPO_ROOT / 'data' / 'output'
sys.path.insert(0, str(REPO_ROOT))

from src.common.st_utils import page_config, excel_download, footer

# ============================================================
# 页面配置
# ============================================================
page_config("灌溉需水 - Hydro Toolkit", "🌾")

# ============================================================
# 工具函数
# ============================================================
def read_txt_file(filepath):
    """读取 txt 文件为 DataFrame"""
    try:
        for sep in ['\t', ',', ' ']:
            try:
                df = pd.read_csv(filepath, sep=sep, encoding='utf-8')
                if len(df.columns) > 1:
                    return df
            except:
                continue
        return pd.read_fwf(filepath, encoding='utf-8')
    except:
        return None

def parse_results_txt(filepath):
    """解析输出结果 txt 文件"""
    try:
        lines = filepath.read_text(encoding='utf-8').strip().split('\n')
        if not lines:
            return None
        
        data = []
        for line in lines:
            parts = line.split()
            if parts:
                data.append(parts)
        
        if len(data) < 2:
            return None
        
        df = pd.DataFrame(data[1:], columns=data[0])
        for col in df.columns[1:]:
            try:
                df[col] = pd.to_numeric(df[col])
            except:
                pass
        return df
    except:
        return None

def create_sample_zip():
    """将示例数据打包成 ZIP"""
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file in DATA_SAMPLE_DIR.glob('*.txt'):
            zf.write(file, file.name)
    
    zip_buffer.seek(0)
    return zip_buffer

def extract_uploaded_zip(uploaded_file):
    """解压上传的 ZIP 文件到临时目录"""
    temp_dir = tempfile.mkdtemp()
    
    with zipfile.ZipFile(uploaded_file, 'r') as zf:
        zf.extractall(temp_dir)
    
    return Path(temp_dir)

# ============================================================
# 标题
# ============================================================
st.title("🌾 灌溉需水")
st.markdown("基于作物需水与水量平衡的灌溉需水量预测系统")
st.markdown("---")

# ============================================================
# 侧边栏
# ============================================================
with st.sidebar:
    st.header("📖 使用说明")
    st.markdown("""
    **步骤：**
    1. 选择数据来源
    2. 预览数据
    3. 选择计算模式
    4. 点击「开始计算」
    5. 查看并下载结果
    
    ---
    
    **计算模式：**
    - **综合模式**：旱地 + 水稻
    - **旱地模式**：仅旱地作物
    - **水稻模式**：仅水稻灌溉
    
    ---
    
    **覆盖区域：**
    
    浙东 15 个平原河区
    - 余姚：上河区、下河区...
    - 慈溪：西河区、中河区...
    """)

# ============================================================
# Step 1: 数据来源
# ============================================================
st.header("📁 Step 1: 数据来源")

data_source = st.radio(
    "选择数据来源",
    options=["sample", "upload"],
    format_func=lambda x: "使用示例数据（直接演示）" if x == "sample" else "上传自己的数据",
    horizontal=True
)

data_path = None
input_files = []

if data_source == "sample":
    # 使用示例数据
    data_path = DATA_SAMPLE_DIR
    if data_path.exists():
        input_files = list(data_path.glob("*.txt"))
        if input_files:
            st.success(f"✅ 示例数据已加载，共 {len(input_files)} 个文件")
        else:
            st.warning("⚠️ 示例数据目录为空")
    else:
        st.error("❌ 示例数据目录不存在")

else:
    # 上传数据
    st.markdown("**上传数据 ZIP 压缩包**")
    
    uploaded_zip = st.file_uploader(
        "选择 ZIP 文件",
        type=["zip"],
        help="请上传包含所有输入 txt 文件的 ZIP 压缩包"
    )
    
    if uploaded_zip:
        try:
            data_path = extract_uploaded_zip(uploaded_zip)
            input_files = list(data_path.glob("*.txt"))
            
            if input_files:
                st.success(f"✅ 已解压 {len(input_files)} 个文件")
                
                # 保存到 session 以便后续使用
                st.session_state['uploaded_data_path'] = str(data_path)
            else:
                st.warning("⚠️ ZIP 中没有 .txt 文件")
        except Exception as e:
            st.error(f"❌ 解压失败：{str(e)}")
    else:
        # 从 session 恢复之前上传的数据
        if 'uploaded_data_path' in st.session_state:
            data_path = Path(st.session_state['uploaded_data_path'])
            if data_path.exists():
                input_files = list(data_path.glob("*.txt"))
        
        st.info("👆 请上传包含输入文件的 ZIP 压缩包")

# 下载示例文件按钮
col1, col2 = st.columns([1, 3])
with col1:
    st.download_button(
        "📥 下载示例文件",
        data=create_sample_zip(),
        file_name="灌溉需水模型_示例数据.zip",
        mime="application/zip",
        help="下载示例数据，了解输入格式"
    )

# 格式要求说明
with st.expander("📋 查看输入格式要求"):
    st.markdown("""
    ### 必需文件
    
    | 文件名 | 说明 |
    |--------|------|
    | `in_TIME.txt` | 预测起始时间和预测天数 |
    | `in_JYGC.txt` | 降雨量数据（各分区逐日） |
    | `in_ZFGC.txt` | 蒸发量数据（各分区逐日） |
    | `static_fenqu.txt` | 灌区分区信息 |
    | `static_single_crop.txt` | 单季稻灌溉制度表 |
    | `static_double_crop.txt` | 双季稻灌溉制度表 |
    
    ### 可选文件
    
    | 文件名 | 说明 |
    |--------|------|
    | `static_crops.txt` | 作物需水参数 |
    | `in_dry_crop_area.txt` | 旱地作物种植面积 |
    
    💡 **提示**：下载示例文件查看具体格式
    """)

# ============================================================
# Step 2: 数据预览
# ============================================================
if data_path and input_files:
    st.header("👁️ Step 2: 数据预览")
    
    preview_files = {
        "分区信息": "static_fenqu.txt",
        "时间配置": "in_TIME.txt",
        "单季稻制度": "static_single_crop.txt",
        "双季稻制度": "static_double_crop.txt",
        "降雨数据": "in_JYGC.txt",
        "蒸发数据": "in_ZFGC.txt",
    }
    
    available_tabs = []
    available_files = []
    
    for label, filename in preview_files.items():
        filepath = data_path / filename
        if filepath.exists():
            available_tabs.append(label)
            available_files.append(filepath)
    
    if available_tabs:
        tabs = st.tabs(available_tabs)
        
        for i, (tab, filepath) in enumerate(zip(tabs, available_files)):
            with tab:
                df = read_txt_file(filepath)
                if df is not None:
                    st.dataframe(df, use_container_width=True, height=250)
                    st.caption(f"共 {len(df)} 行, {len(df.columns)} 列")
                else:
                    content = filepath.read_text(encoding='utf-8')
                    st.code(content[:2000])

# ============================================================
# Step 3: 计算
# ============================================================
if data_path and input_files:
    st.header("🚀 Step 3: 开始计算")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        calc_mode = st.selectbox(
            "计算模式",
            options=["both", "crop", "irrigation"],
            format_func=lambda x: {
                "both": "综合模式（旱地+水稻）",
                "crop": "旱地作物模式",
                "irrigation": "水稻灌溉模式"
            }[x],
            index=0
        )
    
    calc_button = st.button("🚀 开始计算", type="primary", use_container_width=True)
    
    if calc_button:
        results = {}
        
        with st.spinner("计算中..."):
            progress = st.progress(0)
            status = st.empty()
            
            try:
                status.text("📊 加载计算模块...")
                progress.progress(10)
                
                from src.irrigation.calculator import Calculator
                from src.irrigation.utils import combine_results
                import shutil
                
                status.text("📂 初始化计算器...")
                progress.progress(20)
                
                # 准备输出目录
                output_dir = DATA_OUTPUT_DIR
                output_dir.mkdir(parents=True, exist_ok=True)
                
                calculator = Calculator(str(data_path), verbose=False)
                calculator.load_data()
                
                calc_info = {
                    'start_time': str(calculator.current_time),
                    'forecast_days': calculator.forecast_days,
                    'num_areas': len(calculator.irrigation_manager.irrigation_areas),
                    'systems': list(calculator.irrigation_manager.irrigation_systems.keys())
                }
                
                if calc_mode == "crop":
                    status.text("🌾 计算旱地作物需水量...")
                    progress.progress(50)
                    
                    calculator.set_mode("crop", "OUT_GGXS_C.txt", "OUT_PYCS_C.txt")
                    calculator.run_calculation()
                    mode_results = calculator.export_results(return_data=True)
                    
                    results['旱地灌溉需水'] = mode_results.get('irrigation', {})
                    results['旱地排水量'] = mode_results.get('drainage', {})
                    
                elif calc_mode == "irrigation":
                    status.text("🌾 计算水稻灌溉需水量...")
                    progress.progress(50)
                    
                    calculator.set_mode("irrigation", "OUT_GGXS_I.txt", "OUT_PYCS_I.txt")
                    calculator.run_calculation()
                    mode_results = calculator.export_results(return_data=True)
                    
                    results['水稻灌溉需水'] = mode_results.get('irrigation', {})
                    results['水稻排水量'] = mode_results.get('drainage', {})
                    
                else:  # both
                    status.text("🌾 计算旱地作物需水量...")
                    progress.progress(30)
                    
                    calculator.set_mode("crop", "OUT_GGXS_C.txt", "OUT_PYCS_C.txt")
                    calculator.run_calculation()
                    crop_results = calculator.export_results(return_data=True)
                    
                    status.text("🌾 计算水稻灌溉需水量...")
                    progress.progress(50)
                    
                    calculator.set_mode("irrigation", "OUT_GGXS_I.txt", "OUT_PYCS_I.txt")
                    calculator.run_calculation()
                    irrigation_results = calculator.export_results(return_data=True)
                    
                    status.text("📊 合并计算结果...")
                    progress.progress(70)
                    
                    ggxs_total, pycs_total = combine_results(
                        str(data_path),
                        crop_results.get('irrigation', {}),
                        irrigation_results.get('irrigation', {}),
                        crop_results.get('drainage', {}),
                        irrigation_results.get('drainage', {})
                    )
                    
                    results['total_irrigation'] = ggxs_total
                    results['total_drainage'] = pycs_total
                    results['旱地灌溉需水'] = crop_results.get('irrigation', {})
                    results['水稻灌溉需水'] = irrigation_results.get('irrigation', {})
                
                progress.progress(100)
                status.text("✅ 计算完成，整理输出文件...")
                
                # 移动输出文件到 output 目录
                output_patterns = ['OUT_*.txt', 'irrigation_*.txt', 'water_balance_*.txt']
                for pattern in output_patterns:
                    for f in data_path.glob(pattern):
                        dest = output_dir / f.name
                        shutil.move(str(f), str(dest))
                
                # 也检查 data_path 的父目录（有些输出可能在那里）
                parent_dir = data_path.parent
                for pattern in output_patterns:
                    for f in parent_dir.glob(pattern):
                        dest = output_dir / f.name
                        shutil.move(str(f), str(dest))
                
                st.session_state['results'] = results
                st.session_state['calc_info'] = calc_info
                st.session_state['output_path'] = str(output_dir)
                st.session_state['calc_mode'] = calc_mode
                
                st.success("🎉 计算完成！")
                
            except Exception as e:
                st.error(f"❌ 计算出错：{str(e)}")
                import traceback
                st.code(traceback.format_exc())
    
    # ============================================================
    # 显示结果
    # ============================================================
    if 'results' in st.session_state:
        results = st.session_state['results']
        calc_info = st.session_state.get('calc_info', {})
        output_path = st.session_state.get('output_path', str(DATA_OUTPUT_DIR))
        
        st.markdown("### 📊 计算汇总")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if 'total_irrigation' in results:
                st.metric("总灌溉需水量", f"{results['total_irrigation']:.2f}")
        
        with col2:
            if 'total_drainage' in results:
                st.metric("总排水量", f"{results['total_drainage']:.2f}")
        
        with col3:
            st.metric("计算天数", f"{calc_info.get('forecast_days', '-')} 天")
        
        with col4:
            st.metric("河区数量", f"{calc_info.get('num_areas', '-')} 个")
        
        with st.expander("📋 计算详情", expanded=False):
            st.write(f"**起始时间：** {calc_info.get('start_time', '-')}")
            st.write(f"**灌溉系统：** {', '.join(calc_info.get('systems', []))}")
            st.write(f"**输出目录：** {output_path}")
        
        # ============================================================
        # Step 4: 计算结果
        # ============================================================
        st.header("📊 Step 4: 计算结果")
        
        result_path = Path(output_path)
        
        output_files = [
            ("OUT_GGXS_TOTAL.txt", "总灌溉需水量"),
            ("OUT_PYCS_TOTAL.txt", "总排水量"),
            ("OUT_GGXS_C.txt", "旱地灌溉需水"),
            ("OUT_GGXS_I.txt", "水稻灌溉需水"),
            ("OUT_PYCS_C.txt", "旱地排水量"),
            ("OUT_PYCS_I.txt", "水稻排水量"),
        ]
        
        available_results = []
        result_dfs = {}
        
        for filename, label in output_files:
            filepath = result_path / filename
            if filepath.exists():
                df = parse_results_txt(filepath)
                if df is not None:
                    available_results.append(label)
                    result_dfs[label] = df
        
        if available_results:
            result_tabs = st.tabs(available_results)
            
            for i, label in enumerate(available_results):
                with result_tabs[i]:
                    df = result_dfs[label]
                    st.dataframe(df, use_container_width=True, height=350)
                    
                    if len(df.columns) > 1:
                        numeric_cols = df.select_dtypes(include=['float64', 'int64']).columns
                        if len(numeric_cols) > 0:
                            total = df[numeric_cols].sum().sum()
                            st.caption(f"📈 合计: {total:.2f}")
        else:
            st.info("暂无结果文件，请先运行计算")
        
        # ============================================================
        # Step 5: 下载结果
        # ============================================================
        st.header("📥 Step 5: 下载结果")
        
        if result_dfs:
            excel_download(result_dfs, "灌溉需水计算结果.xlsx", type="primary")
            st.caption(f"包含 {len(result_dfs)} 个结果表")

# ============================================================
# 页脚
# ============================================================
footer("灌溉需水", repo_url="https://github.com/zengtianli/hydro-irrigation")
