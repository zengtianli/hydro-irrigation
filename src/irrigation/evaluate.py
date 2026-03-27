#!/usr/bin/env python3
"""
灌溉需水模型评估脚本

功能：
1. 计算模型输出与实际数据的误差
2. 生成逐旬误差报告
3. 可视化对比图表
4. 多年验证，检测过拟合

使用：
    python evaluate.py --year 2020
    python evaluate.py --all
"""

import argparse
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'STHeiti']
plt.rcParams['axes.unicode_minus'] = False

# 数据路径配置
BASE_DIR = Path(__file__).parent.parent
B3_DATA_DIR = BASE_DIR / "灌溉模型B3案例数据" / "B3_案例数据"

# 年份与数据目录映射
YEAR_CONFIG = {
    2020: B3_DATA_DIR / "建模数据" / "NC数据输入输出格式",
    2021: B3_DATA_DIR / "率定数据" / "NC输入输出数据格式",
    2022: B3_DATA_DIR / "率定数据" / "NC输入输出数据格式",
    2024: B3_DATA_DIR / "率定数据" / "NC输入输出数据格式",
    2025: B3_DATA_DIR / "率定数据" / "NC输入输出数据格式",
}

# 数据集划分
TRAIN_YEARS = [2020, 2021, 2022]  # 训练集
VAL_YEARS = [2024, 2025]          # 验证集


def load_actual_data(year: int) -> pd.Series:
    """加载实际灌溉量数据"""
    nc_dir = YEAR_CONFIG.get(year)
    if not nc_dir:
        raise ValueError(f"未配置年份 {year} 的数据路径")
    
    nc_file = nc_dir / f"output_{year}.nc"
    if not nc_file.exists():
        raise FileNotFoundError(f"找不到文件: {nc_file}")
    
    ds = xr.open_dataset(nc_file)
    
    # 获取时间范围
    start_date = pd.Timestamp(ds.attrs['BGTM'])
    end_date = pd.Timestamp(ds.attrs['EDTM'])
    
    # 创建时间索引
    dates = pd.date_range(start_date, end_date, freq='D')
    
    # 获取数据（单位：m³）
    values = ds['IRRIGATION_WATER'].values
    
    ds.close()
    
    return pd.Series(values, index=dates, name='actual')


