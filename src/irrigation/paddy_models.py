"""
水稻灌溉系统和灌区模型 - 合并了所有水稻灌溉相关的类
包含：灌溉区域、稻田模型、水平衡计算、灌溉系统、模拟器
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple

from .core import SimulationBase
from .config import log, LOG_CONFIG, WARMUP_DAYS, get_warmup_days

# ============================================================================
# 灌溉区域模块
# ============================================================================

class IrrigationArea:
    """
    水稻灌区模型，表示一个水稻灌溉区域，包含水田、低洼地等不同类型的土地
    """
    
    def __init__(self, config: List):
        """
        初始化灌区
        
        参数:
            config: 灌区配置参数列表，包括名称、面积、参数等
        """
        self.name = str(config[1])                 # 灌区名称
        self.single_crop_area = float(config[2])   # 单季稻面积
        self.double_crop_area = float(config[3])   # 双季稻面积
        self.dry_land_area = float(config[4])      # 旱地面积（保留用于作物模型计算）
        self.low_land_area = float(config[5])      # 低洼地面积
        self.water_area = float(config[6])         # 水面面积
        self.plain_area = float(config[7])         # 平原面积
        self.paddy_leakage = float(config[8])      # 水田渗漏率
        self.flowering_ratio = float(config[10])   # 开花期灌溉比例
        self.rotation_batches = int(config[11])    # 轮灌批次
        
        # 气象数据
        self.rainfall_data = {}     # 降雨量数据
        self.evaporation_data = {}  # 蒸发量数据
        
        # 各类土地的初始水位
        self.low_land_level = 0     # 低洼地初始水位
        self.single_crop_levels = None  # 单季稻各批次水位
        self.double_crop_levels = None  # 双季稻各批次水位
        
        # 指向模拟引擎的引用
        self.simulation_engine = None
        
        # 为兼容旧代码保留calculator引用
        self.calculator = None
        
        # 计算结果
        self.results: Dict[str, pd.Series] = {}

    def initialize(self, current_time: datetime, forecast_days: int):
        """
        初始化灌区数据
        
        参数:
            current_time: 当前时间
            forecast_days: 预测天数
        """
        # 检查轮灌批次设置是否有效
        if self.rotation_batches <= 0:
            log('warnings', f'分区{self.name}轮灌批次有误')
            
        # 初始化单季稻和双季稻的各批次水位
        self.single_crop_levels = np.zeros(self.rotation_batches)
        self.double_crop_levels = np.zeros(self.rotation_batches)
        
        # 设置初始水位
        for i in range(self.rotation_batches):
            self.single_crop_levels[i] = -25
            self.double_crop_levels[i] = -25
        
        # 创建时间序列
        start_time = current_time
        end_time = start_time + pd.Timedelta(days=29 + forecast_days)
        time_index = pd.date_range(start_time, end_time, freq='D')
        
        # 定义需要计算的结果类型
        result_keys = [
            # 灌溉量
            'single_crop_irrigation',  # 单季稻灌溉量
            'double_crop_irrigation',  # 双季稻灌溉量
            'flowering_irrigation',    # 开花期灌溉量
            
            # 排水量
            'single_crop_drainage',    # 单季稻排水量
            'double_crop_drainage',    # 双季稻排水量
            'low_land_drainage',       # 低洼地排水量
            'water_surface_drainage',  # 水面排水量
            
            # 渗漏量
            'single_crop_leakage',     # 单季稻渗漏量
            'double_crop_leakage',     # 双季稻渗漏量
            'low_land_leakage',        # 低洼地渗漏量
            
            # 蒸发量
            'single_crop_evaporation', # 单季稻蒸发量
            'double_crop_evaporation', # 双季稻蒸发量
            'low_land_evaporation',    # 低洼地蒸发量
            
            # 水位平衡数据（新增）
            'initial_water_level',     # 起始水位
            'rainfall_record',         # 降雨量记录
            'evaporation_record',      # 蒸发量记录
            'eva_ratio_record',        # 蒸发系数记录
            'water_balance',           # 初始水位平衡
        ]
        
        # 为每种结果类型创建时间序列
        self.results = {
            key: pd.Series(0.0, index=time_index) 
            for key in result_keys
        }

    def get_engine(self):
        """获取模拟引擎，兼容新旧引用"""
        return self.simulation_engine or self.calculator
    
    def get_flowering_periods(self):
        """获取开花期配置"""
        # 动态导入配置，避免循环引用
        from .config import FLOWERING_PERIODS, is_b3_mode
        if is_b3_mode():
            from .config import B3_FLOWERING_PERIODS
            return B3_FLOWERING_PERIODS
        return FLOWERING_PERIODS
    
    def record_results(self, current_time: datetime, result_type: str, value: float):
        """
        记录计算结果
        
        参数:
            current_time: 当前时间
            result_type: 结果类型
            value: 值
        """
        if result_type in self.results:
            self.results[result_type][current_time] = value


# ============================================================================
# 灌溉系统模块
# ============================================================================

class IrrigationSystem:
    """
    水稻灌溉系统模型，管理单季稻和双季稻的灌溉参数
    """
    
    def __init__(self, name: str, grow_num: int):
        """
        初始化灌溉系统
        
        参数:
            name: 系统名称（如"单季稻"、"双季稻"、"旱地"）
            grow_num: 生长阶段数量
        """
        self.name = name
        self.grow_num = grow_num
        
        # 每个生长阶段的参数，包括天数和4个灌溉参数
        self.growth_data = np.zeros([grow_num, 5])
        
        self.current_year = None
        
        # 全年每天的灌溉参数时间序列
        self.time_series: Dict[str, pd.Series] = {}
        
        # 指向模拟引擎的引用
        self.simulation_engine = None
        
        # 兼容旧代码的引用
        self.calculator = None

    def set_period(self, period: int, values: List[float]):
        """
        设置特定生长阶段的参数
        
        参数:
            period: 生长阶段索引
            values: 该阶段的参数值列表
        """
        self.growth_data[period] = values

    def initialize_time_series(self, current_time: datetime):
        """
        初始化全年的灌溉参数时间序列
        
        参数:
            current_time: 当前时间，用于确定年份
        """
        self.current_year = current_time.year
        
        # 创建全年的日期索引（包括闰年）
        time_index = pd.date_range(
            f"{current_time.year}/01/01", 
            periods=366, 
            freq='D'
        )
        
        # 为每个参数创建时间序列
        self.time_series = {
            k: pd.Series(0.0, index=time_index)
            for k in ['eva_ratio', 'H_min', 'Storage', 'H_max']
        }
        
        # 填充每天的灌溉参数
        current = time_index[0]
        for i in range(self.grow_num):
            # 该生长阶段的天数
            days = int(self.growth_data[i, 0])
            
            # 为该阶段的每一天设置参数
            for _ in range(days):
                for j, key in enumerate(
                    ['eva_ratio', 'H_min', 'Storage', 'H_max']
                ):
                    self.time_series[key][current] = self.growth_data[i, j + 1]
                current += pd.Timedelta(days=1)

    def get_value(self, current_time: datetime) -> Tuple[float, float, float, float]:
        """
        获取指定日期的灌溉参数
        
        参数:
            current_time: 需要查询的日期
            
        返回:
            (eva_ratio, H_min, Storage, H_max) 参数元组
        """
        # 同时兼容新旧引用
        engine = self.simulation_engine or self.calculator
        
        # 处理闰年
        if hasattr(engine, 'handle_leap_year'):
            current_time = engine.handle_leap_year(current_time)
        else:
            # 使用工具函数
            from .utils import handle_leap_year
            current_time = handle_leap_year(current_time)
        
        # 统一年份为初始化年份
        if current_time.year != self.current_year:
            current_time = current_time.replace(year=self.current_year)
        
        # 返回当天的灌溉参数
        values = tuple(
            self.time_series[k][current_time]
            for k in ['eva_ratio', 'H_min', 'Storage', 'H_max']
        )
        return values


# ============================================================================
# 稻田模型模块
# ============================================================================

class PaddyFieldModel:
    """
    水稻田水量平衡模型，处理单季稻和双季稻的水量计算
    """
    
    def calculate(self, area, current_time: datetime, irrigation_system):
        """
        计算水稻田（单季稻或双季稻）的水量平衡
        
        参数:
            area: 灌区对象
            current_time: 当前时间
            irrigation_system: 灌溉系统
        
        返回:
            计算后的结果数据
        """
        # 确定是单季稻还是双季稻
        is_single_crop = irrigation_system.name == '单季稻'
        crop_type = 'single_crop' if is_single_crop else 'double_crop'
        
        # 获取对应的水位和面积
        levels = area.single_crop_levels if is_single_crop else area.double_crop_levels
        field_area = area.single_crop_area if is_single_crop else area.double_crop_area
        
        # 水位平衡记录变量初始化
        total_batch_area = 0
        total_water_level = 0
        
        # 计算每个轮灌批次
        for i in range(area.rotation_batches):
            # 获取该日期的灌溉参数
            eva_ratio, H_min, Storage, H_max = irrigation_system.get_value(
                current_time + pd.Timedelta(days=i)
            )
            
            # 计算批次面积（km²）转为亩（1平方公里 = 1500亩）
            batch_area = field_area / area.rotation_batches / 10
            total_batch_area += batch_area
            
            # 记录起始水位（按面积加权）
            total_water_level += levels[i] * batch_area
            
            # 获取模拟引擎
            engine = area.get_engine()
            
            # 直接计算水量平衡
            end_H, Irr, Drain, Leak, actual_E, calculation_process = self.calculate_water_balance(
                levels[i],                         # 初始水位
                eva_ratio,                         # 蒸发系数
                H_min,                             # 最小水位
                Storage,                           # 设计蓄水位
                H_max,                             # 最大水位
                area.paddy_leakage,                # 渗漏率
                area.rainfall_data[current_time],  # 降雨量
                area.evaporation_data[current_time], # 蒸发量
                verbose=getattr(engine, 'verbose', False)
            )
            
            # 更新水位
            levels[i] = end_H
            
            # 计算实际值
            actual_values = {
                f'{crop_type}_irrigation': Irr * batch_area,     # 灌溉量
                f'{crop_type}_drainage': Drain * batch_area,     # 排水量
                f'{crop_type}_leakage': Leak * batch_area,       # 渗漏量
                f'{crop_type}_evaporation': actual_E * batch_area # 蒸发量
            }
            
            # 将结果添加到时间序列中
            for key, value in actual_values.items():
                if key in area.results:
                    area.results[key][current_time] += value
                    
        # 记录水位平衡数据（使用面积加权平均值）
        if total_batch_area > 0:
            # 获取平均蒸发系数（简化处理，使用当天的参数）
            eva_ratio, _, _, _ = irrigation_system.get_value(current_time)
            
            # 计算初始水位平衡
            water_balance = total_water_level / total_batch_area + \
                          area.rainfall_data[current_time] - \
                          area.evaporation_data[current_time] * eva_ratio
            
            # 保存按作物类型分类的水位平衡数据
            if is_single_crop:
                # 单季稻水位平衡数据
                area.results['single_crop_initial_water_level'] = area.results.get('single_crop_initial_water_level', {})
                area.results['single_crop_rainfall_record'] = area.results.get('single_crop_rainfall_record', {})
                area.results['single_crop_evaporation_record'] = area.results.get('single_crop_evaporation_record', {})
                area.results['single_crop_eva_ratio_record'] = area.results.get('single_crop_eva_ratio_record', {})
                area.results['single_crop_water_balance'] = area.results.get('single_crop_water_balance', {})
                
                area.results['single_crop_initial_water_level'][current_time] = total_water_level / total_batch_area
                area.results['single_crop_rainfall_record'][current_time] = area.rainfall_data[current_time]
                area.results['single_crop_evaporation_record'][current_time] = area.evaporation_data[current_time]
                area.results['single_crop_eva_ratio_record'][current_time] = eva_ratio
                area.results['single_crop_water_balance'][current_time] = water_balance
            else:
                # 双季稻水位平衡数据
                area.results['double_crop_initial_water_level'] = area.results.get('double_crop_initial_water_level', {})
                area.results['double_crop_rainfall_record'] = area.results.get('double_crop_rainfall_record', {})
                area.results['double_crop_evaporation_record'] = area.results.get('double_crop_evaporation_record', {})
                area.results['double_crop_eva_ratio_record'] = area.results.get('double_crop_eva_ratio_record', {})
                area.results['double_crop_water_balance'] = area.results.get('double_crop_water_balance', {})
                
                area.results['double_crop_initial_water_level'][current_time] = total_water_level / total_batch_area
                area.results['double_crop_rainfall_record'][current_time] = area.rainfall_data[current_time]
                area.results['double_crop_evaporation_record'][current_time] = area.evaporation_data[current_time]
                area.results['double_crop_eva_ratio_record'][current_time] = eva_ratio
                area.results['double_crop_water_balance'][current_time] = water_balance
            
            # 保留原有的通用水位平衡数据（向下兼容）
            area.results['initial_water_level'][current_time] = total_water_level / total_batch_area
            area.results['rainfall_record'][current_time] = area.rainfall_data[current_time]
            area.results['evaporation_record'][current_time] = area.evaporation_data[current_time]
            area.results['eva_ratio_record'][current_time] = eva_ratio
            area.results['water_balance'][current_time] = water_balance
                    
        # 处理开花期特殊灌溉需求
        self._handle_flowering_period(area, current_time, irrigation_system.name)
        
    def _handle_flowering_period(self, area, current_time: datetime, crop_type: str):
        """
        处理开花期特殊灌溉需求
        
        参数:
            area: 灌区对象
            current_time: 当前时间
            crop_type: 作物类型（"单季稻"或"双季稻"）
        """
        # 获取开花期配置
        FLOWERING_PERIODS = area.get_flowering_periods()
        
        # 获取开花期时间范围
        flowering_start = f"{current_time.year}{FLOWERING_PERIODS[crop_type]['start']}"
        flowering_end = f"{current_time.year}{FLOWERING_PERIODS[crop_type]['end']}"
        
        # 检查当前日期是否在开花期内
        if pd.Timestamp(flowering_start) <= current_time < pd.Timestamp(flowering_end):
            # 在开花期内，直接返回不做特殊处理
            return
            
        # 不在开花期时，转移灌溉量到开花期灌溉
        irrigation_key = (
            'single_crop_irrigation' if crop_type == '单季稻' 
            else 'double_crop_irrigation'
        )
        
        # 计算开花期灌溉量
        flowering_irrigation = area.results[irrigation_key][current_time] * area.flowering_ratio
        area.results['flowering_irrigation'][current_time] = flowering_irrigation
        
        # 清空原灌溉量
        area.results[irrigation_key][current_time] = 0 
        
    def calculate_water_balance(
            self, 
            H_start: float,       # 初始水位
            eva_ratio: float,     # 蒸发系数
            H_min: float,         # 最小水位
            Storage: float,       # 设计蓄水位
            H_max: float,         # 最大水位
            Max_leakH: float,     # 最大渗漏深度
            rainfall: float,      # 降雨量
            evaporation: float,   # 蒸发量
            verbose: bool = False # 是否输出详细信息
        ) -> Tuple[float, float, float, float, float, Dict[str, Any]]:
        """
        计算水田的水量平衡，保持与原Calculator.calculate_paddy_field方法兼容
        
        返回:
            (终止水位, 灌溉量, 排水量, 渗漏量, 蒸发量, 计算过程)
        """
        # 记录计算过程
        calculation_process = {
            'inputs': {
                'H_start': H_start, 
                'eva_ratio': eva_ratio, 
                'H_min': H_min,
                'Storage': Storage, 
                'H_max': H_max, 
                'Max_leakH': Max_leakH,
                'rainfall': rainfall, 
                'evaporation': evaporation
            }
        }
        
        # 计算初始水平衡
        begin_H = H_start + rainfall - evaporation * eva_ratio
        actual_E = evaporation * eva_ratio
        
        calculation_process['initial_balance'] = {
            'begin_H': begin_H, 
            'actual_E': actual_E,
            'formula': f"begin_H = {H_start} + {rainfall} - {evaporation} * {eva_ratio} = {begin_H}"
        }
        
        # 计算渗漏
        if begin_H < 0:
            Leak = 0
        elif begin_H < Max_leakH:
            Leak = begin_H
            begin_H = 0
        else:
            Leak = Max_leakH
            begin_H = begin_H - Max_leakH
            
        calculation_process['leakage'] = {
            'Leak': Leak, 
            'begin_H_after_leak': begin_H
        }
        
        # 计算灌溉和排水
        if begin_H > H_max:
            # 水位过高，需要排水
            Irr = 0
            Drain = begin_H - H_max
            end_H = H_max
            status = "水位超过最大值，需要排水"
        elif begin_H < H_min:
            # 水位过低，需要灌溉
            Irr = Storage - begin_H
            Drain = 0
            end_H = Storage
            status = "水位低于最小值，需要灌溉"
        else:
            # 水位正常，无需灌溉或排水
            Irr = 0
            Drain = 0
            end_H = begin_H
            status = "水位在正常范围内"
            
        calculation_process['final_results'] = {
            'status': status,
            'Irr': Irr,
            'Drain': Drain,
            'end_H': end_H,
            'actual_E': actual_E
        }
        
        return end_H, Irr, Drain, Leak, actual_E, calculation_process


# ============================================================================
# 水平衡计算模块
# ============================================================================

class LowLandModel:
    """
    水田低洼地水量平衡模型
    """
    
    def calculate(self, area, current_time: datetime):
        """
        计算低洼地的水量平衡
        
        参数:
            area: 灌区对象
            current_time: 当前时间
        """
        # 初始水位加上降雨量
        begin_H = area.low_land_level + area.rainfall_data[current_time]
        
        # 获取模拟引擎
        engine = area.get_engine()
        
        # 计算蒸发
        begin_H, actual_E = self.calculate_evaporation(
            current_time, 
            begin_H, 
            area.evaporation_data[current_time]
        )
        
        # 保存蒸发量
        area.results['low_land_evaporation'][current_time] = (
            actual_E * area.low_land_area / 10
        )
        
        # 计算渗漏
        begin_H, leak = self.calculate_leakage(begin_H)
        
        # 保存渗漏量
        area.results['low_land_leakage'][current_time] = (
            leak * area.low_land_area / 10
        )
        
        # 处理排水
        if begin_H > 80:
            # 如果水位超过80mm，需要排水
            area.results['low_land_drainage'][current_time] = (
                (begin_H - 80) * area.low_land_area / 10
            )
            end_H = 80
        else:
            # 否则不需要排水
            area.results['low_land_drainage'][current_time] = 0
            end_H = begin_H
            
        # 更新水位
        area.low_land_level = end_H
        
    def calculate_evaporation(
            self, 
            current_time: datetime, 
            begin_H: float, 
            evaporation: float
        ) -> Tuple[float, float]:
        """
        计算低洼地蒸发量，与原Calculator.calculate_low_land_evaporation保持兼容
        
        参数:
            current_time: 当前时间
            begin_H: 初始水位
            evaporation: 蒸发量
            
        返回:
            (蒸发后水位, 实际蒸发量)
        """
        # 根据不同时期设置不同蒸发系数
        eva_ratio = 0.65 if current_time < pd.Timestamp(f"{current_time.year}/07/01") else 0.8
        
        # 计算最大蒸发量
        max_E = evaporation * eva_ratio
        
        if begin_H > max_E:
            return begin_H - max_E, max_E
        return 0, begin_H
        
    def calculate_leakage(self, begin_H: float) -> Tuple[float, float]:
        """
        计算低洼地渗漏量，与原Calculator.calculate_low_land_leakage保持兼容
        
        参数:
            begin_H: 初始水位
            
        返回:
            (渗漏后水位, 渗漏量)
        """
        if begin_H > 0:
            return 0, begin_H
        return 0, 0


class WaterSurfaceModel:
    """
    水田水面水量平衡模型
    """
    
    def calculate(self, area, current_time: datetime):
        """
        计算水面的水量平衡
        
        参数:
            area: 灌区对象
            current_time: 当前时间
        """
        # 如果降雨量大于蒸发量，产生排水
        if area.rainfall_data[current_time] > area.evaporation_data[current_time]:
            area.results['water_surface_drainage'][current_time] = (
                (area.rainfall_data[current_time] - area.evaporation_data[current_time])
                * area.water_area / 10
            )
        else:
            # 否则不产生排水
            area.results['water_surface_drainage'][current_time] = 0


# ============================================================================
# 水稻灌溉模拟器
# ============================================================================

class IrrigationSimulator(SimulationBase):
    """
    水稻灌溉系统模拟器，计算水稻灌区水量平衡的主要类
    """
    
    def __init__(self, simulation_engine):
        """
        初始化水稻灌溉模拟器
        
        参数:
            simulation_engine: 模拟引擎对象
        """
        super().__init__(simulation_engine)
        
        # 创建水量平衡模型
        self.paddy_field_model = PaddyFieldModel()
        self.low_land_model = LowLandModel()
        self.water_surface_model = WaterSurfaceModel()
    
    def run(self):
        """执行灌溉系统模拟计算"""
        # 验证数据
        self._validate_data()
        
        # 设置计算时间范围（包含预热期历史数据，B3 模式无预热期）
        engine = self.simulation_engine
        warmup = get_warmup_days()
        start_time = pd.Timestamp(engine.current_time) - pd.Timedelta(days=warmup)
        time_range = pd.date_range(
            start_time, 
            periods=engine.forecast_days + warmup, 
            freq='D'
        )
        
        # 逐日计算
        for current in time_range:
            self._simulate_daily_irrigation(current)

    def _simulate_daily_irrigation(self, current):
        """
        模拟单日灌溉情况
        
        参数:
            current: 当前计算日期
        """
        # 获取模拟引擎
        engine = self.simulation_engine
        
        # 遍历每个灌区
        for area in engine.irrigation_manager.irrigation_areas:
            # 1. 计算水稻田（单季稻）
            if area.single_crop_area > 0:
                self.paddy_field_model.calculate(
                    area, 
                    current, 
                    engine.irrigation_manager.irrigation_systems['单季稻']
                )
                
            # 2. 计算水稻田（双季稻）
            if area.double_crop_area > 0:
                self.paddy_field_model.calculate(
                    area, 
                    current, 
                    engine.irrigation_manager.irrigation_systems['双季稻']
                )
                
            # 3. 计算低洼地
            if area.low_land_area > 0:
                self.low_land_model.calculate(area, current)
                
            # 4. 计算水面
            if area.water_area > 0:
                self.water_surface_model.calculate(area, current)


# ============================================================================
# 导出接口（保持兼容性）
# ============================================================================

# 添加新名称（用于重命名）
PaddySimulator = IrrigationSimulator

__all__ = [
    'IrrigationSystem',
    'IrrigationArea',
    'PaddyFieldModel',
    'LowLandModel',
    'WaterSurfaceModel',
    'IrrigationSimulator',
    'PaddySimulator'  # 新名称
] 