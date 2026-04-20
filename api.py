"""FastAPI wrapper for hydro-irrigation — unchanged Python core, no Streamlit.

Run:
    uv run uvicorn api:app --host 127.0.0.1 --port 8615 --reload

Input:  ZIP containing input_*.txt / in_*.txt / static_*.txt.
Output: ZIP containing OUT_GGXS_*.txt + OUT_PYCS_*.txt (+ water_balance_*.txt,
        irrigation_*_crop.txt auxiliaries written by ResultExporter).
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import tempfile
import time
import traceback
import zipfile
from pathlib import Path
from urllib.parse import quote

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

# Project root on sys.path so `from src.irrigation...` resolves like Streamlit.
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.irrigation.calculator import Calculator  # noqa: E402
from src.irrigation.utils import combine_results  # noqa: E402

app = FastAPI(title="hydro-irrigation-api", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3115",
        "http://127.0.0.1:3115",
        "https://hydro-irrigation.tianlizeng.cloud",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/meta")
def meta_info() -> dict:
    return {
        "name": "irrigation",
        "title": "灌溉需水",
        "icon": "🌾",
        "description": "水稻+旱地灌溉需水量水平衡计算",
        "version": "1.0.0",
    }


# Output files we ship back to the client. `combine_results` writes
# OUT_GGXS_TOTAL / OUT_PYCS_TOTAL into cwd/data/ for mode="both"; per-mode
# files land in data_path (same directory in our tmpdir layout).
_RESULT_GLOBS = (
    "OUT_*.txt",
    "water_balance_*.txt",
    "irrigation_*_crop.txt",
)


def _collect_outputs(output_dir: Path, dest_zip: zipfile.ZipFile, seen: set[str]) -> int:
    """Append matching files under `output_dir` (non-recursive) to dest_zip.
    Returns number of files added. `seen` de-dupes across calls."""
    added = 0
    for pattern in _RESULT_GLOBS:
        for f in sorted(output_dir.glob(pattern)):
            if not f.is_file():
                continue
            if f.name in seen:
                continue
            seen.add(f.name)
            dest_zip.writestr(f.name, f.read_bytes())
            added += 1
    return added


def _run_irrigation(
    zip_bytes: bytes, calc_mode: str, collect_full: bool = False
) -> tuple[bytes, dict]:
    """Port of app.py's "开始计算" button handler, Streamlit stripped.

    Layout:
        tmpdir/              ← cwd during calc (combine_results writes here/data/)
            data/            ← data_path; extracted input + generated OUT_*
    `Calculator` writes results to data_path and also to cwd/data/ (same dir).

    When ``collect_full`` is True the returned ``info`` additionally contains:
        input_files: [{name, size}]
        output_files_raw: {name: bytes}
    """
    if calc_mode not in {"crop", "irrigation", "both"}:
        raise HTTPException(400, f"calc_mode 必须是 crop/irrigation/both，收到: {calc_mode!r}")

    with tempfile.TemporaryDirectory() as tmpdir_raw:
        tmpdir = Path(tmpdir_raw)
        data_path = tmpdir / "data"
        data_path.mkdir()

        # Extract zip into data_path — flatten single top-level folder if any.
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                members = [m for m in zf.namelist() if not m.endswith("/")]
                if not members:
                    raise HTTPException(400, "ZIP 为空，没有可用文件")
                # Detect common prefix (single wrapping folder)
                first_parts = {m.split("/", 1)[0] for m in members if "/" in m}
                strip_prefix = None
                if len(first_parts) == 1 and all(
                    m.startswith(f"{next(iter(first_parts))}/") or "/" not in m
                    for m in members
                ):
                    strip_prefix = next(iter(first_parts))
                input_files: list[dict] = []
                for m in members:
                    name = m
                    if strip_prefix and m.startswith(f"{strip_prefix}/"):
                        name = m[len(strip_prefix) + 1 :]
                    if not name or name.startswith("__MACOSX"):
                        continue
                    flat_name = Path(name).name
                    target = data_path / flat_name  # flat — no nested dirs
                    data = zf.read(m)
                    target.write_bytes(data)
                    input_files.append({"name": flat_name, "size": len(data)})
        except zipfile.BadZipFile as e:
            raise HTTPException(400, f"ZIP 解压失败: {e}") from e

        txt_count = sum(1 for _ in data_path.glob("*.txt"))
        if txt_count == 0:
            raise HTTPException(400, "ZIP 中未找到 .txt 输入文件")

        # `combine_results` + `export_results` use os.getcwd()+"/data" as output
        # root — we chdir into tmpdir so cwd/data/ == data_path.
        original_cwd = os.getcwd()
        os.chdir(tmpdir)
        try:
            calc = Calculator(str(data_path), verbose=False)
            calc.load_data()

            info = {
                "start_time": str(calc.current_time),
                "forecast_days": int(calc.forecast_days),
                "num_areas": len(calc.irrigation_manager.irrigation_areas),
                "systems": list(calc.irrigation_manager.irrigation_systems.keys()),
                "calc_mode": calc_mode,
            }

            if calc_mode == "crop":
                calc.set_mode("crop", "OUT_GGXS_C.txt", "OUT_PYCS_C.txt")
                calc.run_calculation()
                calc.export_results(return_data=True)
            elif calc_mode == "irrigation":
                calc.set_mode("irrigation", "OUT_GGXS_I.txt", "OUT_PYCS_I.txt")
                calc.run_calculation()
                calc.export_results(return_data=True)
            else:  # both
                calc.set_mode("crop", "OUT_GGXS_C.txt", "OUT_PYCS_C.txt")
                calc.run_calculation()
                crop_results = calc.export_results(return_data=True)

                calc.set_mode("irrigation", "OUT_GGXS_I.txt", "OUT_PYCS_I.txt")
                calc.run_calculation()
                irr_results = calc.export_results(return_data=True)

                ggxs_total, pycs_total = combine_results(
                    str(data_path),
                    crop_results.get("irrigation", {}),
                    irr_results.get("irrigation", {}),
                    crop_results.get("drainage", {}),
                    irr_results.get("drainage", {}),
                )
                info["total_irrigation"] = float(ggxs_total)
                info["total_drainage"] = float(pycs_total)
        finally:
            os.chdir(original_cwd)

        # Collect outputs from both data_path and tmpdir/data (same dir in our
        # layout, but be defensive — combine_results uses cwd/data explicitly).
        buf = io.BytesIO()
        output_files_raw: dict[str, bytes] = {}
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out_zip:
            seen: set[str] = set()

            def _gather(src: Path) -> int:
                added = 0
                for pattern in _RESULT_GLOBS:
                    for f in sorted(src.glob(pattern)):
                        if not f.is_file() or f.name in seen:
                            continue
                        seen.add(f.name)
                        data = f.read_bytes()
                        out_zip.writestr(f.name, data)
                        if collect_full:
                            output_files_raw[f.name] = data
                        added += 1
                return added

            added = _gather(data_path)
            cwd_data = tmpdir / "data"
            if cwd_data.resolve() != data_path.resolve():
                added += _gather(cwd_data)
            if added == 0:
                raise HTTPException(500, "计算结束但没有生成任何 OUT_*.txt，可能输入格式有误")

        if collect_full:
            info["input_files"] = input_files
            info["output_files_raw"] = output_files_raw
        return buf.getvalue(), info


_TABLE_ROW_LIMIT = 500
_TEXT_PREVIEW_LINES = 50


def _txt_to_payload(name: str, data: bytes) -> dict:
    """Try to read a tab/whitespace-separated table; fall back to text preview.

    Returns one of:
        {"kind": "table", "columns": [...], "rows": [...], "totalRows": N}
        {"kind": "text",  "text": "first N lines…", "totalLines": N}
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = data.decode("gbk")
        except UnicodeDecodeError:
            text = data.decode("utf-8", errors="replace")

    # Try tab first (most output files), then whitespace.
    for sep in ("\t", r"\s+"):
        try:
            df = pd.read_csv(
                io.StringIO(text),
                sep=sep,
                engine="python",
                dtype=str,
                keep_default_na=False,
            )
            if df.shape[1] >= 2 and len(df) > 0:
                total = len(df)
                sliced = df.head(_TABLE_ROW_LIMIT) if total > _TABLE_ROW_LIMIT else df
                # Attempt numeric coercion column-wise for nicer display.
                for col in sliced.columns:
                    try:
                        coerced = pd.to_numeric(sliced[col])
                        sliced[col] = coerced
                    except (ValueError, TypeError):
                        pass
                parsed = json.loads(
                    sliced.to_json(orient="split", force_ascii=False)
                )
                return {
                    "kind": "table",
                    "columns": [str(c) for c in parsed["columns"]],
                    "rows": parsed["data"],
                    "totalRows": int(total),
                }
        except Exception:
            continue

    # Fall back to plain text preview.
    lines = text.splitlines()
    preview = "\n".join(lines[:_TEXT_PREVIEW_LINES])
    return {"kind": "text", "text": preview, "totalLines": len(lines)}


