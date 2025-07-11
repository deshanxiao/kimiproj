from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import JSONResponse, FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
import subprocess
import os
import psutil
import sys
import base64
import io
import matplotlib.pyplot as plt
from contextlib import redirect_stdout
import time
from typing import Optional
from pathlib import Path
import asyncio
import ast
from multiprocessing import Process, Queue
import tempfile
import json

app = FastAPI()
FILES_DIR = Path("/sandbox/files")  # Directory for file uploads/downloads
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

import multiprocessing
multiprocessing.set_start_method('fork')

class LimitUploadSizeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_FILE_SIZE:
            return JSONResponse(status_code=413, content={"detail": f"File too large. Max size is {MAX_FILE_SIZE}"})
        return await call_next(request)

app.add_middleware(LimitUploadSizeMiddleware)

###############################
#    Process Management       #
###############################

@app.get("/{sessionid}/processes")
async def list_processes():
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        processes.append({
            "pid": proc.info['pid'],
            "name": proc.info['name'],
            "cmdline": proc.info['cmdline']
        })
    return {"processes": processes}

@app.post("/{sessionid}/process/kill/{pid}")
async def kill_process(pid: int):
    try:
        process = psutil.Process(pid)
        process.terminate()
        return {"message": f"Process {pid} terminated"}
    except psutil.NoSuchProcess:
        raise HTTPException(status_code=404, detail="Process not found")

###############################
#    File Management          #
###############################

@app.post("/{sessionid}/files/upload")
async def upload_file(file: UploadFile = File(...)):
    file_path = FILES_DIR / file.filename
    try:
        if file_path.exists():
            raise HTTPException(status_code=409, detail=f"File {file.filename} already exists")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("wb") as f:
            content = await file.read()
            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(status_code=413, detail="Uploaded file exceeds 10MB")
            f.write(content)
        return {"message": f"Uploaded file {file.filename}"}
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
    except HTTPException:
        raise
    except Exception as e:
        print("Failed to upload file due to " + str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/{sessionid}/files/delete/{filename}")
async def delete_file(filename: str):
    file_path = FILES_DIR / filename
    try:
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File {filename} not found")
        file_path.unlink()
        return {"message": f"Deleted file {filename}"}
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/{sessionid}/files/download/{filename}")
async def download_file(filename: str):
    file_path = FILES_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=file_path, filename=filename, media_type="application/octet-stream")

###############################
#    Code Execution           #
###############################

class CodeRequest(BaseModel):
    code: str
    timeout: int = 30  # Default timeout 30 seconds

import matplotlib
matplotlib.use('Agg')

def execute_python_in_process(code: str, result_queue: Queue):
    """Execute Python code in a subprocess with stdin closed."""
    try:
        sys.stdin.close()
        output = io.StringIO()
        globals_dict = {}
        with redirect_stdout(output):
            tree = ast.parse(code, mode='exec')
            if not tree.body:
                result_queue.put({"result": None, "output": output.getvalue(), "image": None})
                return

            if len(tree.body) > 1:
                exec(compile(ast.Module(tree.body[:-1], []), '<string>', 'exec'), globals_dict)

            last_node = tree.body[-1] if tree.body else None
            if isinstance(last_node, ast.Expr):
                last_line_code = code.splitlines()[-1]
                result = eval(last_line_code, globals_dict)
                globals_dict['result'] = result
            else:
                exec(code, globals_dict)

            image_base64 = None
            if plt.get_fignums():
                buf = io.BytesIO()
                plt.savefig(buf, format='png')
                buf.seek(0)
                image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                plt.close('all')

        result_queue.put({
            "result": globals_dict.get('result', None),
            "output": output.getvalue(),
            "image": image_base64
        })
    except SyntaxError as e:
        result_queue.put({"error": f"语法错误: {str(e)}", "status_code": 400})
    except ValueError as e:
        if "I/O operation on closed file" in str(e):
            result_queue.put({"error": "无法读取输入（标准输入已关闭）", "status_code": 400})
        else:
            result_queue.put({"error": f"执行错误: {str(e)}", "status_code": 400})
    except EOFError:
        result_queue.put({"error": "无法读取输入（标准输入已关闭）", "status_code": 400})
    except Exception as e:
        result_queue.put({"error": f"执行错误: {str(e)}", "status_code": 400})

