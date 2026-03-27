"""
计算器模块 - 合并了所有计算器相关的组件
包含：DataManager, IrrigationManager, ResultExporter, SimulationController, Calculator
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Any, Callable, Optional

from .utils import (
    read_data_file, load_time_config, load_weather_data,
    export_results, handle_leap_year
)
from .config import (
    INPUT_FILES, USE_STATIC_IRRIGATION, STATIC_IRRIGATION_FILES,
    IRRIGATION_SYSTEMS, WARMUP_DAYS, log, LOG_CONFIG,
    is_b3_mode, B3_NC_DIR, B3_YEAR, get_warmup_days
)

# ============================================================================
# 数据管理器
# ============================================================================

class DataManager:
    """
    数据管理器，负责加载和管理各种数据
    """
    
    def __init__(self, calculator, data_path: str, verbose: bool = False):
        """
        初始化数据管理器
        
        参数:
            calculator: 计算器对象
            data_path: 数据文件路径
            verbose: 是否输出详细信息
        """
        self.calculator = calculator
        self.data_path = data_path
        self.verbose = verbose
        
        # 时间配置
        self.current_time: datetime = None
        self.forecast_days: int = 0
        
        # B3 模式适配器
        self._b3_adapter = None
        if is_b3_mode():
            self._init_b3_adapter()
    
    def _init_b3_adapter(self):
        """初始化 B3 NC 数据适配器"""
        try:
            from .nc_adapter import NCDataAdapter
            nc_dir = B3_NC_DIR or self.data_path
            self._b3_adapter = NCDataAdapter(nc_dir, B3_YEAR)
            if self.verbose:
                print(f"B3 适配器已初始化: {nc_dir}")
        except Exception as e:
            print(f"警告: B3 适配器初始化失败: {e}")
            self._b3_adapter = None

    def get_file_path(self, file_key: str) -> str:
        """
        获取数据文件的完整路径
        
        参数:
            file_key: 文件键名
            
        返回:
            文件完整路径
        """
        return os.path.join(self.data_path, INPUT_FILES[file_key])

    def get_static_file_path(self, crop_type: str) -> str:
        """
        获取静态灌溉制度文件的完整路径
        
        参数:
            crop_type: 作物类型，如"单季稻"或"双季稻"
            
        返回:
            文件完整路径
        """
        if crop_type not in STATIC_IRRIGATION_FILES:
            return None
        
        filename = STATIC_IRRIGATION_FILES[crop_type]
        
        # B3 模式：优先使用 B3 数据目录的文件
        if is_b3_mode() and self._b3_adapter:
            b3_path = os.path.join(self._b3_adapter.data_dir, filename)
            if os.path.exists(b3_path):
                return b3_path
        
        # 默认使用 data_path
        return os.path.join(self.data_path, filename)

    def load_time_config(self):
        """
        加载时间配置
        """
        # B3 模式：从 NC 适配器获取时间配置
        if is_b3_mode() and self._b3_adapter:
            try:
                self.current_time, self.forecast_days = self._b3_adapter.get_time_config()
                if self.verbose:
                    print(f"[B3] 时间配置: 起始时间={self.current_time}, 天数={self.forecast_days}")
                return self.current_time, self.forecast_days
            except Exception as e:
                print(f"[B3] 加载时间配置失败: {e}")
        
        # 原有 TXT 模式
        try:
            # 设置文件读取的debug参数与自身的verbose一致
            self.current_time, self.forecast_days = load_time_config(
                self.get_file_path('time_config'),
                debug=self.verbose
            )
            
            if self.verbose:
                print(f"成功加载时间配置: 起始时间={self.current_time}, 预测天数={self.forecast_days}")
                
            return self.current_time, self.forecast_days
        except Exception as e:
            print(f"加载时间配置失败: {str(e)}")
            # 设置默认值以防止程序崩溃
            self.current_time = datetime.now()
            self.forecast_days = 7
            print(f"使用默认时间配置: 起始时间={self.current_time}, 预测天数={self.forecast_days}")
            return self.current_time, self.forecast_days

    def load_irrigation_area_config(self):
        """
        加载灌区配置
        
        返回:
            灌区配置列表
        """
        # B3 模式：从 NC 适配器获取灌区配置
        if is_b3_mode() and self._b3_adapter:
            try:
                area_configs = self._b3_adapter.get_irrigation_area_config()
                if self.verbose:
                    print(f"[B3] 加载灌区配置: {len(area_configs)} 个灌区")
                return area_configs
            except Exception as e:
                print(f"[B3] 加载灌区配置失败: {e}")
        
        # 原有 TXT 模式
        try:
            lines = read_data_file(self.get_file_path('area_config'), debug=self.verbose)
            
            if self.verbose:
                print("读取到的灌区配置行数:", len(lines))
            
            area_configs = []
            # 跳过表头行，解析每一行灌区数据
            for i, line in enumerate(lines[1:], 1):
                values = line.split('\t')
                if self.verbose:
                    print(f"第{i}行数据: {values}")
                    
                if len(values) >= 11:
                    try:
                        # 构建灌区配置数组
                        config = [i]  # 序号
                        config.append(values[0])  # 灌区名称
                        
                        # 解析数值字段
                        for val in values[1:11]:
                            try:
                                config.append(float(val))
                            except ValueError:
                                if self.verbose:
                                    print(f"警告: 无法将值 '{val}' 转换为浮点数，使用0.0代替")
                                config.append(0.0)
                                
                        # 解析轮灌批次
                        rotation_batches = 1
                        if len(values) > 11:
                            try:
                                rotation_batches = int(values[11])
                            except (ValueError, IndexError):
                                if self.verbose:
                                    print(f"警告: 使用默认轮灌批次值1")
                        config.append(rotation_batches)
                        
                        if self.verbose:
                            print(f"处理后的配置: {config}")
                            
                        area_configs.append(config)
                        
                    except Exception as e:
                        if self.verbose:
                            print(f"处理第{i}行时出错: {str(e)}")
                            print(f"跳过该行: {values}")
                        continue
            
            if not area_configs:
                print("警告: 未能加载任何灌区配置，请检查配置文件格式")
                if self.verbose:
                    print(f"配置文件内容预览: {lines[:3]}")
                    
            return area_configs
        except Exception as e:
            print(f"加载灌区配置时出错: {str(e)}")
            return []  # 返回空列表以防止程序崩溃

    def _load_b3_builtin_irrigation_params(self):
        """
        加载 B3 模式内置灌溉制度参数（不依赖外部文件）
        
        返回:
            灌溉系统数据（与 load_irrigation_system_data 格式兼容）
        """
        from config_b3 import B3_SINGLE_CROP_PARAMS, B3_DOUBLE_CROP_PARAMS
        
        merged_data = []
        
        # 按月份顺序（4-9月）生成参数
        for month in range(4, 10):
            single = B3_SINGLE_CROP_PARAMS.get(month, {})
            double = B3_DOUBLE_CROP_PARAMS.get(month, {})
            
            row = [
                # 单季稻参数: [生长天数, 蒸发系数, 水位下限, 设计蓄水位, 水位上限]
                single.get('days', 30),
                single.get('kc', 1.0),
                single.get('h_min', -35.0),
                single.get('storage', -15.0),
                single.get('h_max', 10.0),
                # 双季稻参数
                double.get('days', 30),
                double.get('kc', 0.5),
                double.get('h_min', -45.0),
                double.get('storage', -25.0),
                double.get('h_max', 0.0),
            ]
            merged_data.append(row)
        
        if self.verbose:
            print(f"[B3] 使用内置灌溉制度参数，共 {len(merged_data)} 个生育期")
        
        return merged_data

    def load_static_irrigation_data(self):
        """
        从静态灌溉制度文件加载灌溉系统数据
        
        返回:
            灌溉系统数据列表 [单季稻数据, 双季稻数据]
        """
        crop_types = ['单季稻', '双季稻']
        irrigation_data = []
        
        for crop_type in crop_types:
            file_path = self.get_static_file_path(crop_type)
            if not file_path or not os.path.exists(file_path):
                if self.verbose:
                    print(f"警告: 静态灌溉制度文件 {file_path} 不存在")
                continue
                
            try:
                # 读取文件内容
                lines = read_data_file(file_path)
                if not lines or len(lines) < 3:
                    if self.verbose:
                        print(f"警告: 静态灌溉制度文件 {file_path} 格式不正确")
                    continue
                
                # 跳过标题行和表头行，从第三行开始读取数据
                data = []
                for line in lines[2:]:
                    line = line.strip()
                    # 跳过空行和分隔符行
                    if not line or line.startswith('-') or line.startswith('#'):
                        continue
                    
                    values = line.split()
                    if len(values) >= 7:  # 开始日期, 结束日期, 生长天数, 蒸发系数, 水位下限, 设计蓄水位, 水位上限
                        try:
                            # 提取生长天数、蒸发系数和水位参数
                            growth_days = float(values[2])
                            eva_ratio = float(values[3])
                            h_min = float(values[4])
                            storage = float(values[5])
                            h_max = float(values[6])
                            
                            # 创建灌溉系统参数列表
                            system_params = [growth_days, eva_ratio, h_min, storage, h_max]
                            data.append(system_params)
                        except (ValueError, IndexError) as e:
                            if self.verbose:
                                print(f"处理静态灌溉制度文件 {file_path} 行时出错: {str(e)}")
                
                irrigation_data.append(data)
                    
            except Exception as e:
                if self.verbose:
                    print(f"处理静态灌溉制度文件 {file_path} 时出错: {str(e)}")
                
        return irrigation_data

    def load_irrigation_system_data(self):
        """
        加载灌溉系统配置数据
        
        返回:
            灌溉系统数据
        """
        # B3 模式：使用内置参数，不依赖外部文件
        if is_b3_mode():
            return self._load_b3_builtin_irrigation_params()
        
        # 如果配置为使用静态灌溉制度文件
        if USE_STATIC_IRRIGATION:
            static_data = self.load_static_irrigation_data()
            if static_data and len(static_data) == 2:
                # 创建与原始格式兼容的数据结构
                single_crop_data = static_data[0]
                double_crop_data = static_data[1]
                
                # 合并为一个二维数组，每行包含两种作物的数据
                merged_data = []
                
                # 确保两个列表长度一致
                max_rows = max(len(single_crop_data), len(double_crop_data))
                for i in range(max_rows):
                    row = []
                    # 添加单季稻数据
                    if i < len(single_crop_data):
                        row.extend(single_crop_data[i])
                    else:
                        # 填充默认值
                        row.extend([0.0, 0.5, -45.0, -25.0, 0.0])
                    
                    # 添加双季稻数据
                    if i < len(double_crop_data):
                        row.extend(double_crop_data[i])
                    else:
                        # 填充默认值
                        row.extend([0.0, 0.5, -45.0, -25.0, 0.0])
                    
                    merged_data.append(row)
                
                if self.verbose:
                    print(f"从静态灌溉制度文件加载了 {len(merged_data)} 行数据")
                
                return merged_data
        
        # 如果静态文件加载失败或未启用，回退到原始方式
        lines = read_data_file(self.get_file_path('irrigation_system'))
        
        # 将表格数据转换为浮点数，跳过表头行
        data = []
        for i, line in enumerate(lines):
            # 尝试判断并跳过表头行
            if i < 2 or "开始日期" in line or "结束日期" in line:
                if self.verbose:
                    print(f"跳过表头行: {line}")
                continue
                
            try:
                row_data = [float(x) if x.strip() else 0 for x in line.split('\t')]
                data.append(row_data)
            except ValueError as e:
                if self.verbose:
                    print(f"跳过无法解析的行: {line}, 错误: {str(e)}")
        
        if not data and self.verbose:
            print("警告: 灌溉系统数据解析后为空")
            
        return data

    def load_weather_data(self, area_names):
        """
        加载气象数据
        
        参数:
            area_names: 灌区名称列表
            
        返回:
            (降雨量数据, 蒸发量数据)
        """
        # B3 模式：从 NC 适配器获取气象数据
        if is_b3_mode() and self._b3_adapter:
            try:
                rainfall, evaporation = self._b3_adapter.get_weather_data()
                # B3 是单灌区，为所有灌区名使用相同数据
                rainfall_data = {name: rainfall for name in area_names}
                evaporation_data = {name: evaporation for name in area_names}
                if self.verbose:
                    print(f"[B3] 气象数据加载完成: {len(rainfall)} 天")
                return rainfall_data, evaporation_data
            except Exception as e:
                print(f"[B3] 加载气象数据失败: {e}")
        
        # 原有 TXT 模式
        # 加载降雨量数据
        rainfall_data = load_weather_data(
            self.get_file_path('rainfall'),
            area_names
        )
        
        # 加载蒸发量数据
        evaporation_data = load_weather_data(
            self.get_file_path('evaporation'),
            area_names
        )
        
        return rainfall_data, evaporation_data
        
    def load_crop_data(self):
        """
        加载作物数据
        
        返回:
            (作物数据文件路径, 旱地面积文件路径, 分区文件路径)
        """
        crop_file = self.get_file_path('crop')
        dry_area_file = self.get_file_path('dry_area')
        fenqu_file = self.get_file_path('fenqu')
        
        return crop_file, dry_area_file, fenqu_file


# ============================================================================
# 灌溉管理器
# ============================================================================

class IrrigationManager:
    """
    水资源管理器，负责管理水稻灌溉系统和灌区
    """
    
    def __init__(self, calculator):
        """
        初始化灌溉管理器
        
        参数:
            calculator: 计算器对象
        """
        self.calculator = calculator
        
        # 灌区数据
        self.irrigation_areas: List = []
        
        # 灌溉系统
        self.irrigation_systems: Dict[str, Any] = {}

    def create_irrigation_areas(self, area_configs: List):
        """
        根据配置创建灌区对象
        
        参数:
            area_configs: 灌区配置列表
        """
        # 延迟导入以避免循环依赖
        from .paddy_models import IrrigationArea
        
        self.irrigation_areas = []
        
        for config in area_configs:
            # 创建灌区对象
            area = IrrigationArea(config)
            area.calculator = self.calculator
            self.irrigation_areas.append(area)
            
        return self.irrigation_areas

    def create_irrigation_systems(self, system_data):
        """
        创建灌溉系统对象
        
        参数:
            system_data: 灌溉系统数据
        """
        # 延迟导入以避免循环依赖
        from .paddy_models import IrrigationSystem
        
        self.irrigation_systems = {}
        
        # 创建各种灌溉系统
        for name, config in IRRIGATION_SYSTEMS.items():
            # 创建系统对象
            system = IrrigationSystem(name, config['periods'])
            system.calculator = self.calculator
            
            # 设置各阶段参数
            for i in range(min(config['periods'], len(system_data))):
                system.set_period(i, system_data[i][config['data_slice']])
                
            # 保存到系统列表
            self.irrigation_systems[name] = system
            
        return self.irrigation_systems

    def assign_weather_data(self, rainfall_data: Dict, evaporation_data: Dict):
        """
        将气象数据分配给各灌区
        
        参数:
            rainfall_data: 降雨量数据
            evaporation_data: 蒸发量数据
        """
        for area in self.irrigation_areas:
            if area.name in rainfall_data:
                area.rainfall_data = rainfall_data[area.name]
            if area.name in evaporation_data:
                area.evaporation_data = evaporation_data[area.name]

    def initialize_systems(self, current_time: datetime, forecast_days: int):
        """
        初始化灌溉系统和灌区
        
        参数:
            current_time: 当前时间
            forecast_days: 预测天数
        """
        # 设置历史数据起点（预热期，B3 模式下为 0）
        warmup = get_warmup_days()
        start_time = current_time - pd.Timedelta(days=warmup)
        
        # 初始化灌溉系统时间序列
        for system in self.irrigation_systems.values():
            system.initialize_time_series(current_time)
            
        # 初始化灌区
        for area in self.irrigation_areas:
            area.initialize(start_time, forecast_days)
            
    def get_area_names(self):
        """
        获取所有灌区名称
        
        返回:
            灌区名称列表
        """
        return [area.name for area in self.irrigation_areas]
        
    def get_area_by_name(self, area_name):
        """
        根据名称获取灌区对象
        
        参数:
            area_name: 灌区名称
            
        返回:
            灌区对象
        """
        return next((a for a in self.irrigation_areas if a.name == area_name), None)
        
    def get_area_results(self, area_name, keys, current_time):
        """
        获取指定灌区在指定时间点的计算结果
        
        参数:
            area_name: 灌区名称
            keys: 需要获取的结果键名列表
            current_time: 时间点
            
        返回:
            结果汇总值
        """
        area = self.get_area_by_name(area_name)
        if not area:
            return 0.0
            
        return sum(area.results[k][current_time] for k in keys if k in area.results) 
    
    def get_area_result(self, area_name, key, current_time):
        """
        获取指定灌区在指定时间点的单个计算结果
        
        参数:
            area_name: 灌区名称
            key: 需要获取的结果键名
            current_time: 时间点
            
        返回:
            单个结果值
        """
        area = self.get_area_by_name(area_name)
        if not area or key not in area.results:
            return 0.0
            
        return area.results[key][current_time]


# ============================================================================
# 结果导出器
# ============================================================================

class ResultExporter:
    """
    结果导出器，负责处理计算结果的导出
    """
    
    def __init__(self, calculator):
        """
        初始化结果导出器
        
        参数:
            calculator: 计算器对象
        """
        self.calculator = calculator
        self.irrigation_file = None
        self.drainage_file = None
        
    def set_output_files(self, irrigation_file: str, drainage_file: str):
        """
        设置输出文件名
        
        参数:
            irrigation_file: 灌溉结果输出文件名
            drainage_file: 排水结果输出文件名
        """
        self.irrigation_file = irrigation_file
        self.drainage_file = drainage_file
        
    def export_results(self, data_path: str, current_time: datetime, forecast_days: int, return_data=False):
        """
        导出计算结果
        
        参数:
            data_path: 数据文件路径
            current_time: 当前时间
            forecast_days: 预测天数
            return_data: 是否返回计算结果数据
            
        返回:
            计算结果数据字典
        """
        # 检查输出文件是否已设置
        if not self.irrigation_file or not self.drainage_file:
            raise ValueError("请先通过set_output_files方法设置输出文件名")
            
        # 获取灌区名称列表
        area_names = self.calculator.irrigation_manager.get_area_names()
        
        # 存储结果
        results = {}
        
        # 灌溉量数据获取函数
        def get_irrigation_data(area_name: str, current_time: datetime) -> float:
            irrigation_keys = [
                'single_crop_irrigation',  # 单季稻灌溉量
                'double_crop_irrigation',  # 双季稻灌溉量
                'flowering_irrigation'     # 开花期灌溉量
            ]
            return self.calculator.irrigation_manager.get_area_results(
                area_name, irrigation_keys, current_time
            )
            
        # 导出灌溉量结果
        results['irrigation'] = export_results(
            data_path,
            self.irrigation_file,
            area_names,
            get_irrigation_data,
            current_time,
            forecast_days,
            return_data=return_data
        )
        
        # 排水量数据获取函数
        def get_drainage_data(area_name: str, current_time: datetime) -> float:
            drainage_keys = [
                'single_crop_drainage',    # 单季稻排水量
                'double_crop_drainage',    # 双季稻排水量
                'low_land_drainage',       # 低洼地排水量
                'water_surface_drainage'   # 水面排水量
            ]
            return self.calculator.irrigation_manager.get_area_results(
                area_name, drainage_keys, current_time
            )
            
        # 导出排水量结果
        results['drainage'] = export_results(
            data_path,
            self.drainage_file,
            area_names,
            get_drainage_data,
            current_time,
            forecast_days,
            return_data=return_data
        )
        
        # 导出水位平衡数据
        self.export_water_balance_data(data_path, area_names, current_time, forecast_days, return_data)
        
        # 导出不同类型的灌溉需水数据
        self.export_irrigation_requirements_by_type(data_path, area_names, current_time, forecast_days, return_data)
        
        return results

    def export_water_balance_data(self, data_path: str, area_names: List[str], current_time: datetime, forecast_days: int, return_data=False):
        """
        导出水位平衡数据
        
        参数:
            data_path: 数据文件路径
            area_names: 灌区名称列表
            current_time: 当前时间
            forecast_days: 预测天数
            return_data: 是否返回计算结果数据
        """
        # 定义水位平衡相关数据类型
        balance_data_keys = [
            'initial_water_level',  # 起始水位
            'rainfall_record',      # 降雨量
            'evaporation_record',   # 蒸发量
            'eva_ratio_record',     # 蒸发系数
            'water_balance'         # 初始水位平衡
        ]
        
        # 分别为单季稻和双季稻导出水位平衡数据
        crop_types = {
            'single_crop': 'water_balance_single_crop.txt',
            'double_crop': 'water_balance_double_crop.txt'
        }
        
        for crop_type, file_name in crop_types.items():
            # 数据获取函数
            def get_crop_balance_data(area_name: str, current_time: datetime, crop_type=crop_type) -> float:
                area = self.calculator.irrigation_manager.get_area_by_name(area_name)
                if not area:
                    return 0.0
                
                # 确保该区域有相应的作物类型
                if crop_type == 'single_crop' and area.single_crop_area <= 0:
                    return 0.0
                if crop_type == 'double_crop' and area.double_crop_area <= 0:
                    return 0.0
                
                # 获取水位平衡数据 - 使用作物特定的键
                data_key = f"{crop_type}_water_balance"
                if data_key in area.results and current_time in area.results[data_key]:
                    return area.results[data_key][current_time]
                
                return 0.0
            
            # 导出结果
            export_results(
                data_path,
                file_name,
                area_names,
                get_crop_balance_data,
                current_time,
                forecast_days,
                return_data=False,  # 水位平衡数据不需要返回
                include_warmup_days=True  # 包含预热期数据
            )
            
    def export_irrigation_requirements_by_type(self, data_path: str, area_names: List[str], current_time: datetime, forecast_days: int, return_data=False):
        """
        按作物类型导出灌溉需水数据
        
        参数:
            data_path: 数据文件路径
            area_names: 灌区名称列表
            current_time: 当前时间
            forecast_days: 预测天数
            return_data: 是否返回计算结果数据
        """
        # 定义不同作物类型的灌溉需水和对应的输出文件名
        crop_irrigation_types = {
            'single_crop_irrigation': 'irrigation_single_crop.txt',  # 单季稻灌溉需水
            'double_crop_irrigation': 'irrigation_double_crop.txt'   # 双季稻灌溉需水
        }
        
        # 分别导出每种作物类型的灌溉需水数据
        for irrigation_type, file_name in crop_irrigation_types.items():
            # 数据获取函数
            def get_irrigation_data(area_name: str, current_time: datetime, irrigation_type=irrigation_type) -> float:
                return self.calculator.irrigation_manager.get_area_result(
                    area_name, irrigation_type, current_time
                )
            
            # 导出结果
            export_results(
                data_path,
                file_name,
                area_names,
                get_irrigation_data,
                current_time,
                forecast_days,
                return_data=False,  # 灌溉需水数据不需要返回
                include_warmup_days=True  # 包含预热期数据
            )


# ============================================================================
# 模拟控制器
# ============================================================================

class SimulationController:
    """
    模拟控制器，负责管理旱地作物和水稻灌溉的不同模拟模式
    """
    
    def __init__(self, calculator):
        """
        初始化模拟控制器
        
        参数:
            calculator: 计算器对象
        """
        self.calculator = calculator
        self.mode = 'irrigation'  # 默认模式为灌溉
        
        # 各种计算模式的计算器
        self.mode_calculators = {
            'irrigation': None,  # 水稻灌溉模式
            'crop': None         # 旱地作物模式
        }
        
        # 作物计算器（为保持向后兼容性）
        self.crop_calculator = None
        
    def set_mode(self, mode: str):
        """
        设置计算模式
        
        参数:
            mode: 计算模式，'irrigation'(水稻灌溉)或'crop'(旱地作物)
        """
        if mode in ['irrigation', 'crop']:
            self.mode = mode
            
            # 使用更清晰的模式名称
            mode_display = {
                'crop': '旱地作物(dryland)',
                'irrigation': '水稻灌溉(paddy)',
            }.get(mode, mode)
            
            print(f"\n=== 切换到{mode_display}模式 ===")
            
            if mode == 'crop':
                self._init_crop_mode()
        else:
            log('errors', f"不支持的计算模式: {mode}")
            raise ValueError(f"不支持的计算模式: {mode}")
            
        return self.mode
            
    def _init_crop_mode(self):
        """
        初始化旱地作物模式
        """
        if self.mode_calculators['crop'] is None:
            # 延迟导入以避免循环依赖
            from .dryland_models import CropSimulator
            
            # 创建旱地作物计算器
            self.mode_calculators['crop'] = CropSimulator(self.calculator)
            self.crop_calculator = self.mode_calculators['crop']
            
            # 加载作物数据
            crop_file, dry_area_file, fenqu_file = self.calculator.data_manager.load_crop_data()
            
            # 初始化作物计算器
            self.crop_calculator.initialize(crop_file, dry_area_file, fenqu_file)
    
    def init_irrigation_mode(self):
        """
        初始化水稻灌溉模式
        """
        if self.mode_calculators['irrigation'] is None:
            # 延迟导入以避免循环依赖
            from .paddy_models import IrrigationSimulator
            
            # 创建水稻灌溉计算器
            self.mode_calculators['irrigation'] = IrrigationSimulator(self.calculator)
            
    def run_calculation(self):
        """
        执行当前模式的计算
        """
        calculator = self.mode_calculators[self.mode]
        if calculator is None:
            raise ValueError(f"计算器{self.mode}未初始化")
        calculator.run()
        
    def get_current_simulator(self):
        """
        获取当前模式的计算器
        
        返回:
            当前模式的计算器
        """
        return self.mode_calculators[self.mode]


# ============================================================================
# 主计算器
# ============================================================================

class Calculator:
    """
    重构后的主计算器类，整合各模块并保持与原版API兼容
    """
    
    def __init__(self, data_path: str, verbose: bool = False):
        """
        初始化计算器
        
        参数:
            data_path: 数据文件路径
            verbose: 是否输出详细信息
        """
        self.data_path = data_path
        self.verbose = verbose
        
        # 初始化关键属性，确保API兼容性
        self.current_time = None
        self.forecast_days = 0
        self.irrigation_file = None
        self.drainage_file = None
        
        # 组件初始化
        self.data_manager = DataManager(self, data_path, verbose)
        self.irrigation_manager = IrrigationManager(self)
        self.result_exporter = ResultExporter(self)
        self.simulation_controller = SimulationController(self)
        
        # 保持核心属性引用
        self.crop_calculator = None

    def _get_file_path(self, file_key: str) -> str:
        """
        获取数据文件的完整路径
        
        参数:
            file_key: 文件键名
            
        返回:
            文件完整路径
        """
        return self.data_manager.get_file_path(file_key)

    def load_data(self):
        """
        加载所有数据
        """
        # 加载时间配置
        current_time, forecast_days = self.data_manager.load_time_config()
        
        # 设置时间配置
        self.current_time = current_time
        self.forecast_days = forecast_days
        
        # 加载灌区配置
        area_configs = self.data_manager.load_irrigation_area_config()
        
        # 创建灌区对象
        self.irrigation_manager.create_irrigation_areas(area_configs)
        
        # 加载灌溉系统配置
        system_data = self.data_manager.load_irrigation_system_data()
        
        # 创建灌溉系统
        self.irrigation_manager.create_irrigation_systems(system_data)
        
        # 加载气象数据
        area_names = self.irrigation_manager.get_area_names()
        rainfall_data, evaporation_data = self.data_manager.load_weather_data(area_names)
        
        # 将气象数据分配给灌区
        self.irrigation_manager.assign_weather_data(rainfall_data, evaporation_data)
        
        # 初始化灌溉系统和灌区
        self.irrigation_manager.initialize_systems(current_time, forecast_days)
        
        # 初始化灌溉模式计算器
        self.simulation_controller.init_irrigation_mode()

    def set_mode(self, mode: str, irrigation_file: str = None, drainage_file: str = None):
        """
        设置计算模式
        
        参数:
            mode: 计算模式，'irrigation'或'crop'
            irrigation_file: 灌溉结果输出文件名
            drainage_file: 排水结果输出文件名
        """
        # 设置输出文件
        if irrigation_file is not None and drainage_file is not None:
            self.result_exporter.set_output_files(irrigation_file, drainage_file)
        
        # 设置模式
        self.simulation_controller.set_mode(mode)
        
        # 更新属性
        self.crop_calculator = self.simulation_controller.crop_calculator

    def run_calculation(self):
        """
        执行当前模式的计算
        """
        self.simulation_controller.run_calculation()

    def export_results(self, return_data=False):
        """
        导出计算结果
        
        参数:
            return_data: 是否返回计算结果数据
            
        返回:
            计算结果数据字典
        """
        return self.result_exporter.export_results(
            self.data_path,
            self.current_time,
            self.forecast_days,
            return_data
        )