def run_model_and_get_output(year: int) -> pd.Series:
    """运行模型并获取输出"""
    nc_dir = YEAR_CONFIG.get(year)
    if not nc_dir:
        raise ValueError(f"未配置年份 {year}")
    
    # 运行模型
    cmd = [
        sys.executable, 
        str(Path(__file__).parent / "main.py"),
        "--b3", str(nc_dir),
        "--year", str(year)
    ]
    
    print(f"  运行模型: python main.py --b3 ... --year {year}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"  模型运行失败: {result.stderr}")
        raise RuntimeError(f"模型运行失败: {result.stderr}")
    
    # 立即读取输出
    output_file = Path(__file__).parent / "data" / "irrigation_single_crop.txt"
    if not output_file.exists():
        raise FileNotFoundError(f"找不到输出文件: {output_file}")
    
    df = pd.read_csv(output_file, sep='\t')
    df['日期'] = pd.to_datetime(df['日期'])
    df = df.set_index('日期')
    
    # 获取灌区列
    col = df.columns[0]
    
    # 模型输出单位是万m³，转为m³
    values = df[col].values * 10000
    
    return pd.Series(values, index=df.index, name='model')


def calculate_dekad(date: pd.Timestamp) -> str:
    """计算日期所属的旬"""
    month = date.month
    day = date.day
    
    if day <= 10:
        dekad = "上旬"
    elif day <= 20:
        dekad = "中旬"
    else:
        dekad = "下旬"
    
    return f"{month}月{dekad}"


def aggregate_to_dekad(series: pd.Series) -> pd.Series:
    """将逐日数据聚合为逐旬数据"""
    df = pd.DataFrame({'value': series})
    df['dekad'] = df.index.map(calculate_dekad)
    
    # 按旬聚合
    result = df.groupby('dekad', sort=False)['value'].sum()
    
    # 重新排序
    months = series.index.month.unique()
    ordered_dekads = []
    for m in sorted(months):
        for d in ['上旬', '中旬', '下旬']:
            dekad_name = f"{m}月{d}"
            if dekad_name in result.index:
                ordered_dekads.append(dekad_name)
    
    return result.reindex(ordered_dekads)


def calculate_errors(actual: pd.Series, model: pd.Series) -> dict:
    """计算各项误差指标"""
    # 对齐数据
    common_idx = actual.index.intersection(model.index)
    actual = actual.loc[common_idx]
    model = model.loc[common_idx]
    
    # 总量误差
    total_actual = actual.sum()
    total_model = model.sum()
    
    if total_actual > 0:
        total_error = abs(total_model - total_actual) / total_actual * 100
    else:
        total_error = float('nan')
    
    # 逐旬误差
    actual_dekad = aggregate_to_dekad(actual)
    model_dekad = aggregate_to_dekad(model)
    
    dekad_errors = {}
    for dekad in actual_dekad.index:
        if dekad in model_dekad.index and actual_dekad[dekad] > 0:
            err = abs(model_dekad[dekad] - actual_dekad[dekad]) / actual_dekad[dekad] * 100
            dekad_errors[dekad] = err
        elif actual_dekad[dekad] == 0 and model_dekad.get(dekad, 0) == 0:
            dekad_errors[dekad] = 0
        else:
            dekad_errors[dekad] = 100.0
    
    max_dekad_error = max(dekad_errors.values()) if dekad_errors else 0
    
    is_pass = (not np.isnan(total_error) and total_error <= 25 and max_dekad_error <= 25)
    
    return {
        'total_actual': total_actual / 10000,  # 转万m³
        'total_model': total_model / 10000,
        'total_error': total_error,
        'max_dekad_error': max_dekad_error,
        'dekad_errors': dekad_errors,
        'actual_dekad': actual_dekad / 10000,
        'model_dekad': model_dekad / 10000,
        'actual_daily': actual,
        'model_daily': model,
        'pass': is_pass
    }


def plot_comparison(results: dict, year: int, output_dir: Path):
    """生成对比可视化图表"""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f'{year}年 灌溉需水模型评估', fontsize=14, fontweight='bold')
    
    # 1. 逐日时间序列对比
    ax1 = axes[0, 0]
    actual_daily = results['actual_daily'] / 10000  # 转万m³
    model_daily = results['model_daily'] / 10000
    
    ax1.plot(actual_daily.index, actual_daily.values, 'b-', label='实际值', alpha=0.7, linewidth=1)
    ax1.plot(model_daily.index, model_daily.values, 'r--', label='模型值', alpha=0.7, linewidth=1)
    ax1.set_xlabel('日期')
    ax1.set_ylabel('灌溉量 (万m³)')
    ax1.set_title('逐日灌溉量对比')
    ax1.legend()
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    ax1.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)
    ax1.grid(True, alpha=0.3)
    
    # 2. 逐旬误差柱状图
    ax2 = axes[0, 1]
    dekad_errors = results['dekad_errors']
    x = range(len(dekad_errors))
    colors = ['green' if e <= 25 else 'orange' if e <= 50 else 'red' for e in dekad_errors.values()]
    
    bars = ax2.bar(x, dekad_errors.values(), color=colors, alpha=0.7)
    ax2.axhline(y=25, color='green', linestyle='--', label='合格线 (25%)', linewidth=2)
    ax2.set_xticks(x)
    ax2.set_xticklabels(dekad_errors.keys(), rotation=45, ha='right')
    ax2.set_ylabel('误差 (%)')
    ax2.set_title(f'逐旬误差分布 (最大: {results["max_dekad_error"]:.1f}%)')
    ax2.legend()
    ax2.grid(True, alpha=0.3, axis='y')
    
    # 3. 逐旬对比柱状图
    ax3 = axes[1, 0]
    actual_dekad = results['actual_dekad']
    model_dekad = results['model_dekad']
    
    x = np.arange(len(actual_dekad))
    width = 0.35
    
    ax3.bar(x - width/2, actual_dekad.values, width, label='实际值', color='blue', alpha=0.7)
    ax3.bar(x + width/2, model_dekad.values, width, label='模型值', color='red', alpha=0.7)
    ax3.set_xticks(x)
    ax3.set_xticklabels(actual_dekad.index, rotation=45, ha='right')
    ax3.set_ylabel('灌溉量 (万m³)')
    ax3.set_title('逐旬灌溉量对比')
    ax3.legend()
    ax3.grid(True, alpha=0.3, axis='y')
    
    # 4. 散点图：模型 vs 实际
    ax4 = axes[1, 1]
    ax4.scatter(actual_daily.values, model_daily.values, alpha=0.5, s=20, c='blue')
    
    # 添加 y=x 参考线
    max_val = max(actual_daily.max(), model_daily.max()) * 1.1
    ax4.plot([0, max_val], [0, max_val], 'k--', label='y=x (理想)', alpha=0.7)
    
    # 添加误差带
    ax4.fill_between([0, max_val], [0, max_val*0.75], [0, max_val*1.25], 
                     alpha=0.1, color='green', label='±25%误差带')
    
    ax4.set_xlabel('实际灌溉量 (万m³)')
    ax4.set_ylabel('模型灌溉量 (万m³)')
    ax4.set_title(f'模型值 vs 实际值 (总量误差: {results["total_error"]:.1f}%)')
    ax4.legend()
    ax4.set_xlim(0, max_val)
    ax4.set_ylim(0, max_val)
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # 保存图表
    output_file = output_dir / f"evaluation_{year}.png"
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"  图表已保存: {output_file}")
    
    plt.close()


