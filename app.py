import logging
import json
import time
import os
import copy
from json import JSONDecodeError
from datetime import datetime, timedelta
from collections import deque
from threading import Lock

# 第三方库导入
from ruamel.yaml import YAML
import httpx
import contextvars
import traceback
import tiktoken
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, Response, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles


# =============================================================================
# 日志记录功能
# =============================================================================

def log_interaction(log_type: str, content: any) -> None:
    """记录API交互日志到文件，支持文件大小限制和日志轮转
    
    Args:
        log_type: 日志类型（REQUEST/RESPONSE）
        content: 日志内容，可以是字符串、字典或列表
        
    Features:
        - 单个文件最大5MB
        - 保留最近10个文件
    """
    log_dir = os.path.join(script_dir, 'log')
    os.makedirs(log_dir, exist_ok=True)
    base_log_file = 'agent_interactions.log'
    log_file = os.path.join(log_dir, base_log_file)
    max_file_size = 5 * 1024 * 1024  # 5MB
    max_backup_count = 10
    
    # 检查当前日志文件大小
    if os.path.exists(log_file) and os.path.getsize(log_file) >= max_file_size:
        # 执行日志轮转
        for i in range(max_backup_count - 1, 0, -1):
            old_file = os.path.join(log_dir, f'{base_log_file}.{i}')
            new_file = os.path.join(log_dir, f'{base_log_file}.{i + 1}')
            if os.path.exists(old_file):
                if i == max_backup_count - 1:
                    os.remove(old_file)  # 删除最旧的日志文件
                else:
                    os.rename(old_file, new_file)
        # 重命名当前日志文件
        if os.path.exists(log_file):
            os.rename(log_file, os.path.join(log_dir, f'{base_log_file}.1'))
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {log_type}\n")
        if isinstance(content, dict) or isinstance(content, list):
            f.write(json.dumps(content, ensure_ascii=False, indent=2))
        else:
            f.write(str(content))
        f.write("\n")
        f.write("----------\n" if log_type == "REQUEST" else "==========\n\n")


# =============================================================================
# 速率限制器类
# =============================================================================