def execute_nodejs_in_process(code: str, result_queue: Queue, timeout: int):
    """Execute Node.js code in a subprocess using vm2 sandbox."""
    try:
        sys.stdin.close()
        # Create a temporary file for the JavaScript code
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as temp_file:
            temp_file.write(code)
            temp_file_path = temp_file.name

        print(f"code is {code}")
        # Execute the code using sandbox.js
        try:
            result = subprocess.run(
                ["node", "sandbox.js", temp_file_path, str(timeout)],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            stdout = result.stdout
            stderr = result.stderr

            # Parse output
            captured_output = ""
            error = None
            image_base64 = None
            for line in stdout.splitlines():
                if line.startswith('__OUTPUT__:'):
                    captured_output = json.loads(line.replace('__OUTPUT__:', '')) or []
                    captured_output = '\n'.join(captured_output)
                elif line.startswith('__ERROR__:'):
                    error = json.loads(line.replace('__ERROR__:', ''))
                    error = f"{error['name']}: {error['message']}"

            # Check for Plotly image
            plot_path = "/tmp/plot.png"
            if os.path.exists(plot_path):
                with open(plot_path, "rb") as f:
                    image_base64 = base64.b64encode(f.read()).decode('utf-8')
                os.unlink(plot_path)

            if result.returncode != 0 or error:
                result_queue.put({"error": error or f"执行错误: {stderr}", "status_code": 400})
                return

            result_queue.put({
                "result": None,
                "output": captured_output,
                "image": image_base64
            })
        finally:
            pass
            # os.unlink(temp_file_path)  # Clean up temporary file
    except subprocess.TimeoutExpired:
        result_queue.put({"error": "代码执行超时", "status_code": 408})
    except Exception as e:
        result_queue.put({"error": f"执行错误: {str(e)}", "status_code": 400})

async def run_in_process(code: str, timeout: float, language: str = "python"):
    process = None
    try:
        result_queue = Queue()
        if language == "python":
            process = Process(target=execute_python_in_process, args=(code, result_queue))
        elif language == "javascript":
            process = Process(target=execute_nodejs_in_process, args=(code, result_queue, timeout))
        else:
            raise HTTPException(status_code=400, detail=f"不支持的语言: {language}")

        process.start()
        process.join(timeout)

        if process.is_alive():
            process.terminate()
            time.sleep(0.1)
            if process.is_alive():
                process.kill()
            raise asyncio.TimeoutError

        if not result_queue.empty():
            result = result_queue.get()
            if "error" in result:
                raise HTTPException(status_code=result["status_code"], detail=result["error"])
            return result
        else:
            raise HTTPException(status_code=500, detail="服务器内部错误: 无结果返回")
    finally:
        if process and process.is_alive():
            process.terminate()
            time.sleep(0.1)
            if process.is_alive():
                process.kill()
            process.close()

@app.post("/{sessionid}/exec/python")
async def execute_python(request: CodeRequest):
    print(f'timeout is {request.timeout}')
    try:
        result = await run_in_process(request.code, request.timeout, language="python")
        return result
    except asyncio.TimeoutError:
        raise HTTPException(status_code=408, detail="代码执行超时")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")

@app.post("/{sessionid}/exec/nodejs")
async def execute_nodejs(request: CodeRequest):
    print(f'timeout is {request.timeout}')
    try:
        result = await run_in_process(request.code, request.timeout, language="javascript")
        return result
    except asyncio.TimeoutError:
        raise HTTPException(status_code=408, detail="代码执行超时")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")