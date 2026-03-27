import pandas as pd
from datetime import datetime
from abc import ABC, abstractmethod

class SimulationBase(ABC):
    """
    模拟计算的基类，为所有水文模拟模块提供基础功能
    """
    
    def __init__(self, simulation_engine):
        """
        初始化模拟基类
        
        参数:
            simulation_engine: 模拟引擎实例，提供全局配置和数据
        """
        self.simulation_engine = simulation_engine
        
        
        self.verbose = getattr(simulation_engine, 'verbose', False)
    
    @abstractmethod
    def run(self):
        """执行模拟计算，需要由子类实现"""
        pass
    
    def _validate_data(self):
        """验证灌区数据是否已初始化"""
        # 获取灌区数据
        if hasattr(self.simulation_engine, 'irrigation_manager'):
            areas = self.simulation_engine.irrigation_manager.irrigation_areas
        else:
            areas = getattr(self.simulation_engine, 'irrigation_areas', [])
        if not areas:
            raise ValueError("灌区数据未初始化")
    
    def _get_time_range(self):
        """获取模拟计算的时间范围"""
        # 兼容旧属性名
        engine = self.simulation_engine
        start_time = pd.Timestamp(engine.current_time)
        end_time = start_time + pd.Timedelta(days=engine.forecast_days)
        return pd.date_range(start_time, end_time, freq='D')
    
    def _print_debug(self, message):
        """打印调试信息"""
        if self.verbose:
            print(message)

