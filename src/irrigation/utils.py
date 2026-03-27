"""
水文模拟工具包 - 合并了所有工具函数和类
包含：文件IO、时间处理、数据处理、导出工具、结果管理
"""

import os
import sys
import pandas as pd
from datetime import datetime
from typing import List, Dict, Tuple, Any, Callable

# ============================================================================
# 文件IO工具
# ============================================================================

def read_data_file(file_path: str, debug: bool = False) -> List[str]:
    """
    读取数据文件内容，返回非空行列表
    
    参数:
        file_path: 文件路径
        debug: 是否输出详细调试信息
        
    返回:
        文件非空行列表
    """
    search_paths = []
    
    # 记录原始路径请求
    if debug:
        print(f"请求读取文件: {file_path}")
    
    # 获取文件名（无路径部分）
    base_name = os.path.basename(file_path)
    
    # 构建搜索路径优先级
    
    # 1. 当前工作目录下的同名文件（优先级最高）
    cwd_path = os.path.join(os.getcwd(), base_name)
    search_paths.append(cwd_path)
    
    # 2. 当前工作目录下的data子目录
    data_path = os.path.join(os.getcwd(), 'data', base_name)
    search_paths.append(data_path)
    
    # 3. 相对路径（如果提供）
    if os.path.dirname(file_path):
        rel_path = os.path.join(os.getcwd(), file_path)
        search_paths.append(rel_path)
    
    # 4. 父目录中的静态文件
    parent_static_path = os.path.join(os.getcwd(), '..', base_name)
    if os.path.exists(parent_static_path):
        search_paths.append(parent_static_path)
    
    # 5. 绝对路径（如果提供）
    if os.path.isabs(file_path):
        search_paths.append(file_path)
    
    # 6. 尝试使用脚本目录
    try:
        script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        script_path = os.path.join(script_dir, base_name)
        search_paths.append(script_path)
        
        # 同时检查脚本所在目录的data子目录
        script_data_path = os.path.join(script_dir, 'data', base_name)
        search_paths.append(script_data_path)
    except Exception as e:
        if debug:
            print(f"获取脚本目录失败: {str(e)}")
    
    # 移除重复路径
    search_paths = list(dict.fromkeys(search_paths))
    
    if debug:
        print(f"搜索文件 '{base_name}' 的路径:")
        for i, path in enumerate(search_paths, 1):
            print(f"  {i}. {path}")
    
    # 尝试所有可能的路径
    for path in search_paths:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='UTF-8') as f:
                    lines = [line.strip() for line in f if line.strip()]
                    if debug:
                        print(f"成功读取文件: {path}")
                        print(f"  - 读取了 {len(lines)} 行")
                        if lines and len(lines) > 0:
                            print(f"  - 首行内容: {lines[0][:50]}{'...' if len(lines[0]) > 50 else ''}")
                    return lines
            except Exception as e:
                if debug:
                    print(f"尝试读取 '{path}' 时出错: {str(e)}")
                continue
    
    # 如果所有路径都失败，打印详细错误信息
    error_msg = f"错误: 无法找到文件 '{base_name}'"
    print(error_msg)
    print(f"当前工作目录: {os.getcwd()}")
    print("尝试了以下路径:")
    for path in search_paths:
        print(f"  - {path}")
    
    # 对常见的配置文件，给出特别提示
    special_files = {
        'in_TIME.txt': '时间配置文件',
        'static_fenqu.txt': '分区数据文件',
        'static_crops.txt': '作物数据文件',
        'static_single_crop.txt': '单季稻灌溉制度文件',
        'static_double_crop.txt': '双季稻灌溉制度文件'
    }
    
    if base_name in special_files:
        print(f"\n提示: {base_name} 是 {special_files[base_name]}，对程序运行至关重要。")
        print(f"请确保此文件存在于工作目录或data子目录中。")
    
    sys.exit(1)

def ensure_directory(directory_path: str) -> None:
    """
    确保目录存在，如不存在则创建
    
    参数:
        directory_path: 目录路径
    """
    os.makedirs(directory_path, exist_ok=True)