def plot_multi_year_heatmap(all_results: dict, output_dir: Path):
    """生成多年误差热力图"""
    # 收集所有旬的误差数据
    all_dekads = set()
    for results in all_results.values():
        all_dekads.update(results['dekad_errors'].keys())
    
    # 排序旬
    def dekad_sort_key(d):
        month = int(d.split('月')[0])
        dekad = d.split('月')[1]
        dekad_num = {'上旬': 0, '中旬': 1, '下旬': 2}[dekad]
        return (month, dekad_num)
    
    sorted_dekads = sorted(all_dekads, key=dekad_sort_key)
    years = sorted(all_results.keys())
    
    # 构建数据矩阵
    data = []
    for dekad in sorted_dekads:
        row = []
        for year in years:
            err = all_results[year]['dekad_errors'].get(dekad, np.nan)
            row.append(err)
        data.append(row)
    
    data = np.array(data)
    
    # 绘制热力图
    fig, ax = plt.subplots(figsize=(12, 10))
    
    im = ax.imshow(data, cmap='RdYlGn_r', aspect='auto', vmin=0, vmax=100)
    
    ax.set_xticks(range(len(years)))
    ax.set_xticklabels([f'{y}\n{"验证" if y in VAL_YEARS else "训练"}' for y in years])
    ax.set_yticks(range(len(sorted_dekads)))
    ax.set_yticklabels(sorted_dekads)
    
    # 添加数值标注
    for i in range(len(sorted_dekads)):
        for j in range(len(years)):
            val = data[i, j]
            if not np.isnan(val):
                color = 'white' if val > 50 else 'black'
                ax.text(j, i, f'{val:.0f}%', ha='center', va='center', color=color, fontsize=9)
    
    ax.set_xlabel('年份')
    ax.set_ylabel('旬')
    ax.set_title('多年逐旬误差热力图\n(绿色≤25%合格, 黄色25-50%, 红色>50%)')
    
    # 添加颜色条
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label('误差 (%)')
    
    plt.tight_layout()
    
    output_file = output_dir / "evaluation_heatmap.png"
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"热力图已保存: {output_file}")
    
    plt.close()