class RateLimiter:
    """API速率限制器，支持RPM、TPM、RPD、TPR限制和错误计数限制"""
    
    def __init__(self):
        self.lock = Lock()
        self.counters = {}  # {api_provider: {'rpm': deque(), 'tpm': deque(), 'rpd': int}}
        self.error_counters = {}  # {api_provider: [(timestamp, error_count)]}
        
    def check_limit(self, api_provider, limits, token_count=0):
        """检查是否超出速率限制"""
        with self.lock:
            if api_provider not in self.counters:
                self.counters[api_provider] = {
                    'rpm': deque(),
                    'tpm': deque(),
                    'rpd': 0
                }
                
            now = datetime.now()
            counters = self.counters[api_provider]
            
            # 清理过期的分钟级记录
            while counters['rpm'] and (now - counters['rpm'][0][0]) > timedelta(minutes=1):
                counters['rpm'].popleft()
            while counters['tpm'] and (now - counters['tpm'][0][0]) > timedelta(minutes=1):
                counters['tpm'].popleft()
                
            # 检查RPM限制
            if 'rpm' in limits and len(counters['rpm']) >= limits['rpm']:
                return False, "RPM limit exceeded"
                
            # 检查TPM限制
            if 'tpm' in limits:
                current_tpm = sum(t for _, t in counters['tpm'])
                if current_tpm + token_count > limits['tpm']:
                    return False, "TPM limit exceeded"

            # 检查TPR限制
            if 'tpr' in limits and token_count > limits['tpr']:
                return False, f"Token per request limit exceeded: {token_count} > {limits['tpr']}"
                    
            # 检查RPD限制
            if 'rpd' in limits and counters['rpd'] >= limits['rpd']:
                return False, "RPD limit exceeded"
                
            return True, ""
            
    def increment(self, api_provider, token_count=0):
        """增加计数器"""
        with self.lock:
            now = datetime.now()
            self.counters[api_provider]['rpm'].append((now, 1))
            self.counters[api_provider]['tpm'].append((now, token_count))
            self.counters[api_provider]['rpd'] += 1
            
    def reset_daily_counts(self):
        """重置每日计数"""
        with self.lock:
            for api_provider in self.counters:
                self.counters[api_provider]['rpd'] = 0
                
    def increment_error(self, api_provider):
        """增加错误计数"""
        with self.lock:
            now = datetime.now()
            if api_provider not in self.error_counters:
                self.error_counters[api_provider] = []
            
            # 清理24小时前的记录
            cutoff_time = now - timedelta(hours=24)
            self.error_counters[api_provider] = [
                (timestamp, count) for timestamp, count in self.error_counters[api_provider]
                if timestamp > cutoff_time
            ]
            
            # 计算当前错误计数
            current_error_count = sum(count for _, count in self.error_counters[api_provider])
            
            # 添加新的错误记录（错误计数+1）
            self.error_counters[api_provider].append((now, 1))
            
            # 返回当前总错误数（用于调试）
            return current_error_count + 1
            
    def is_error_limited(self, api_provider):
        """检查是否在错误限制期间"""
        with self.lock:
            now = datetime.now()
            if api_provider not in self.error_counters or not self.error_counters[api_provider]:
                return False, 0  # 不在限制中，错误计数为0
            
            # 清理24小时前的记录
            cutoff_time = now - timedelta(hours=24)
            self.error_counters[api_provider] = [
                (timestamp, count) for timestamp, count in self.error_counters[api_provider]
                if timestamp > cutoff_time
            ]
            
            if not self.error_counters[api_provider]:
                return False, 0  # 不在限制中，错误计数为0
            
            # 计算当前错误计数
            current_error_count = sum(count for _, count in self.error_counters[api_provider])
            
            # 找到最新的错误时间
            latest_error_time = max(timestamp for timestamp, _ in self.error_counters[api_provider])
            
            # 计算限制结束时间（每次错误增加10分钟限制，最多24小时）
            limit_duration = min(current_error_count * 10, 24 * 60)  # 最多24小时（1440分钟）
            limit_end_time = latest_error_time + timedelta(minutes=limit_duration)
            
            # 检查是否仍在限制期间
            if now < limit_end_time:
                remaining_minutes = (limit_end_time - now).total_seconds() / 60
                return True, int(remaining_minutes)  # 在限制中，返回剩余分钟数
            
            return False, 0  # 不在限制中，错误计数为0
            
    def cleanup_error_counters(self):
        """清理过期的错误记录"""
        with self.lock:
            now = datetime.now()
            cutoff_time = now - timedelta(hours=24)
            
            for api_provider in list(self.error_counters.keys()):
                # 清理24小时前的记录
                self.error_counters[api_provider] = [
                    (timestamp, count) for timestamp, count in self.error_counters[api_provider]
                    if timestamp > cutoff_time
                ]
                
                # 如果没有记录了，删除这个提供商的条目
                if not self.error_counters[api_provider]:
                    del self.error_counters[api_provider]
                
    def get_usage_stats(self):
        """获取使用统计信息"""
        stats = {}
        now = datetime.now()
        
        with self.lock:
            for api_provider, counters in self.counters.items():
                # 计算RPM
                rpm_count = 0
                while counters['rpm'] and (now - counters['rpm'][0][0]) > timedelta(minutes=1):
                    counters['rpm'].popleft()
                rpm_count = len(counters['rpm'])
                
                # 计算TPM
                tpm_count = 0
                while counters['tpm'] and (now - counters['tpm'][0][0]) > timedelta(minutes=1):
                    counters['tpm'].popleft()
                tpm_count = sum(t for _, t in counters['tpm'])
                
                # 获取RPD
                rpd_count = counters['rpd']
                
                # 获取配置限制
                limits = API_PROVIDER.get(api_provider, {}).get('limits', {})
                
                stats[api_provider] = {
                    'rpm': {'current': rpm_count, 'limit': limits.get('rpm', 0)},
                    'tpm': {'current': tpm_count, 'limit': limits.get('tpm', 0)},
                    'rpd': {'current': rpd_count, 'limit': limits.get('rpd', 0)}
                }
        
        return {
            'data': stats,
            'timestamp': now.isoformat()
        }
    
    def reset_all_limits(self):
        """重置所有API提供商的速率限制计数器"""
        with self.lock:
            # 重置计数器
            for api_provider in self.counters:
                self.counters[api_provider] = {
                    'rpm': deque(),
                    'tpm': deque(),
                    'rpd': 0
                }
            
            # 重置错误计数器
            self.error_counters = {}
            
        return {"status": "success", "message": "All rate limits have been reset"}