def write_table_to_file(file_path: str, headers: List[str], data_rows: List[dict]) -> None:
    """
    将表格数据写入文件
    
    参数:
        file_path: 输出文件路径
        headers: 表头列表
        data_rows: 数据行列表，每行是一个字典
    """
    # 如果不是绝对路径，使用当前工作目录
    if not os.path.isabs(file_path):
        file_path = os.path.join(os.getcwd(), file_path)
    
    # 确保输出目录存在
    output_dir = os.path.dirname(file_path)
    if output_dir:
        ensure_directory(output_dir)
        
    with open(file_path, 'w', encoding='UTF-8') as f:
        # 写入表头
        header_line = '\t'.join(headers)
        f.write(header_line + '\n')
        
        # 写入数据行
        for row in data_rows:
            values = [str(row.get(header, '')) for header in headers]
            f.write('\t'.join(values) + '\n')


# ============================================================================
# 时间处理工具
# ============================================================================

def load_time_config(file_path: str, debug: bool = False) -> Tuple[datetime, int]:
    """
    加载时间配置
    
    参数:
        file_path: 时间配置文件路径
        debug: 是否输出详细调试信息
        
    返回:
        (当前时间, 预测天数)
    """
    # 使用debug参数读取文件
    lines = read_data_file(file_path, debug=debug)
    
    if debug:
        print(f"读取时间配置文件，共 {len(lines)} 行")
        for i, line in enumerate(lines):
            print(f"行 {i+1}: {line}")
    
    try:
        # 解析起始时间行
        time_parts = lines[0].split('\t')
        if len(time_parts) < 2:
            raise ValueError(f"时间配置格式错误: {lines[0]}")
        
        current_time = pd.to_datetime(time_parts[1])
        
        # 解析预测天数行
        days_parts = lines[1].split('\t')
        if len(days_parts) < 2:
            raise ValueError(f"预测天数配置格式错误: {lines[1]}")
        
        forecast_days = int(days_parts[1])
        
        if debug:
            print(f"解析结果: 起始时间={current_time}, 预测天数={forecast_days}")
        
        return current_time, forecast_days
    
    except Exception as e:
        print(f"解析时间配置文件失败: {str(e)}")
        print("时间配置文件应该包含两行，格式示例:")
        print("ForcastDate\t2025/07/15")
        print("ForcastDays\t16")
        raise

def create_date_range(start_time: datetime, days: int) -> pd.DatetimeIndex:
    """
    创建日期范围
    
    参数:
        start_time: 起始日期
        days: 天数
        
    返回:
        日期范围
    """
    end_time = pd.Timestamp(start_time) + pd.Timedelta(days=days-1)
    return pd.date_range(start_time, end_time, freq='D')

def handle_leap_year(current_time: datetime) -> datetime:
    """
    处理闰年2月29日的特殊情况
    
    参数:
        current_time: 当前时间
        
    返回:
        处理后的时间
    """
    if current_time.month == 2 and current_time.day == 29:
        return current_time.replace(day=28)
    return current_time


# ============================================================================
# 数据处理工具
# ============================================================================

def parse_table_data(lines: List[str], value_columns: bool = True) -> Dict[str, Any]:
    """
    解析表格数据
    
    参数:
        lines: 文件行列表
        value_columns: 是否将值列转为浮点数
        
    返回:
        解析后的表格数据字典
    """
    if not lines:
        return {}
        
    # 解析表头
    headers = lines[0].split('\t')
    
    # 解析数据行
    data = {}
    for line in lines[1:]:
        values = line.split('\t')
        if len(values) < 2:
            continue
            
        row_key = values[0]
        data[row_key] = {}
        
        for i, header in enumerate(headers):
            if i < len(values):
                if i > 0 and value_columns and values[i].strip():
                    try:
                        data[row_key][header] = float(values[i])
                    except ValueError:
                        data[row_key][header] = values[i]
                else:
                    data[row_key][header] = values[i]
    
    return data

