import os
import time
import sys
import argparse

# 定义文件复制函数
def copy_files_to_root():
    """将结果文件复制到根目录"""
    import shutil
    import os
    
    print("\n=== 复制文件到根目录 ===")
    
    # 定义需要复制的文件
    files_to_copy = [
        'OUT_PYCS_TOTAL.txt',
        'OUT_GGXS_TOTAL.txt'
    ]
    
    # 源目录
    source_dir = 'data'
    
    for filename in files_to_copy:
        source_path = os.path.join(source_dir, filename)
        dest_path = filename
        
        try:
            if os.path.exists(source_path):
                shutil.copy2(source_path, dest_path)
                print(f"复制: {filename}")
            elif os.path.exists(dest_path):
                print(f"文件已存在: {filename}")
            else:
                print(f"源文件不存在: {source_path}")
        except Exception as e:
            print(f"复制 {filename} 失败: {e}")
    
    print("文件复制完成")

# 添加当前目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# 导入重构后的模块
try:
    from .calculator import Calculator
except ImportError as e:
    print(f"导入Calculator失败: {e}")
    sys.exit(1)

from .utils import combine_results
from .config import (
    CALCULATION_MODE, OUTPUT_DIR,
    MODE_OUTPUT_FILES, CROP_WATER_BALANCE_FILES, CROP_IRRIGATION_FILES,
    TOTAL_OUTPUT_FILES, INPUT_FILES, LOG_CONFIG,
    is_b3_mode, set_b3_mode
)

def setup_logging(args):
    """设置日志级别"""
    # 根据命令行参数设置日志级别
    if args.quiet:
        # 安静模式，仅输出错误
        LOG_CONFIG['enabled'] = True
        for key in LOG_CONFIG['levels']:
            LOG_CONFIG['levels'][key] = False
        LOG_CONFIG['levels']['errors'] = True
    elif args.verbose:
        # 详细模式，输出所有信息
        LOG_CONFIG['enabled'] = True
        for key in LOG_CONFIG['levels']:
            LOG_CONFIG['levels'][key] = True
        LOG_CONFIG['verbose'] = True
    else:
        # 自定义特定的日志级别
        if args.log_levels:
            for level in args.log_levels:
                if level in LOG_CONFIG['levels']:
                    LOG_CONFIG['levels'][level] = True
    
    # 调试模式
    if args.debug:
        LOG_CONFIG['verbose'] = True
        LOG_CONFIG['levels']['file_io'] = True
        LOG_CONFIG['levels']['errors'] = True
        LOG_CONFIG['levels']['warnings'] = True

def check_required_files():
    """检查必要的输入文件是否存在"""
    from .utils import read_data_file
    from .config import log
    
    log('file_io', "\n=== 检查必要文件 ===")
    required_files = [
        'time_config',     # 时间配置
        'area_config',     # 区域配置
        'fenqu'            # 分区数据
    ]
    
    if CALCULATION_MODE in ["crop", "both"]:
        required_files.extend(['crop', 'dry_area'])
    
    missing_files = []
    for key in required_files:
        file_name = INPUT_FILES[key]
        try:
            # 仅检查文件是否可读
            read_data_file(file_name, debug=LOG_CONFIG['levels'].get('file_io', False))
            log('file_io', f"✓ {file_name} - 已找到")
        except SystemExit:
            missing_files.append(file_name)
    
    if missing_files:
        log('errors', "\n警告: 以下必要文件未找到:")
        for file in missing_files:
            log('errors', f"  - {file}")
        log('errors', "\n请确保这些文件在正确的位置，否则程序可能无法正常工作。")
        return False
    
    log('file_io', "所有必要文件已找到")
    return True

def print_calculator_info(calculator):
    # 使用更清晰的模式名称
    mode_display_names = {
        "crop": "旱地作物(dryland)",
        "irrigation": "水稻灌溉(paddy)",
        "both": "综合(both)"
    }
    display_mode = mode_display_names.get(CALCULATION_MODE, CALCULATION_MODE)
    
    print(f"\n计算器信息:")
    print(f"- 使用重构模块: 是")
    print(f"- 灌区数量: {len(calculator.irrigation_manager.irrigation_areas)}")
    print(f"- 灌溉系统: {list(calculator.irrigation_manager.irrigation_systems.keys())}")
    print(f"- 计算模式: {display_mode}")
    print(f"- 计算起始时间: {calculator.current_time}")
    print(f"- 预测天数: {calculator.forecast_days}")

