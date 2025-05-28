import urllib.request
import urllib.parse  # Make sure this is imported at the top level
import time
import concurrent.futures
from datetime import datetime
import sys
import os
import subprocess  # Added for running the login script

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

TIMEOUT = 3  # Timeout for authentication checks.
LOGIN_SCRIPT_NAME = "login.py"  # Name of your login script
LOGIN_SCRIPT_TIMEOUT = 120  # Seconds to wait for login.py to complete


def verify_authenticated_connection(target_info):
    """
    Checks a single target URL for expected content to verify authenticated internet access.
    Returns a dictionary with status, reason, and target_info.
    """
    url = target_info["url"]
    expected_string = target_info["expected_string"]
    # description = target_info["description"] # Not directly used in this function's logic after input

    try:
        start_time = time.perf_counter()
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'})

        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            final_url = response.geturl()
            http_status_code = response.getcode()

            if http_status_code != 200:
                return {
                    "status": False,
                    "reason": f"HTTP Status {http_status_code}",
                    "target_info": target_info,
                    "latency": None
                }

            # Basic redirect check (as in your original script)
            # Ensure that urllib.parse is available here
            original_hostname = urllib.parse.urlparse(url).hostname
            final_hostname = urllib.parse.urlparse(final_url).hostname
            if final_hostname != original_hostname:
                # A more lenient check for subdomains like www.
                if not (original_hostname.endswith(final_hostname) or final_hostname.endswith(original_hostname)):
                    return {
                        "status": False,
                        "reason": f"Redirected from {url} to {final_url}",
                        "target_info": target_info,
                        "latency": None
                    }

            content_to_check = response.read(4096).decode('utf-8', errors='ignore')
            latency = round((time.perf_counter() - start_time) * 1000)

            if expected_string in content_to_check:
                return {
                    "status": True,
                    "reason": "Authenticated: Expected content found.",
                    "target_info": target_info,
                    "latency": latency
                }
            else:
                return {
                    "status": False,
                    "reason": "Not Authenticated: Expected content NOT found.",
                    "target_info": target_info,
                    "latency": latency,
                    "content_snippet": content_to_check[:200]
                }

    except Exception as e:
        error_message = str(e)
        if "timed out" in error_message.lower() or isinstance(e, socket.timeout):
            error_message = "Timeout"
        return {
            "status": False,
            "reason": f"Error: {error_message}",
            "target_info": target_info,
            "latency": None
        }


def main():
    print("🔑 Campus Network Authentication Monitor (Ctrl+C 终止)")
    print(f"   (每当未认证时将尝试运行 '{LOGIN_SCRIPT_NAME}')")
    print(f"⏱️  单目标超时: {TIMEOUT}s.")
    if not AUTHENTICATION_TARGETS:
        print("🛑 错误: AUTHENTICATION_TARGETS 配置为空，无法启动检测。")
        return
    print(f"ℹ️  检测目标 ({len(AUTHENTICATION_TARGETS)}):")
    for i, target in enumerate(AUTHENTICATION_TARGETS):
        print(f"    {i + 1}. {target['description']} ({target['url']}) - Expects: \"{target['expected_string']}\"")
    print("=" * 60)

    num_workers = len(AUTHENTICATION_TARGETS)
    # Determine the absolute path to login.py assuming it's in the same directory as this script
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    login_script_path = os.path.join(current_script_dir, LOGIN_SCRIPT_NAME)

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        while True:
            cycle_start_time_obj = datetime.now()
            overall_cycle_perf_start = time.perf_counter()

            print(f"\n[{cycle_start_time_obj.strftime('%H:%M:%S.%f')[:-3]}] 🚦 开始新一轮认证状态检测...")

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
                        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                        print(f"  [{ts}] ✅ **AUTHENTICATED & ONLINE**")
                        print(f"     └── Via: {result['target_info']['description']} ({result['target_info']['url']})")
                        if result['latency'] is not None:
                            print(f"     └── 延迟: {result['latency']}ms")

                        for f_to_cancel in future_to_target_info_map.keys():
                            if f_to_cancel != future and not f_to_cancel.done():
                                f_to_cancel.cancel()
                        break
                except concurrent.futures.CancelledError:
                    pass
                except Exception as e_future:
                    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    print(f"  [{ts}] ⚠️  处理目标 '{target_info_processed['description']}' 时发生内部错误: {e_future}")

            if not found_authenticated_session:
                ts_fail = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                print(f"  [{ts_fail}] ❌ **NOT AUTHENTICATED / CAPTIVE PORTAL DETECTED** (或网络连接问题)")
                for res in results_this_cycle:
                    if not res['status']:
                        print(
                            f"      尝试 {res['target_info']['description']} ({res['target_info']['url']}): {res['reason']}")
                        if "content_snippet" in res and res[
                            'content_snippet']:  # Check if snippet exists and is not empty
                            print(f"       ↳ 收到片段: \"{res['content_snippet'].strip()}...\"")

                # Attempt to run the login script
                ts_login_attempt = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                print(f"  [{ts_login_attempt}] ℹ️  检测到未认证，尝试执行 '{LOGIN_SCRIPT_NAME}' 脚本...")

                if not os.path.exists(login_script_path):
                    print(
                        f"  [{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] 🛑 错误: '{LOGIN_SCRIPT_NAME}' 未在脚本所在目录找到 ({login_script_path})。")
                else:
                    try:
                        completed_process = subprocess.run(
                            [sys.executable, login_script_path],  # sys.executable ensures using the correct Python
                            capture_output=True, text=True, timeout=LOGIN_SCRIPT_TIMEOUT, check=False,
                            # encoding errors common on Windows without specifying
                            encoding=sys.stdout.encoding or 'utf-8', errors='replace'
                        )
                        ts_login_done = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                        print(
                            f"  [{ts_login_done}] ℹ️  '{LOGIN_SCRIPT_NAME}' 执行完毕。退出码: {completed_process.returncode}")
                        if completed_process.stdout.strip():
                            print(f"     [login.py stdout]:\n{completed_process.stdout.strip()}")
                        if completed_process.stderr.strip():
                            print(f"     [login.py stderr]:\n{completed_process.stderr.strip()}")

                    except FileNotFoundError:  # Should be caught by os.path.exists, but as a fallback
                        print(
                            f"  [{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] 🛑 错误: Python解释器或 '{LOGIN_SCRIPT_NAME}' 无法执行。")
                    except subprocess.TimeoutExpired:
                        print(
                            f"  [{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] ⚠️  '{LOGIN_SCRIPT_NAME}' 执行超时 (超过 {LOGIN_SCRIPT_TIMEOUT} 秒)。")
                    except Exception as e_login_script:
                        print(
                            f"  [{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] 🔥  执行 '{LOGIN_SCRIPT_NAME}' 时发生错误: {e_login_script}")

            elapsed_cycle_duration = time.perf_counter() - overall_cycle_perf_start
            sleep_duration = max(5.0 - elapsed_cycle_duration, 1.0)
            if found_authenticated_session:
                sleep_duration = max(50.0 - elapsed_cycle_duration, 5.0)

            print(f"--- 本轮检测耗时: {elapsed_cycle_duration:.2f}s, 下轮检测前等待: {sleep_duration:.2f}s ---")
            time.sleep(sleep_duration)


if __name__ == '__main__':
    # urllib.parse is imported at the top level now
    # socket is also needed for socket.timeout in verify_authenticated_connection's except block
    import socket

    main()