def _run_irrigation_full(zip_bytes: bytes, calc_mode: str) -> dict:
    """Run calc + build rich JSON payload (preview / meta / results / zipBase64)."""
    started = time.perf_counter()
    result_zip, info = _run_irrigation(zip_bytes, calc_mode, collect_full=True)
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    input_files = info.get("input_files", [])
    raw_outputs: dict[str, bytes] = info.get("output_files_raw", {})

    output_files_meta: list[dict] = []
    results_payload: dict[str, dict] = {}
    for name in sorted(raw_outputs.keys()):
        data = raw_outputs[name]
        results_payload[name] = _txt_to_payload(name, data)
        output_files_meta.append(
            {
                "name": name,
                "size": len(data),
                "type": "txt" if name.lower().endswith(".txt") else "bin",
            }
        )

    total_in_size = sum(f["size"] for f in input_files)

    meta_payload: dict = {
        "calcMode": info.get("calc_mode", calc_mode),
        "startTime": info.get("start_time"),
        "forecastDays": info.get("forecast_days"),
        "numAreas": info.get("num_areas"),
        "systems": info.get("systems", []),
        "elapsedMs": elapsed_ms,
        "zipBytes": len(result_zip),
    }
    if "total_irrigation" in info:
        meta_payload["totalIrrigation"] = info["total_irrigation"]
    if "total_drainage" in info:
        meta_payload["totalDrainage"] = info["total_drainage"]

    return {
        "preview": {
            "inputFiles": input_files,
            "fileCount": len(input_files),
            "totalSize": total_in_size,
        },
        "meta": meta_payload,
        "results": results_payload,
        "outputFiles": output_files_meta,
        "zipBase64": base64.b64encode(result_zip).decode("ascii"),
    }


