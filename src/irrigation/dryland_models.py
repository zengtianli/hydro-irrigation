"""
旱地作物模型和需水计算模块 - 合并了所有旱地作物相关的类
包含：作物定义、区域管理、需水量计算、模拟器
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

from .core import SimulationBase
from .config import log, LOG_CONFIG

# ============================================================================
# 作物定义模块
# ============================================================================

class Crop:
    """
    旱地作物模型类，表示一种旱地作物及其需水参数
    """
    
    def __init__(self, name: str, water_75: float, water_90: float):
        """
        初始化旱地作物
        
        参数:
            name: 作物名称
            water_75: 75%水文年需水量 (mm/d)
            water_90: 90%水文年需水量 (mm/d)
        """
        self.name = name
        self.water_requirements = {
            75: water_75,  # 75%水文年需水量
            90: water_90   # 90%水文年需水量
        }
    
    def get_daily_water(self, hydrological_year: int) -> float:
        """
        获取指定水文年的单位面积需水量
        
        参数:
            hydrological_year: 水文年类型 (75或90)
            
        返回:
            单位面积日需水量 (mm/d)
        """
        # 确保使用有效的水文年
        if hydrological_year not in [75, 90]:
            # 默认使用90%水文年
            hydrological_year = 90
            
        return self.water_requirements[hydrological_year]
    
    def calculate_water_volume(self, area: float, hydrological_year: int) -> float:
        """
        计算特定面积和水文年条件下的需水量
        
        参数:
            area: 种植面积 (km²)
            hydrological_year: 水文年类型 (75或90)
            
        返回:
            需水量 (立方米/日)
        """
        # 获取单位面积需水量
        daily_water = self.get_daily_water(hydrological_year)
        
        # 转换单位：mm/d * km² -> m³/d
        # 原始转换系数: 1000/10000 = 0.1
        return daily_water * area * 0.1


class CropRegistry:
    """
    旱地作物注册表，管理所有旱地作物
    """
    
    def __init__(self):
        """初始化作物注册表"""
        self.crops: Dict[str, Crop] = {}
    
    def add_crop(self, crop: Crop) -> None:
        """
        添加作物到注册表
        
        参数:
            crop: 作物对象
        """
        self.crops[crop.name] = crop
    
    def get_crop(self, name: str) -> Optional[Crop]:
        """
        获取作物
        
        参数:
            name: 作物名称
            
        返回:
            作物对象，如不存在则返回None
        """
        return self.crops.get(name)
    
    def list_crops(self) -> List[str]:
        """
        获取所有作物名称
        
        返回:
            作物名称列表
        """
        return list(self.crops.keys())
    
    def load_from_file(self, file_path: str) -> None:
        """
        从文件加载作物数据
        
        参数:
            file_path: 作物数据文件路径
        """
        try:
            with open(file_path, 'r', encoding='UTF-8') as f:
                lines = [line.strip() for line in f if line.strip()]
                
                # 跳过表头行
                for line in lines[1:]:
                    fields = line.split('\t')
                    
                    if len(fields) >= 3:
                        name = fields[0]
                        try:
                            water_75 = float(fields[1])  # 75%水文年需水量
                            water_90 = float(fields[2])  # 90%水文年需水量
                            
                            # 创建作物对象并添加到注册表
                            crop = Crop(name, water_75, water_90)
                            self.add_crop(crop)
                            
                        except ValueError as e:
                            log('warnings', f"解析作物数据失败 '{name}': {e}")
                            
        except Exception as e:
            log('errors', f"读取作物数据文件失败: {e}")


# ============================================================================
# 区域管理模块
# ============================================================================

class AreaLimits:
    """
    旱地区域面积限制模型
    """
    
    def __init__(self, area_name: str, dry_land: float, misc_land: float):
        """
        初始化区域面积限制
        
        参数:
            area_name: 区域名称
            dry_land: 旱地面积 (km²)
            misc_land: 其他面积 (km²)
        """
        self.area_name = area_name
        self.dry_land = dry_land  # 旱地面积
        self.misc_land = misc_land  # 其他面积
        
    @property
    def total_available(self) -> float:
        """
        获取总可用面积
        
        返回:
            总可用面积 (km²)
        """
        return self.dry_land + self.misc_land


class CropArea:
    """
    旱地区域作物种植面积模型
    """
    
    def __init__(self, area_name: str, hydrological_year: int = 90):
        """
        初始化区域作物种植面积
        
        参数:
            area_name: 区域名称
            hydrological_year: 水文年类型，默认90
        """
        self.area_name = area_name
        self.hydrological_year = hydrological_year
        self.crop_areas: Dict[str, float] = {}  # 作物种植面积 {作物名: 面积km²}
    
    def set_area(self, crop_name: str, area: float) -> None:
        """
        设置作物种植面积
        
        参数:
            crop_name: 作物名称
            area: 种植面积 (km²)
        """
        self.crop_areas[crop_name] = area
    
    def get_area(self, crop_name: str) -> float:
        """
        获取作物种植面积
        
        参数:
            crop_name: 作物名称
            
        返回:
            种植面积 (km²)，如不存在则返回0
        """
        return self.crop_areas.get(crop_name, 0.0)
    
    @property
    def total_area(self) -> float:
        """
        获取总种植面积
        
        返回:
            总种植面积 (km²)
        """
        return sum(self.crop_areas.values())
    
    def get_crop_list(self) -> List[str]:
        """
        获取种植的所有作物名称
        
        返回:
            作物名称列表
        """
        return list(self.crop_areas.keys())


class AreaManager:
    """
    旱地区域管理器，管理区域面积限制和作物种植面积
    """
    
    def __init__(self):
        """初始化区域管理器"""
        self.area_limits: Dict[str, AreaLimits] = {}  # 区域面积限制
        self.crop_areas: Dict[str, CropArea] = {}  # 区域作物种植面积
    
    def add_area_limits(self, area_limits: AreaLimits) -> None:
        """
        添加区域面积限制
        
        参数:
            area_limits: 区域面积限制对象
        """
        self.area_limits[area_limits.area_name] = area_limits
    
    def add_crop_area(self, crop_area: CropArea) -> None:
        """
        添加区域作物种植面积
        
        参数:
            crop_area: 区域作物种植面积对象
        """
        self.crop_areas[crop_area.area_name] = crop_area
    
    def load_area_limits_from_file(self, file_path: str) -> None:
        """
        从文件加载区域面积限制
        
        参数:
            file_path: 分区数据文件路径
        """
        try:
            with open(file_path, 'r', encoding='UTF-8') as f:
                lines = [line.strip() for line in f if line.strip()]
                
                # 跳过表头行
                for line in lines[1:]:
                    fields = line.split('\t')
                    
                    if len(fields) >= 5:
                        area_name = fields[0]
                        try:
                            dry_land = float(fields[3])   # 旱地面积
                            misc_land = float(fields[4])  # 其他面积
                            
                            # 创建区域面积限制对象并添加
                            area_limits = AreaLimits(area_name, dry_land, misc_land)
                            self.add_area_limits(area_limits)
                            
                        except ValueError as e:
                            log('warnings', f"解析区域面积限制失败 '{area_name}': {e}")
                            
        except Exception as e:
            log('errors', f"读取分区面积限制文件失败: {e}")
    
    def load_crop_areas_from_file(self, file_path: str) -> None:
        """
        从文件加载区域作物种植面积
        
        参数:
            file_path: 旱地作物面积文件路径
        """
        try:
            with open(file_path, 'r', encoding='UTF-8') as f:
                lines = [line.strip() for line in f if line.strip()]
                
                # 获取表头（作物名称）
                header = lines[0].split('\t')[1:]
                
                # 解析每一行（每个区域）数据
                for line in lines[1:]:
                    fields = line.split('\t')
                    if len(fields) < 2:
                        continue
                        
                    area_name = fields[0]  # 区域名称
                    
                    # 解析水文年类型
                    hydrological_year = 90
                    try:
                        hydrological_year = int(fields[1])
                    except (ValueError, IndexError):
                        log('warnings', f"警告: 区域 {area_name} 的水文年数据无效，使用默认值90")
                    
                    # 创建区域作物种植面积对象
                    crop_area = CropArea(area_name, hydrological_year)
                    
                    # 解析各作物种植面积
                    for crop_name, area_value in zip(header[1:], fields[2:]):
                        try:
                            area = float(area_value)
                            crop_area.set_area(crop_name, area)
                        except ValueError:
                            log('warnings', f"解析种植面积失败: {area_name} - {crop_name}")
                    
                    # 添加到区域管理器
                    self.add_crop_area(crop_area)
                    
        except Exception as e:
            log('errors', f"读取作物种植面积文件失败: {e}")
    
    def validate_areas(self, verbose: bool = False) -> List[Tuple[str, float, float]]:
        """
        验证各区域的种植面积是否超过限制
        
        参数:
            verbose: 是否输出详细信息
            
        返回:
            超出限制的区域列表 [(区域名, 种植面积, 可用面积)]
        """
        
        over_limits = []
        
        # 遍历每个区域的作物种植面积
        for area_name, crop_area in self.crop_areas.items():
            # 检查该区域是否有面积限制
            if area_name not in self.area_limits:
                if verbose:
                    log('warnings', f"警告: 未找到区域 {area_name} 的面积限制")
                continue
            
            # 获取区域面积限制
            area_limits = self.area_limits[area_name]
            
            # 计算该区域的总种植面积
            total_crop_area = crop_area.total_area
            available_area = area_limits.total_available
            
            # 检查面积是否超限
            if total_crop_area > available_area:
                over_area = total_crop_area - available_area
                over_limits.append((area_name, total_crop_area, available_area))
                
                if verbose:
                    log('warnings', f"警告: 区域 {area_name} 的总种植面积 {total_crop_area:.2f} km² "
                          f"超过可用面积 {available_area:.2f} km² (超出 {over_area:.2f} km²)")
                          
        return over_limits
    
    def get_hydrological_year(self, area_name: str) -> int:
        """
        获取区域的水文年类型
        
        参数:
            area_name: 区域名称
            
        返回:
            水文年类型，如不存在则返回90
        """
        if area_name in self.crop_areas:
            return self.crop_areas[area_name].hydrological_year
        return 90


# ============================================================================
# 需水量计算模块
# ============================================================================

class WaterRequirementCalculator:
    """
    旱地作物需水计算模型，计算不同旱地作物的灌溉需水量
    """
    
    def __init__(self, crop_registry: CropRegistry, area_manager: AreaManager):
        """
        初始化旱地作物需水计算模型
        
        参数:
            crop_registry: 作物注册表
            area_manager: 区域管理器
        """
        self.crop_registry = crop_registry
        self.area_manager = area_manager
        self.crop_water_data: Dict[str, Dict[str, float]] = {}  # {作物名: {区域名: 需水量}}
        self.verbose = False
    
    def set_verbose(self, verbose: bool):
        """设置是否输出详细信息"""
        self.verbose = verbose
    
    def _print_debug(self, message: str):
        """打印调试信息"""
        if self.verbose:
            log('calculation', message)
            
    def calculate_water_requirements(self) -> Dict[str, Dict[str, float]]:
        """
        计算各区域各作物的需水量
        
        返回:
            需水量数据 {作物名: {区域名: 需水量}}
        """
        log('calculation', "\n=== 开始计算作物需水量 ===")
        
        # 清空之前的计算结果
        self.crop_water_data = {}
        
        # 遍历每个区域
        for area_name, crop_area in self.area_manager.crop_areas.items():
            # 获取水文年类型
            hydrological_year = crop_area.hydrological_year
            
            # 输出调试信息
            if LOG_CONFIG['levels'].get('crop_details', False):
                log('crop_details', f"\n区域: {area_name} (单位: km²)")
                log('crop_details', f"水文年类型: {hydrological_year}%")
            
            # 遍历该区域的每种作物
            for crop_name, planted_area in crop_area.crop_areas.items():
                # 获取作物
                crop = self.crop_registry.get_crop(crop_name)
                if not crop:
                    # 对于水稻类作物（在旱地模式下），完全不显示提示
                    if crop_name not in ['单季稻', '双季稻']:
                        log('warnings', f"警告: 未找到作物 {crop_name}")
                    continue
                
                # 获取单位面积需水量
                daily_water = crop.get_daily_water(hydrological_year)
                
                # 计算需水量 (mm/d * km²)
                water_mm_km2 = daily_water * planted_area
                
                # 仅在crop_details日志级别开启时输出详细计算过程
                if LOG_CONFIG['levels'].get('crop_details', False):
                    log('crop_details', 
                        f"- {crop_name}: {planted_area:.2f} km² * "
                        f"{daily_water:.6f} mm/d = {water_mm_km2:.6f} mm*km²/d"
                    )
                
                # 转换单位: mm/d * km² -> m³/d
                water_m3 = crop.calculate_water_volume(planted_area, hydrological_year)
                
                # 存储计算结果
                if crop_name not in self.crop_water_data:
                    self.crop_water_data[crop_name] = {}
                self.crop_water_data[crop_name][area_name] = water_m3
        
        return self.crop_water_data

    def calculate_daily_water(self, area: Any, current_time: datetime) -> float:
        """
        计算指定灌区当天的总需水量
        
        参数:
            area: 灌区对象
            current_time: 当前时间
        
        返回:
            总需水量 (立方米/日)
        """
        # 获取该区域的作物种植情况
        if area.name not in self.area_manager.crop_areas:
            return 0.0
            
        crop_area = self.area_manager.crop_areas[area.name]
        
        # 计算当天所有作物的总需水量
        daily_total_water = 0.0
        
        for crop_name, planted_area in crop_area.crop_areas.items():
            # 获取作物
            crop = self.crop_registry.get_crop(crop_name)
            if not crop:
                continue
            
            # 获取水文年类型
            hydrological_year = crop_area.hydrological_year
            
            # 计算需水量
            crop_water = crop.calculate_water_volume(planted_area, hydrological_year)
            daily_total_water += crop_water
        
        # 输出调试信息
        if self.verbose and LOG_CONFIG['levels'].get('calculation', False):
            log('calculation', 
                f"区域 {area.name} 当天总需水量: {daily_total_water:.2f} m³/d"
            )
        
        return daily_total_water
    
    def apply_to_irrigation_areas(
            self, 
            areas: List[Any], 
            time_range: pd.DatetimeIndex
        ) -> None:
        """
        将计算结果应用到灌区对象
        
        参数:
            areas: 灌区对象列表
            time_range: 时间范围
        """
        log('calculation', "\n=== 应用作物需水计算结果 ===")
        
        # 遍历每个灌区
        for area in areas:
            if LOG_CONFIG['levels'].get('calculation', False):
                log('calculation', f"\n计算区域: {area.name}")
            
            # 遍历时间范围内的每一天
            for current in time_range:
                # 计算当天的总需水量
                daily_total_water = self.calculate_daily_water(area, current)
                
                # 保存到灌区结果中
                area.results['single_crop_irrigation'][current] = daily_total_water
                
                # 只在启用相应日志级别时输出详细信息
                if LOG_CONFIG['levels'].get('crop_details', False):
                    log('crop_details',
                        f"{current.strftime('%Y-%m-%d')}: {daily_total_water/10000:.4f} 万m³/d"
                    )


# ============================================================================
# 旱地作物模拟器
# ============================================================================

class CropSimulator(SimulationBase):
    """
    旱地作物模拟器，计算旱地作物需水量的主要类
    """
    
    def __init__(self, simulation_engine):
        """
        初始化旱地作物模拟器
        
        参数:
            simulation_engine: 模拟引擎实例
        """
        super().__init__(simulation_engine)
        
        # 创建模型组件
        self.crop_registry = CropRegistry()
        self.area_manager = AreaManager()
        self.water_calculator = WaterRequirementCalculator(
            self.crop_registry,
            self.area_manager
        )
        
        # 设置调试输出
        self.water_calculator.set_verbose(self.verbose)
        
        # 记录数据文件路径
        self.crop_file = None
        self.dry_area_file = None
        self.fenqu_file = None
    
    def initialize(self, crop_file: str, dry_area_file: str, fenqu_file: str):
        """
        初始化作物数据
        
        参数:
            crop_file: 作物数据文件路径
            dry_area_file: 旱地作物面积文件路径
            fenqu_file: 分区数据文件路径
        """
        self.crop_file = crop_file
        self.dry_area_file = dry_area_file
        self.fenqu_file = fenqu_file
        
        try:
            # 加载作物数据
            self.crop_registry.load_from_file(crop_file)
        except Exception as e:
            log('errors', f"读取作物数据文件失败: {str(e)}")
        
        try:
            # 加载区域面积限制
            self.area_manager.load_area_limits_from_file(fenqu_file)
        except Exception as e:
            log('errors', f"读取分区面积限制文件失败: {str(e)}")
        
        try:
            # 加载区域作物种植面积
            self.area_manager.load_crop_areas_from_file(dry_area_file)
        except Exception as e:
            log('errors', f"读取作物种植面积文件失败: {str(e)}")
    
    def run(self):
        """
        执行作物需水计算
        """
        # 验证数据
        self._validate_data()
        
        # 验证种植面积
        self.area_manager.validate_areas(
            verbose=LOG_CONFIG['levels'].get('area_processing', False)
        )
        
        # 计算作物需水量
        self.water_calculator.calculate_water_requirements()
        
        # 计算每个灌区每一天的需水量，并应用到结果
        self.water_calculator.apply_to_irrigation_areas(
            self.simulation_engine.irrigation_manager.irrigation_areas,
            self._get_time_range()
        )


__all__ = [
    'Crop',
    'CropRegistry',
    'AreaLimits',
    'CropArea',
    'AreaManager',
    'WaterRequirementCalculator',
    'CropSimulator'
] 