def load_weather_data(file_path: str, area_names: List[str]) -> Dict[str, pd.Series]:
    """
    加载气象数据
    
    参数:
        file_path: 气象数据文件路径
        area_names: 需要加载的区域列表
        
    返回:
        区域名到气象数据时间序列的映射
    """
    lines = read_data_file(file_path)
    file_headers = lines[0].split('\t')
    
    # 获取每个区域在文件中的列索引
    area_indices = {
        file_headers[i + 1]: i + 1 
        for i in range(len(file_headers) - 1)
    }
    
    dates = []
    area_data = {name: [] for name in area_names}
    
    # 解析每一行数据
    for line in lines[1:]:
        values = line.split('\t')
        dates.append(values[0])
        for name in area_names:
            if name in area_indices:
                area_data[name].append(float(values[area_indices[name]]))
    
    # 创建时间索引
    time_index = pd.DatetimeIndex(dates)
    
    # 构建结果
    return {
        name: pd.Series(area_data[name], index=time_index)
        for name in area_names if name in area_data
    }

def merge_datasets(data1: Dict, data2: Dict) -> Tuple[Dict, List]:
    """
    合并两个数据集
    
    参数:
        data1: 第一个数据集
        data2: 第二个数据集
        
    返回:
        (合并后的数据集, 合并后的表头)
    """
    merged = {}
    headers = None
    
    for data in [data1, data2]:
        for key, row in data.items():
            if headers is None:
                headers = list(row.keys())
                
            if key not in merged:
                merged[key] = row.copy()
            else:
                for col_key, value in row.items():
                    if col_key != '日期':
                        merged[key][col_key] = merged[key].get(col_key, 0.0) + value
                        
    return merged, headers


# ============================================================================
# 结果导出工具
# ============================================================================

def export_results(
        data_path: str,
        filename: str,
        headers: List[str],
        data_getter: Callable[[str, datetime], float],
        current_time: datetime,
        forecast_days: int,
        return_data: bool = False,
        include_warmup_days: bool = False
    ) -> Dict:
    """
    导出计算结果
    
    参数:
        data_path: 数据路径
        filename: 输出文件名
        headers: 区域列表
        data_getter: 获取数据的回调函数
        current_time: 当前时间
        forecast_days: 预测天数
        return_data: 是否返回数据
        include_warmup_days: 是否包含预热期数据
        
    返回:
        计算结果数据
    """
    # 使用重构后的配置模块
    from .config import OUTPUT_DIR, get_warmup_days
    
    data = {}
    warmup = get_warmup_days()
    
    # 如果包含预热期数据，则从预热期开始计算
    if include_warmup_days and warmup > 0:
        start_time = pd.Timestamp(current_time) - pd.Timedelta(days=warmup)
        total_days = warmup + forecast_days
    else:
        start_time = pd.Timestamp(current_time)
        total_days = forecast_days
    
    # 生成时间序列
    time_range = pd.date_range(start=start_time, periods=total_days, freq='D')
    
    # 计算每一天的数据
    for current in time_range:
        date = current.strftime('%Y/%m/%d')
        data[date] = {'日期': date}
        
        # 获取每个区域的数据
        for header in headers:
            data[date][header] = data_getter(header, current)
    
    # 是否需要保存到文件
    if not return_data:
        # 始终使用当前工作目录下的data目录
        output_dir = os.path.join(os.getcwd(), OUTPUT_DIR)
        ensure_directory(output_dir)
        
        # 保存到data目录
        file_path = os.path.join(output_dir, filename)
        with open(file_path, 'w', encoding='UTF-8') as f:
            # 写入表头
            header_line = '日期' + ''.join(f'\t{header}' for header in headers)
            f.write(header_line + '\n')
            
            # 写入数据行
            for date in sorted(data.keys()):
                row = date
                for header in headers:
                    row += f'\t{data[date][header]:.2f}'
                f.write(f'{row}\n')
    
    return data


# ============================================================================
# 结果管理工具
# ============================================================================