# =============================================================================
# 应用配置和初始化
# =============================================================================

script_dir = os.path.dirname(os.path.abspath(__file__))

# 配置日志
# 创建日志目录
log_dir = os.path.join(script_dir, 'log')
os.makedirs(log_dir, exist_ok=True)

# 配置日志格式
log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 创建logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 创建文件处理器
file_handler = logging.FileHandler(os.path.join(log_dir, 'app.log'), encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(log_format)

# 创建控制台处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(log_format)

# 添加处理器到logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# 创建FastAPI应用
app = FastAPI()

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，生产环境应更严格
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有头部
)

# 常量定义
TRUNCATE_NUM = 100
TRUNKATE_NUM = 5

# 初始化速率限制器
rate_limiter = RateLimiter()

# 初始化定时任务
scheduler = BackgroundScheduler()
scheduler.add_job(rate_limiter.reset_daily_counts, 'cron', hour=0, minute=0)
scheduler.add_job(rate_limiter.cleanup_error_counters, 'interval', minutes=30)  # 每30分钟清理一次过期错误记录
scheduler.start()

# API 配置
config_lock = Lock()
yaml = YAML()
config_path = f"{script_dir}/config.yaml"

with open(config_path, 'r') as file:
    config = yaml.load(file)
API_PROVIDER = config['api_provider']
MODEL_CONFIG = config['model_config']

# 创建一个 context variable
log_display_cnt_var = contextvars.ContextVar("log_display_cnt", default=0)

# =============================================================================
# 请求处理函数
# =============================================================================

async def handle_streaming_request(api_provider: str, uri: str, request_headers: dict, request_body: dict, passthrough: bool = False):
    """处理流式请求"""
    log_display_cnt_var.set(0)  # 每次请求时重置计数器
    response_status = contextvars.ContextVar("response_status", default=200)  # 添加状态码上下文变量
    
    async def generate_stream_response():
        """生成流式响应"""
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                async with client.stream(
                    "POST",
                    f"{API_PROVIDER[api_provider]['base_url']}/{uri}",
                    headers=request_headers,
                    json=request_body
                ) as response:
                    
                    response_status.set(response.status_code)
                    # 立即检查响应状态码
                    if response.status_code >= 400:
                        error_content = await response.aread()
                        try:
                            error_body = json.loads(error_content)
                            if isinstance(error_body, dict):
                                error_detail = error_body
                            else:
                                error_detail = {"error": error_body}
                        except json.JSONDecodeError:
                            error_detail = {"error": error_content.decode('utf-8')}
                            
                        logger.error(f"Upstream error: {response.status_code} - {error_detail}")
                        # 增加错误计数
                        rate_limiter.increment_error(api_provider)
                        yield json.dumps(error_detail).encode()
                        return
                    
                    if passthrough:
                        # 直接透传内容，同时记录日志
                        full_response_for_log = ""
                        async for chunk in response.aiter_bytes():
                            full_response_for_log += chunk.decode('utf-8', errors='ignore')
                            yield chunk
                        log_interaction("RESPONSE", full_response_for_log)
                        return
                    
                    is_done = False
                    complete_content = ""
                    full_response_for_log = ""
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            full_response_for_log += chunk.decode('utf-8', errors='ignore')
                            log_display_cnt = log_display_cnt_var.get()
                            try:
                                chunk_str = chunk.decode('utf-8').rstrip('\n\n')
                            except UnicodeDecodeError as e:
                                logger.error(f"Failed to decode chunk: {chunk}")
                            if log_display_cnt < TRUNKATE_NUM:
                                logger.info(f"[chunk_{log_display_cnt}] " + chunk_str)
                                if not chunk_str.startswith("data: ") and "error" in chunk_str:
                                    logger.error(f"Found error in chunk: {chunk_str}")
                                    pass
                                else:
                                    try:
                                        for choice in json.loads(chunk_str[5:])['choices']:
                                            if "delta" in choice:
                                                content = choice.get("delta", {}).get("content", "")
                                                if content:
                                                    complete_content += content
                                    except JSONDecodeError as e:
                                        pass
                            elif log_display_cnt == TRUNKATE_NUM:
                                logger.info("... (truncated)\n")
                            log_display_cnt_var.set(log_display_cnt + 1)
                            if 'data: [DONE]' in chunk_str:
                                is_done = True
                            yield chunk
                    
                    log_interaction("RESPONSE", full_response_for_log)

                    if complete_content == '':
                        logger.warning(f"Complete content is empty")
                    if not is_done:
                        logger.warning(f"Response did not end with [DONE] api_provider: {api_provider} chunk_str: {chunk_str}")
        except Exception as e:
            logger.error(f"Unexpected error occurred: {e}\n{traceback.format_exc()}")
            response_status.set(500)
            yield json.dumps({"error": str(e)}).encode()
    return StreamingResponse(generate_stream_response(), media_type="text/event-stream", status_code=response_status.get())