def run_mode(calculator, mode_name):
    # 使用更清晰的模式名称
    mode_display_names = {
        "crop": "旱地作物(dryland)",
        "irrigation": "水稻灌溉(paddy)",
        "both": "综合(both)"
    }
    display_name = mode_display_names.get(mode_name, mode_name)
    
    print(f"\n=== 执行{display_name}模式计算 ===")
    calculator.set_mode(
        mode_name,
        MODE_OUTPUT_FILES[mode_name]['irrigation'],
        MODE_OUTPUT_FILES[mode_name]['drainage']
    )
    calculator.run_calculation()
    # 不使用 return_data=True，确保文件被保存
    results = calculator.export_results(return_data=False)
    # 同时返回数据以便合并
    results = calculator.export_results(return_data=True)
    print(f"{display_name}模式计算完成")
    return results


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='农田灌溉需水计算系统')
    
    # 添加数据目录参数
    parser.add_argument('data_dir', nargs='?', default=None,
                      help='数据目录路径，如不提供则使用当前目录')
    
    # B3 模式参数
    b3_group = parser.add_argument_group('B3 NC数据模式')
    b3_group.add_argument('--b3', dest='b3_mode', action='store_true',
                         help='启用 B3 NC 数据格式模式')
    b3_group.add_argument('--year', type=int, default=None,
                         help='B3 数据年份（可选，默认自动检测）')
    
    # 日志控制
    log_group = parser.add_argument_group('日志控制')
    log_group.add_argument('-q', '--quiet', action='store_true', help='安静模式，只显示错误信息')
    log_group.add_argument('-v', '--verbose', action='store_true', help='详细模式，显示所有调试信息')
    log_group.add_argument('-d', '--debug', action='store_true', help='调试模式')
    log_group.add_argument('--log-levels', nargs='+', choices=list(LOG_CONFIG['levels'].keys()),
                         help='启用特定的日志级别 (可指定多个)')
    
    return parser.parse_args()

def run_b3_mode(data_path: str, year: int = None, verbose: bool = False):
    """
    运行 B3 NC 数据模式
    
    参数:
        data_path: NC 文件目录
        year: 数据年份（可选）
        verbose: 是否输出详细信息
    """
    from .nc_adapter import NCDataAdapter
    
    print("\n=== B3 NC 数据模式 ===")
    
    # 创建适配器并显示摘要
    adapter = NCDataAdapter(data_path, year)
    adapter.print_summary()
    
    # 使用 Calculator 加载数据
    print("\n=== 初始化计算器 ===")
    calculator = Calculator(data_path, verbose=verbose)
    calculator.load_data()
    
    print(f"\n计算器信息:")
    print(f"  - 灌区数量: {len(calculator.irrigation_manager.irrigation_areas)}")
    print(f"  - 起始时间: {calculator.current_time}")
    print(f"  - 计算天数: {calculator.forecast_days}")
    
    # 获取模型数据用于对比
    model_data = adapter.to_model_format()
    print(f"  - 作物面积: {model_data['crop_areas']}")
    
    # 尝试运行灌溉模式计算
    try:
        print("\n=== 执行水稻灌溉计算 ===")
        calculator.set_mode(
            'irrigation',
            'OUT_GGXS_B3.txt',
            'OUT_PYCS_B3.txt'
        )
        calculator.run_calculation()
        results = calculator.export_results(return_data=True)
        print("✅ 水稻灌溉计算完成")
        
        # 计算总量
        total_irrigation = sum(
            sum(row.get(col, 0) for col in row if col != '日期')
            for row in results['irrigation'].values()
        )
        print(f"总灌溉需水量: {total_irrigation:.2f}")
        
    except Exception as e:
        print(f"⚠️ 计算过程出现问题: {e}")
        import traceback
        if verbose:
            traceback.print_exc()
    
    return model_data


def main():
    # 解析命令行参数
    args = parse_args()
    setup_logging(args)
    
    try:
        start_time = time.time()
        print("\n=== 开始执行灌溉计算 ===")
        
        # 获取数据目录
        data_path = args.data_dir if args.data_dir else os.getcwd()
        print(f"使用数据目录: {data_path}")
        
        if not os.path.exists(data_path):
            print(f"错误: 找不到数据目录 {data_path}")
            return
        
        # B3 NC 数据模式
        if args.b3_mode:
            set_b3_mode(data_path, args.year)
            run_b3_mode(data_path, args.year, LOG_CONFIG['verbose'])
            end_time = time.time()
            print(f"\n=== B3 模式完成! 总耗时: {end_time - start_time:.2f} 秒 ===")
            return
            
        # 将当前工作目录设置为数据目录，这样文件读写都会在正确的目录
        if args.data_dir:
            print(f"切换工作目录到: {data_path}")
            os.chdir(data_path)
        
        # 检查必要文件
        if not check_required_files():
            print("\n警告: 缺少部分必要文件，但尝试继续执行...")
            
        # 启用详细输出以便调试
        verbose = LOG_CONFIG['verbose']
        calculator = Calculator(data_path, verbose=verbose)
        print("\n1. 初始化计算器完成")
        
        # 先加载数据，再打印信息，以便显示正确的时间和预测天数
        calculator.load_data()
        print_calculator_info(calculator)
        
        if CALCULATION_MODE in ["crop", "irrigation"]:
            run_mode(calculator, CALCULATION_MODE)
        else:
            crop_results = run_mode(calculator, "crop")
            irrigation_results = run_mode(calculator, "irrigation")
            print("\n=== 合并计算结果 ===")
            ggxs_total, pycs_total = combine_results(
                data_path,
                crop_results['irrigation'],
                irrigation_results['irrigation'],
                crop_results['drainage'],
                irrigation_results['drainage']
            )
            print(f"总灌溉需水量: {ggxs_total:.6f}")
            print(f"总排水量: {pycs_total:.6f}")
            print("结果合并完成")
        end_time = time.time()
        print(f"\n=== 计算完成! 总耗时: {end_time - start_time:.2f} 秒 ===")
    except Exception as e:
        print(f"\n发生错误: {str(e)}")
        print("\n详细错误信息:")
        import traceback
        print(traceback.format_exc())
    finally:
        copy_files_to_root()

if __name__ == "__main__":
    main()