def plot_summary_chart(all_results: dict, output_dir: Path):
    """生成总结图表"""
    years = sorted(all_results.keys())
    
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    
    # 1. 总量误差对比
    ax1 = axes[0]
    total_errors = [all_results[y]['total_error'] for y in years]
    colors = ['blue' if y in TRAIN_YEARS else 'orange' for y in years]
    
    bars = ax1.bar(range(len(years)), total_errors, color=colors, alpha=0.7)
    ax1.axhline(y=25, color='green', linestyle='--', label='合格线 (25%)', linewidth=2)
    ax1.set_xticks(range(len(years)))
    ax1.set_xticklabels(years)
    ax1.set_ylabel('总量误差 (%)')
    ax1.set_title('各年总量误差对比')
    ax1.legend()
    ax1.grid(True, alpha=0.3, axis='y')
    
    # 添加数值标注
    for i, (bar, err) in enumerate(zip(bars, total_errors)):
        if not np.isnan(err):
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                    f'{err:.1f}%', ha='center', va='bottom', fontsize=10)
    
    # 2. 最大旬误差对比
    ax2 = axes[1]
    max_errors = [all_results[y]['max_dekad_error'] for y in years]
    
    bars = ax2.bar(range(len(years)), max_errors, color=colors, alpha=0.7)
    ax2.axhline(y=25, color='green', linestyle='--', label='合格线 (25%)', linewidth=2)
    ax2.set_xticks(range(len(years)))
    ax2.set_xticklabels(years)
    ax2.set_ylabel('最大旬误差 (%)')
    ax2.set_title('各年最大旬误差对比')
    ax2.legend()
    ax2.grid(True, alpha=0.3, axis='y')
    
    # 添加图例说明
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='blue', alpha=0.7, label='训练集'),
        Patch(facecolor='orange', alpha=0.7, label='验证集'),
    ]
    ax2.legend(handles=legend_elements, loc='upper right')
    
    plt.tight_layout()
    
    output_file = output_dir / "evaluation_summary.png"
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"总结图表已保存: {output_file}")
    
    plt.close()


def print_report(results: dict, year: int):
    """打印评估报告"""
    print(f"\n{'='*60}")
    print(f"  {year}年 灌溉需水模型评估报告")
    print(f"{'='*60}")
    
    status = "✅ 合格" if results['pass'] else "❌ 不合格"
    print(f"\n总体评价: {status}")
    
    print(f"\n--- 总量对比 ---")
    print(f"实际总量: {results['total_actual']:,.0f} 万m³")
    print(f"模型总量: {results['total_model']:,.0f} 万m³")
    err_str = f"{results['total_error']:.1f}%" if not np.isnan(results['total_error']) else "N/A"
    err_status = '✅' if (not np.isnan(results['total_error']) and results['total_error'] <= 25) else '❌'
    print(f"总量误差: {err_str} {err_status}")
    
    print(f"\n--- 逐旬误差 ---")
    print(f"最大旬误差: {results['max_dekad_error']:.1f}% {'✅' if results['max_dekad_error'] <= 25 else '❌'}")
    
    print(f"\n{'旬':<10} {'实际(万m³)':<12} {'模型(万m³)':<12} {'误差':<10} {'状态':<6}")
    print("-" * 52)
    
    for dekad in results['actual_dekad'].index:
        actual = results['actual_dekad'][dekad]
        model = results['model_dekad'].get(dekad, 0)
        error = results['dekad_errors'].get(dekad, 0)
        status = "✅" if error <= 25 else "❌"
        print(f"{dekad:<10} {actual:>10,.0f} {model:>10,.0f} {error:>8.1f}% {status}")


def save_report_csv(all_results: dict, output_dir: Path):
    """保存 CSV 格式的误差报告"""
    # 逐旬误差报告
    rows = []
    for year in sorted(all_results.keys()):
        results = all_results[year]
        for dekad, error in results['dekad_errors'].items():
            rows.append({
                '年份': year,
                '数据集': '验证集' if year in VAL_YEARS else '训练集',
                '旬': dekad,
                '实际(万m³)': results['actual_dekad'].get(dekad, 0),
                '模型(万m³)': results['model_dekad'].get(dekad, 0),
                '误差(%)': error,
                '是否合格': '是' if error <= 25 else '否'
            })
    
    df = pd.DataFrame(rows)
    csv_file = output_dir / "evaluation_dekad_errors.csv"
    df.to_csv(csv_file, index=False, encoding='utf-8-sig')
    print(f"逐旬误差报告已保存: {csv_file}")
    
    # 年度汇总报告
    summary_rows = []
    for year in sorted(all_results.keys()):
        results = all_results[year]
        summary_rows.append({
            '年份': year,
            '数据集': '验证集' if year in VAL_YEARS else '训练集',
            '实际总量(万m³)': results['total_actual'],
            '模型总量(万m³)': results['total_model'],
            '总量误差(%)': results['total_error'],
            '最大旬误差(%)': results['max_dekad_error'],
            '是否合格': '是' if results['pass'] else '否'
        })
    
    df_summary = pd.DataFrame(summary_rows)
    csv_summary = output_dir / "evaluation_summary.csv"
    df_summary.to_csv(csv_summary, index=False, encoding='utf-8-sig')
    print(f"年度汇总报告已保存: {csv_summary}")