async def handle_non_streaming_request(api_provider: str, uri: str, request_headers: dict, request_body: dict):
    """处理非流式请求"""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{API_PROVIDER[api_provider]['base_url']}/{uri}",
                headers={
                    **request_headers,
                    "Content-Type": "application/json"
                },
                json=request_body
            )
            # response.raise_for_status()
            logger.info(response.text)
            log_interaction("RESPONSE", response.text)
            return Response(content=response.text, status_code=response.status_code, media_type="application/json")
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error occurred: {e.response.status_code} - {e.response.text}")
        # raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        # 增加错误计数
        rate_limiter.increment_error(api_provider)
        return Response(content=json.dumps({"choices": [{"message": {"role": "assistant", "content": str(e)}}]}), status_code=e.response.status_code, media_type="application/json")

    except Exception as e:
        logger.error(f"Unexpected error occurred: {e}\n{traceback.format_exc()}")
        return Response(content=json.dumps({"choices": [{"message": {"role": "assistant", "content": str(e)}}]}), status_code=500, media_type="application/json")


async def handle_force_streaming_request(api_provider: str, uri: str, request_headers: dict, request_body: dict):
    """强制流式请求处理"""
    request_body["stream"] = True
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_PROVIDER[api_provider]['base_url']}/{uri}",
            headers={
                **request_headers,
                "Content-Type": "application/json"
            },
            json=request_body
        )
        response.raise_for_status()
        
        complete_content = ""
        async for line in response.aiter_lines():
            logger.info(line)
            if line:
                logger.info(line)
                try:
                    line_json = json.loads(line[6:])
                    for choice in line_json.get("choices", []):
                        complete_content += choice["delta"]["content"]
                except JSONDecodeError as e:
                    pass
                except Exception as e:
                    logger.error(f"Error occurred while processing response: {e} \n {line}")

        complete_response = {
            "id": "", "model": request_body['model'],
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0, "message": {"role": "assistant", "content": complete_content}, "finish_reason": "stop"
                }
            ],
            "created": int(time.time())
        }
        logger.info(complete_response)
        log_interaction("RESPONSE", response.text)
        return JSONResponse(content=complete_response, media_type="application/json", status_code=response.status_code)


# =============================================================================
# 内容处理函数
# =============================================================================

def truncate_content(request_body):
    """截断消息内容以减少日志大小"""
    truncated_body = copy.deepcopy(request_body)
    if 'messages' in truncated_body:
        for message in truncated_body['messages']:
            if 'content' in message and len(message['content']) > TRUNCATE_NUM:
                message['content'] = message['content'][:TRUNCATE_NUM] + f"... (truncated, {len(message['content']) - TRUNCATE_NUM} more characters)"
    return truncated_body


def extract_content(request_body):
    """从请求体中提取内容"""
    all_content = ''
    if 'messages' in request_body:
        for message in request_body['messages']:
            if 'content' in message:
                try:
                    if message['content']:
                        if isinstance(message['content'], list):  # Check if content is a list
                            all_content += json.dumps(message['content'], ensure_ascii=False)  # Concatenate list elements
                        else:
                            all_content += message['content']
                except Exception as e:
                    logger.error(f"Unexpected error occurred: {e}\n{traceback.format_exc()}")
    return all_content


