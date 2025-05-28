import urllib.request
import urllib.parse
import time
import concurrent.futures
from datetime import datetime
import sys
import os
import subprocess
import logging
import logging.handlers  # 导入 logging.handlers
import socket
import locale

# --- 日志配置 (每小时轮替, 只保留当前小时的错误日志) ---
LOG_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILENAME_BASE = "auth_monitor.log"
LOG_FILE_PATH = os.path.join(LOG_DIR, LOG_FILENAME_BASE)

logger = logging.getLogger("AuthMonitorLogger")
logger.setLevel(logging.DEBUG)  # Logger本身处理所有DEBUG及以上级别消息，由Handler决定最终输出哪些

# 创建 TimedRotatingFileHandler
# when='H': 每小时轮替 (H for Hour)
# interval=1: 表示每1个小时轮替一次
# backupCount=0: 不保留任何备份日志文件。轮替时，旧日志会被清除。
handler = logging.handlers.TimedRotatingFileHandler(
    LOG_FILE_PATH,
    when="H",  # 按小时轮替
    interval=1,
    backupCount=0,  # 不保留备份，旧日志在轮替时被删除
    encoding='utf-8',
    delay=False,
    utc=False
)
# 设置文件处理器只记录 WARNING 及以上级别的信息
handler.setLevel(logging.WARNING)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
handler.setFormatter(formatter)
logger.addHandler(handler)
# --- END 日志配置 ---

# --- Targets for Authentication Check ---
AUTHENTICATION_TARGETS = [
    {
        "url": "http://detectportal.firefox.com/success.txt",
        "expected_string": "success",
        "description": "Firefox Captive Portal Detection"
    },
    {
        "url": "http://example.com",
        "expected_string": "Example Domain",
        "description": "Example.com Check"
    },
]

TIMEOUT = 3
LOGIN_SCRIPT_NAME = "login.py"
LOGIN_SCRIPT_TIMEOUT = 120


def verify_authenticated_connection(target_info):
    url = target_info["url"]
    expected_string = target_info["expected_string"]
    try:
        start_time = time.perf_counter()
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            final_url = response.geturl()
            http_status_code = response.getcode()
            if http_status_code != 200:
                return {"status": False, "reason": f"HTTP Status {http_status_code}", "target_info": target_info,
                        "latency": None}
            original_hostname = urllib.parse.urlparse(url).hostname
            final_hostname = urllib.parse.urlparse(final_url).hostname
            if final_hostname != original_hostname:
                if not (original_hostname.endswith(final_hostname.replace("www.", "")) or \
                        final_hostname.endswith(original_hostname.replace("www.", "")) or \
                        original_hostname.replace("www.", "") == final_hostname.replace("www.", "")):
                    if original_hostname.split('.')[-2] != final_hostname.split('.')[
                        -2]:  # Compare second-level domains
                        return {"status": False, "reason": f"Redirected from {url} to {final_url}",
                                "target_info": target_info, "latency": None}
            content_to_check = response.read(4096).decode('utf-8', errors='ignore')
            latency = round((time.perf_counter() - start_time) * 1000)
            if expected_string in content_to_check:
                return {"status": True, "reason": "Authenticated: Expected content found.", "target_info": target_info,
                        "latency": latency}
            else:
                return {"status": False, "reason": "Not Authenticated: Expected content NOT found.",
                        "target_info": target_info, "latency": latency, "content_snippet": content_to_check[:200]}
    except Exception as e:
        error_message = str(e)
        if "timed out" in error_message.lower() or isinstance(e, socket.timeout):
            error_message = "Timeout"
        return {"status": False, "reason": f"Error: {error_message}", "target_info": target_info, "latency": None}