def main():
    parser = argparse.ArgumentParser(description='灌溉需水模型评估')
    parser.add_argument('--year', type=int, help='评估指定年份')
    parser.add_argument('--all', action='store_true', help='评估所有年份')
    parser.add_argument('--output', type=str, default='evaluation', help='输出目录')
    
    args = parser.parse_args()
    
    # 创建输出目录
    output_dir = Path(__file__).parent / args.output
    output_dir.mkdir(exist_ok=True)
    
    years = list(YEAR_CONFIG.keys()) if args.all else [args.year] if args.year else [2020]
    
    all_results = {}
    
    print("\n" + "="*60)
    print("  灌溉需水模型评估")
    print("="*60)
    
    for year in years:
        print(f"\n{'#'*60}")
        print(f"# 评估 {year} 年 {'(验证集)' if year in VAL_YEARS else '(训练集)'}")
        print(f"{'#'*60}")
        
        try:
            # 加载实际数据
            actual = load_actual_data(year)
            print(f"  实际数据: {len(actual)} 天, 总量 {actual.sum()/1e8:.2f} 亿m³")
            
            # 运行模型并获取输出
            model = run_model_and_get_output(year)
            print(f"  模型输出: {len(model)} 天, 总量 {model.sum()/1e8:.2f} 亿m³")
            
            # 计算误差
            results = calculate_errors(actual, model)
            all_results[year] = results
            
            # 打印报告
            print_report(results, year)
            
            # 生成图表
            plot_comparison(results, year, output_dir)
            
        except Exception as e:
            print(f"  评估 {year} 年时出错: {e}")
            import traceback
            traceback.print_exc()
    
    # 如果有多年数据，生成汇总
    if len(all_results) > 1:
        print(f"\n{'='*60}")
        print("  多年评估总结")
        print(f"{'='*60}")
        
        # 生成热力图
        plot_multi_year_heatmap(all_results, output_dir)
        
        # 生成总结图表
        plot_summary_chart(all_results, output_dir)
        
        # 保存 CSV 报告
        save_report_csv(all_results, output_dir)
        
        # 打印总结
        print(f"\n{'年份':<8} {'总量误差':<12} {'最大旬误差':<12} {'数据集':<8} {'状态':<6}")
        print("-" * 50)
        
        for year in sorted(all_results.keys()):
            r = all_results[year]
            dataset = "验证集" if year in VAL_YEARS else "训练集"
            status = "✅" if r['pass'] else "❌"
            err_str = f"{r['total_error']:.1f}%" if not np.isnan(r['total_error']) else "N/A"
            print(f"{year:<8} {err_str:>10} {r['max_dekad_error']:>10.1f}% {dataset:<8} {status}")
        
        # 过拟合检测
        train_errors = [all_results[y]['total_error'] for y in TRAIN_YEARS if y in all_results and not np.isnan(all_results[y]['total_error'])]
        val_errors = [all_results[y]['total_error'] for y in VAL_YEARS if y in all_results and not np.isnan(all_results[y]['total_error'])]
        
        if train_errors and val_errors:
            avg_train = np.mean(train_errors)
            avg_val = np.mean(val_errors)
            
            print(f"\n--- 过拟合检测 ---")
            print(f"训练集平均误差: {avg_train:.1f}%")
            print(f"验证集平均误差: {avg_val:.1f}%")
            
            if avg_val > avg_train * 1.5 and avg_val > 30:
                print("⚠️ 警告: 可能存在过拟合 (验证集误差明显高于训练集)")
            elif avg_train > 30 and avg_val > 30:
                print("⚠️ 警告: 模型欠拟合 (训练集和验证集误差都偏高)")
            elif avg_train <= 25 and avg_val <= 25:
                print("✅ 优秀: 训练集和验证集误差都在合格范围内")
            else:
                print("⚡ 需要进一步优化参数")
    
    print(f"\n所有结果已保存到: {output_dir}/")


if __name__ == "__main__":
    main()