def get_api_provider(model, request_body):
    """根据模型和请求体获取API提供商"""
    if model not in MODEL_CONFIG:
        raise HTTPException(status_code=404, detail=f"model not found in cfg_model.json! model: {model}")
    all_content = extract_content(request_body)
    encoding = tiktoken.get_encoding("cl100k_base")
    tokens = encoding.encode(all_content)
    token_count = len(tokens)
    logger.info(f"Request Body token: {token_count}, content: {all_content[:TRUNCATE_NUM]}... (truncated, {len(all_content) - TRUNCATE_NUM} more characters)")
    
    selected_api = None
    api_providers = list(MODEL_CONFIG[model].keys())
    
    for api_provider in api_providers:
        api_provider_cfg = API_PROVIDER[api_provider]
        
        if MODEL_CONFIG[model][api_provider].get('enable', True) is False:
            logging.info(f"{model} @ {api_provider} is disabled, skipping.")
            continue

        # 检查错误限制
        is_error_limited, remaining_minutes = rate_limiter.is_error_limited(api_provider)
        if is_error_limited:
            logging.warning(f"API {api_provider} is error limited for {remaining_minutes} more minutes")
            continue

        # 检查速率限制
        limits = api_provider_cfg.get('limits', {})
        is_allowed, reason = rate_limiter.check_limit(api_provider, limits, token_count)
        if not is_allowed:
            logging.warning(f"API {api_provider} limit reached: {reason}")
            continue
            
        # 更新计数器
        rate_limiter.increment(api_provider, token_count)
        selected_api = api_provider
        break
        
    if not selected_api:
        raise HTTPException(
            status_code=429, 
            detail="no api available due to rate limits or all APIs are switched off. Please try again later."
        )
        
    return selected_api

# =============================================================================
# API路由处理函数
# =============================================================================