@app.post("/api/compute")
async def compute(
    file: UploadFile = File(..., description="输入 ZIP — 含 in_*.txt/static_*.txt"),
    calc_mode: str = Form("both", description="crop / irrigation / both"),
    format: str = Form("zip", description="zip (binary) | json (preview+results+base64)"),
) -> Response:
    content = await file.read()
    if not content:
        raise HTTPException(400, "上传文件为空")

    try:
        if format == "json":
            payload = _run_irrigation_full(content, calc_mode)
            return JSONResponse(content=payload)
        zip_bytes, info = _run_irrigation(content, calc_mode)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            500,
            f"计算失败: {type(e).__name__}: {e}\n{traceback.format_exc()[-800:]}",
        )

    # Headers are latin-1; URL-encode any CJK content.
    headers = {
        "Content-Disposition": 'attachment; filename="irrigation_result.zip"',
        "X-Calc-Mode": quote(info.get("calc_mode", "")),
        "X-Start-Time": quote(info.get("start_time", "")),
        "X-Forecast-Days": str(info.get("forecast_days", "")),
        "X-Num-Areas": str(info.get("num_areas", "")),
        "X-Systems": quote(",".join(info.get("systems", []))),
        "Access-Control-Expose-Headers": (
            "X-Calc-Mode, X-Start-Time, X-Forecast-Days, X-Num-Areas, "
            "X-Systems, X-Total-Irrigation, X-Total-Drainage, Content-Disposition"
        ),
    }
    if "total_irrigation" in info:
        headers["X-Total-Irrigation"] = f"{info['total_irrigation']:.4f}"
    if "total_drainage" in info:
        headers["X-Total-Drainage"] = f"{info['total_drainage']:.4f}"

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers=headers,
    )


@app.get("/api/sample")
def sample_zip() -> Response:
    """Bundle repo's data/sample/*.txt as a ready-to-upload ZIP."""
    sample_dir = PROJECT_ROOT / "data" / "sample"
    if not sample_dir.exists():
        raise HTTPException(404, "示例数据目录不存在")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(sample_dir.glob("*.txt")):
            zf.write(f, arcname=f.name)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="irrigation_sample.zip"'},
    )