def combine_results(
        data_path: str, 
        ggxs_crop, 
        ggxs_irr, 
        pycs_crop, 
        pycs_irr
    ) -> Tuple[float, float]:
    """
    合并作物需水和灌溉系统的结果
    
    参数:
        data_path: 数据路径
        ggxs_crop: 作物灌溉数据
        ggxs_irr: 灌溉系统灌溉数据
        pycs_crop: 作物排水数据
        pycs_irr: 灌溉系统排水数据
        
    返回:
        (总灌溉量, 总排水量)
    """
    # 使用重构后的配置模块
    from .config import OUTPUT_DIR, TOTAL_OUTPUT_FILES
    
    # 确保输出目录存在 - 使用当前工作目录
    output_dir = os.path.join(os.getcwd(), OUTPUT_DIR)
    ensure_directory(output_dir)
    
    def read_file_data(file_param):
        """读取文件数据或直接使用已有数据"""
        if isinstance(file_param, dict):
            return file_param
            
        # 优先检查当前工作目录下的data子目录
        data_subdir_path = os.path.join(os.getcwd(), OUTPUT_DIR, os.path.basename(file_param))
        if os.path.exists(data_subdir_path):
            # 如果data子目录中存在该文件，优先使用它
            full_path = data_subdir_path
            print(f"优先使用data目录文件: {data_subdir_path}")
        else:
            # 尝试使用当前工作目录
            cwd_path = os.path.join(os.getcwd(), os.path.basename(file_param))
            if os.path.exists(cwd_path):
                full_path = cwd_path
                print(f"使用当前目录文件: {cwd_path}")
            else:
                # 最后尝试原有路径
                full_path = os.path.join(os.getcwd(), file_param)
                print(f"尝试使用路径: {full_path}")
        
        data = {}
        
        try:
            with open(full_path, 'r', encoding='UTF-8') as f:
                lines = [line.strip() for line in f if line.strip()]
                
            if not lines:
                return data
                
            headers = lines[0].split('\t')
            
            for line in lines[1:]:
                values = line.split('\t')
                if len(values) < 2:
                    continue
                    
                date = values[0]
                data[date] = {
                    headers[i]: float(values[i]) if i > 0 and values[i].strip() else 0.0 
                    for i in range(len(headers))
                }
        except Exception as e:
            print(f"读取文件 {full_path} 时出错: {str(e)}")
            return {}
            
        return data
    
    # 读取数据
    ggxs_crop_data = read_file_data(ggxs_crop)
    ggxs_irr_data = read_file_data(ggxs_irr)
    pycs_crop_data = read_file_data(pycs_crop)
    pycs_irr_data = read_file_data(pycs_irr)
    
    # 合并灌溉和排水数据
    merged_ggxs, ggxs_headers = merge_datasets(ggxs_crop_data, ggxs_irr_data)
    merged_pycs, pycs_headers = merge_datasets(pycs_crop_data, pycs_irr_data)
    
    def write_total(merged: Dict, headers: List, output_file: str) -> float:
        """写入合并后的总量数据"""
        # 始终使用当前工作目录下的data目录
        output_dir = os.path.join(os.getcwd(), OUTPUT_DIR)
        ensure_directory(output_dir)
        
        # 保存到data目录
        file_path = os.path.join(output_dir, output_file)
        try:
            with open(file_path, 'w', encoding='UTF-8') as f:
                # 写入表头
                f.write('\t'.join(headers) + '\n')
                
                # 写入每一天的数据
                for date in sorted(merged.keys()):
                    row = [date] + [
                        f'{merged[date][h]:.2f}' 
                        for h in headers[1:]
                    ]
                    f.write('\t'.join(row) + '\n')
        except Exception as e:
            print(f"写入文件 {file_path} 时出错: {str(e)}")
            
        # 计算总量
        total = sum(
            sum(row[h] for h in headers[1:]) 
            for row in merged.values()
        )
        return total
    
    # 写入并计算总量
    ggxs_total = write_total(merged_ggxs, ggxs_headers, TOTAL_OUTPUT_FILES['irrigation'])
    pycs_total = write_total(merged_pycs, pycs_headers, TOTAL_OUTPUT_FILES['drainage'])
    
    return ggxs_total, pycs_total


# ============================================================================
# 导出接口（保持兼容性）
# ============================================================================

__all__ = [
    # 文件IO相关
    'read_data_file', 'ensure_directory', 'write_table_to_file',
    
    # 时间相关
    'load_time_config', 'create_date_range', 'handle_leap_year',
    
    # 数据处理相关
    'parse_table_data', 'load_weather_data', 'merge_datasets',
    
    # 结果导出相关
    'export_results',
    
    # 结果处理相关
    'combine_results'
] 