@app.api_route("/v1/{path:path}", methods=['POST'])
async def handle_post_request(request: Request, path: str):
    """处理所有POST请求的主路由"""
    try:
        uri = f"{path}"
        request_headers = {
            key: value for key, value in request.headers.items() 
            if key.lower() not in ["host", "content-length"]
        }

        request_body = await request.json()
        log_interaction("REQUEST", request_body)
        logger.info(f"Request Headers: {request_headers}")
        # truncated_request_body = truncate_content(request_body)
        # logger.info(f"Request Body: {json.dumps(truncated_request_body, ensure_ascii=False)}")
        is_streaming = request_body.get("stream", False)
        model = request_body.get("model", "")

        if model.startswith('auto'):
            for model in MODEL_CONFIG:
                api_provider = get_api_provider(model, request_body)
                if api_provider:
                    break
        else:
            api_provider = get_api_provider(model, request_body)
        logger.info(f"Request api_provider: [{api_provider}] model: [{model}]")
        if api_provider not in API_PROVIDER:
            raise HTTPException(status_code=404, detail=f"API not found in config.yaml! api_provider: {api_provider} model: {model}")
        
        if API_PROVIDER[api_provider]['api_key']:
            request_headers.pop("authorization", None)
            request_headers["Authorization"] = f"Bearer {API_PROVIDER[api_provider]['api_key']}"
        
        request_headers.pop("accept-encoding", None)
        request_headers["Content-Type"] = "application/json"

        if MODEL_CONFIG[model][api_provider] and 'alias' in  MODEL_CONFIG[model][api_provider]:
            request_body['model'] = MODEL_CONFIG[model][api_provider]['alias']
            logger.info(f"model has been replaced to alias: {request_body['model']}")

        if is_streaming:
            return await handle_streaming_request(api_provider, uri, request_headers, request_body, passthrough=True)
        else:
            return await handle_non_streaming_request(api_provider, uri, request_headers, request_body)
    except HTTPException as http_exc:
        logger.error(f"HTTP error occurred: {http_exc}")
        raise http_exc
    except Exception as exc:
        logger.error(f"Unexpected error occurred: {exc}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.route('/api_usage', methods=['GET'])
async def get_api_usage(request: Request):
    """
    获取当前API使用情况统计
    ---
    responses:
      200:
        description: 返回各API的当前使用统计数据
        content:
          application/json:
            schema:
              type: object
              properties:
                data:
                  type: object
                  additionalProperties:
                    type: object
                    properties:
                      rpm:
                        type: object
                        properties:
                          current:
                            type: integer
                          limit:
                            type: integer
                      tpm:
                        type: object
                        properties:
                          current:
                            type: integer
                          limit:
                            type: integer
                      rpd:
                        type: object
                        properties:
                          current:
                            type: integer
                          limit:
                            type: integer
                timestamp:
                  type: string
    """
    return JSONResponse(content=rate_limiter.get_usage_stats())


@app.route('/v1/models', methods=['GET', 'POST'])
async def models(request: Request):
    """获取支持的模型列表"""
    data = {
        "object": "list",
        "data": [
            {
                "id": "auto",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "open_ai"
            }
        ]
    }

    for model_name, api_provider in  MODEL_CONFIG.items():
        model = {
            "id": model_name,
            "object": "model",
            "created": int(time.time()),
            "owned_by": api_provider
        }
        data['data'].append(model)
        # precfg_models.append(model_name)

    return JSONResponse(content=data, media_type="application/json", status_code=200)


@app.get("/api/config")
async def get_config():
    """获取模型配置"""
    with open(config_path, 'r') as file:
        config = yaml.load(file)
    MODEL_CONFIG = config['model_config']
    with config_lock:
        return JSONResponse(content=MODEL_CONFIG)


@app.post("/api/config")
async def update_config(request: Request):
    """更新模型配置"""
    global MODEL_CONFIG
    new_model_config = await request.json()
    
    with config_lock:
        # 更新内存中的配置
        MODEL_CONFIG = new_model_config
        
        # 更新YAML文件
        with open(config_path, 'r') as file:
            full_config = yaml.load(file)
        
        full_config['model_config'] = new_model_config
        
        with open(config_path, 'w') as file:
            yaml.dump(full_config, file)
            
    return JSONResponse(content={"status": "success"})

@app.get("/")
async def root_redirect():
    """将根路径重定向到管理界面"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/admin")

@app.get("/admin")
async def admin_ui():
    """返回管理界面"""
    return FileResponse("static/admin.html")


@app.get("/api/error_logs")
async def get_error_logs():
    """获取最近的错误日志"""
    log_dir = os.path.join(script_dir, 'log')
    error_log_file = os.path.join(log_dir, 'app.log')
    
    error_logs = []
    if os.path.exists(error_log_file):
        try:
            with open(error_log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                # 从后往前查找包含ERROR的行
                for i in range(len(lines) - 1, -1, -1):
                    line = lines[i]
                    if '- ERROR' in line:
                        # 获取错误行及其前后几行作为上下文
                        start = max(0, i - 2)
                        end = min(len(lines), i + 1)
                        error_context = ''.join(lines[start:end])
                        error_logs.append(error_context)
                        # 限制返回的错误日志数量
                        if len(error_logs) >= 10:
                            break
                # 反转列表以保持时间顺序（最新的在前面）
                error_logs.reverse()
        except Exception as e:
            logger.error(f"Error reading error logs: {e}")
    
    return JSONResponse(content={"error_logs": error_logs})


@app.post("/api/health_check")
async def health_check(request: Request):
    """健康检测端点"""
    try:
        data = await request.json()
        provider_name = data.get("provider")
        model_name = data.get("model")
        
        if not provider_name:
            raise HTTPException(status_code=400, detail="Provider name is required")
        
        if not model_name:
            raise HTTPException(status_code=400, detail="Model name is required")
        
        if provider_name not in API_PROVIDER:
            raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")
        
        # 获取provider配置
        provider_config = API_PROVIDER[provider_name]
        base_url = provider_config.get("base_url")
        api_key = provider_config.get("api_key")
        
        if not base_url:
            raise HTTPException(status_code=500, detail=f"Provider '{provider_name}' has no base URL configured")
        
        # 构造测试请求
        test_payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 5
        }
        
        # 设置请求头
        headers = {
            "Content-Type": "application/json"
        }
        
        # 如果有API密钥，添加到请求头
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        # 发送测试请求
        import time
        start_time = time.time()
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=test_payload
            )
            
        end_time = time.time()
        response_time = int((end_time - start_time) * 1000)  # 转换为毫秒
        
        # 检查响应状态
        if response.status_code == 200:
            return JSONResponse(content={
                "status": "healthy",
                "provider": provider_name,
                "model": model_name,
                "response_time": response_time
            })
        else:
            return JSONResponse(content={
                "status": "unhealthy",
                "provider": provider_name,
                "model": model_name,
                "error": f"HTTP {response.status_code}: {response.text}",
                "response_time": response_time
            })
            
    except HTTPException as http_exc:
        raise http_exc
    except Exception as exc:
        logger.error(f"Health check error for provider '{provider_name}' and model '{model_name}': {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/api/reset_rate_limits")
async def reset_rate_limits(request: Request):
    """重置所有速率限制的API端点"""
    try:
        result = rate_limiter.reset_all_limits()
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Error resetting rate limits: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset rate limits")

# =============================================================================
# 静态文件和应用启动
# =============================================================================

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")

# 启动服务器
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100)