def main():
    logger.debug("========== SCRIPT ENVIRONMENT START ==========")  # DEBUG level, not logged to file by default
    try:
        logger.debug(f"Current Working Directory (os.getcwd()): {os.getcwd()}")
        logger.debug(f"Script absolute path (__file__): {os.path.abspath(__file__)}")
        logger.debug(f"Python executable (sys.executable): {sys.executable}")
        logger.debug(f"Python version (sys.version): {sys.version.replace(chr(10), ' ').replace(chr(13), ' ')}")
        logger.debug(f"sys.argv: {sys.argv}")
        logger.debug(f"os.getenv('PATH'): {os.getenv('PATH')}")
        logger.debug(f"os.getenv('PYTHONPATH'): {os.getenv('PYTHONPATH')}")
        logger.debug(f"os.getenv('PYTHONHOME'): {os.getenv('PYTHONHOME')}")
        logger.debug(f"sys.path (Python module search paths): {sys.path}")
        logger.debug(f"Default locale encoding: {locale.getpreferredencoding(False)}")
        stdout_encoding = None
        if sys.stdout and hasattr(sys.stdout, 'encoding'): stdout_encoding = sys.stdout.encoding
        logger.debug(f"sys.stdout.encoding: {stdout_encoding}")
    except Exception as e_env:
        logger.error(f"Error logging environment details: {e_env}")  # ERROR, will be logged
    logger.debug("========== SCRIPT ENVIRONMENT END ==========")

    logger.info("Campus Network Authentication Monitor Script Started")  # INFO, not logged to file by default
    logger.debug(f"Authentication targets configured: {len(AUTHENTICATION_TARGETS)}")

    if not AUTHENTICATION_TARGETS:
        logger.error("错误: AUTHENTICATION_TARGETS 配置为空，无法启动检测。")  # ERROR, will be logged
        return

    num_workers = len(AUTHENTICATION_TARGETS)
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    login_script_path = os.path.join(current_script_dir, LOGIN_SCRIPT_NAME)

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        while True:
            cycle_start_time_obj = datetime.now()
            overall_cycle_perf_start = time.perf_counter()
            logger.debug(f"开始新一轮认证状态检测...")  # DEBUG

            found_authenticated_session = False
            future_to_target_info_map = {
                executor.submit(verify_authenticated_connection, target_info): target_info
                for target_info in AUTHENTICATION_TARGETS
            }
            results_this_cycle = []

            for future in concurrent.futures.as_completed(future_to_target_info_map):
                if found_authenticated_session:
                    try:
                        future.result(timeout=0.01)
                    except:
                        pass
                    continue
                target_info_processed = future_to_target_info_map[future]
                try:
                    result = future.result()
                    results_this_cycle.append(result)
                    if result["status"]:
                        found_authenticated_session = True
                        logger.debug(f"AUTHENTICATED & ONLINE via {result['target_info']['description']}")  # DEBUG
                        for f_to_cancel in future_to_target_info_map.keys():
                            if f_to_cancel != future and not f_to_cancel.done():
                                f_to_cancel.cancel()
                        break
                except concurrent.futures.CancelledError:
                    pass
                except Exception as e_future:
                    logger.error(f"处理目标 '{target_info_processed['description']}' 时发生内部错误: {e_future}",
                                 exc_info=True)  # ERROR

            if not found_authenticated_session:
                logger.warning(
                    f"NOT AUTHENTICATED / CAPTIVE PORTAL DETECTED (或网络连接问题)")  # WARNING, will be logged
                for res in results_this_cycle:
                    if not res['status']:
                        logger.warning(  # Log reasons for failure as WARNING
                            f"  尝试 {res['target_info']['description']} ({res['target_info']['url']}): {res['reason']}")
                        if "content_snippet" in res and res[
                            'content_snippet']:  # Content snippet is for debugging if needed
                            logger.debug(f"    ↳ 收到片段: \"{res['content_snippet'].strip()}...\"")  # DEBUG

                logger.info(
                    f"检测到未认证，尝试执行 '{LOGIN_SCRIPT_NAME}' 脚本...")  # INFO (changed to debug as it's an action, not an error itself)
                logger.debug(f"检测到未认证，尝试执行 '{LOGIN_SCRIPT_NAME}' 脚本...")  # DEBUG for this line

                if not os.path.exists(login_script_path):
                    logger.error(f"错误: '{LOGIN_SCRIPT_NAME}' 未在脚本所在目录找到 ({login_script_path})。")  # ERROR
                else:
                    try:
                        process_encoding = 'utf-8'
                        try:
                            if sys.stdout and hasattr(sys.stdout, 'encoding') and sys.stdout.encoding:
                                process_encoding = sys.stdout.encoding
                            else:
                                preferred_encoding = locale.getpreferredencoding(False)
                                if preferred_encoding: process_encoding = preferred_encoding
                        except Exception:
                            logger.warning(
                                "无法获取 sys.stdout.encoding 或 locale.getpreferredencoding，将使用 utf-8 作为 subprocess 编码。")  # WARNING
                            pass

                        completed_process = subprocess.run(
                            [sys.executable, login_script_path],
                            capture_output=True, text=True, timeout=LOGIN_SCRIPT_TIMEOUT, check=False,
                            encoding=process_encoding, errors='replace'
                        )

                        if completed_process.returncode != 0:
                            logger.error(
                                f"'{LOGIN_SCRIPT_NAME}' 执行失败。退出码: {completed_process.returncode}")  # ERROR
                            if completed_process.stdout.strip():
                                logger.error(f"  [login.py stdout for error code]:\n{completed_process.stdout.strip()}")
                            if completed_process.stderr.strip():
                                logger.error(f"  [login.py stderr for error code]:\n{completed_process.stderr.strip()}")
                        else:
                            logger.debug(
                                f"'{LOGIN_SCRIPT_NAME}' 执行成功。退出码: {completed_process.returncode}")  # DEBUG
                            if completed_process.stdout.strip():
                                logger.debug(
                                    f"  [login.py stdout for success code]:\n{completed_process.stdout.strip()}")
                            if completed_process.stderr.strip():  # Stderr might contain warnings even on success
                                logger.warning(
                                    f"  [login.py stderr on success code]:\n{completed_process.stderr.strip()}")

                    except FileNotFoundError:
                        logger.error(f"错误: Python解释器或 '{LOGIN_SCRIPT_NAME}' 无法执行。")  # ERROR
                    except subprocess.TimeoutExpired:
                        logger.warning(f"'{LOGIN_SCRIPT_NAME}' 执行超时 (超过 {LOGIN_SCRIPT_TIMEOUT} 秒)。")  # WARNING
                    except Exception as e_login_script:
                        logger.error(f"执行 '{LOGIN_SCRIPT_NAME}' 时发生错误: {e_login_script}", exc_info=True)  # ERROR

            elapsed_cycle_duration = time.perf_counter() - overall_cycle_perf_start

            if found_authenticated_session:
                sleep_duration = 60  # 1 分钟
            else:  # 未认证 (login.py 已尝试或即将尝试)
                sleep_duration = 10  # 10 秒

            logger.debug(f"本轮检测耗时: {elapsed_cycle_duration:.2f}s, 下轮检测前等待: {sleep_duration:.2f}s")  # DEBUG
            time.sleep(sleep_duration)


if __name__ == '__main__':
    main()