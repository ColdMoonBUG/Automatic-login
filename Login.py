# -*- coding: utf-8 -*-
import requests
import time
import socket
import os
import sys
import json
import random  # Added for shuffling

# --- Configuration ---
SUCCESSFUL_LOGIN_CANDIDATES_FILE = "successful.json"  # Source for login attempts

# Network and Login Configuration
LOGOUT_URL_TEMPLATE = "http://172.16.1.38:801/eportal/?c=ACSetting&a=Logout&loginMethod=1&protocol=http%3A&hostname=172.16.1.38&port=&iTermType={iTermType}&wlanuserip={local_ip}&wlanacip=172.20.1.1&wlanacname=huawei-me60&redirect=null&session=null&vlanid=null%3Cinput+type%3D&ip={local_ip}&queryACIP=0&jsVersion=2.4.3"
LOGIN_URL_TEMPLATE = "http://172.16.1.38:801/eportal/?c=ACSetting&a=Login&loginMethod=1&protocol=http%3A&hostname=172.16.1.38&port=&iTermType={iTermType}&wlanuserip={local_ip}&wlanacip=172.20.1.1&wlanacname=&redirect=null&session=null&vlanid=0&mac=00-00-00-00-00-00&ip={local_ip}&enAdvert=0&jsVersion=2.4.3&DDDDD=%2C0%2C{account}%40cmcc&upass={password}&R1=0&R2=0&R3=0&R6=0&para=00&0MKKey=123456&buttonClicked=&redirect_url=&err_flag=&username=&password=&user=&cmd=&Login=&v6ip="
LOGIN_SUCCESS_TITLE = "认证成功页"
PASSWORD = "147258"
ITERM_TYPES_FOR_PRE_LOGOUT = [1, 2, 3]  # Used for pre-logout

# Delays and Retries
REQUEST_TIMEOUT = 10
LOGOUT_REQUEST_TIMEOUT = 15
POST_LOGOUT_DELAY = 2  # Used after the pre-logout sequence
INTER_LOGIN_ATTEMPT_DELAY = 1  # Delay between failed login attempts

# Global variables
local_ip = None
login_candidates = []  # Will store entries from successful.json


# --- Helper Functions ---
def fix_cmd_encoding():
    if sys.platform == 'win32':
        os.system('chcp 65001 > nul')


def get_local_ip_address():
    try:
        # Try to connect to a public DNS server to find the local IP used for internet-bound traffic
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(2)  # Short timeout for the connection attempt
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception as e:
        print(f"[警告] 自动获取IP失败: {e}")
        return None


def load_login_candidates():
    global login_candidates
    try:
        if os.path.exists(SUCCESSFUL_LOGIN_CANDIDATES_FILE) and os.path.getsize(SUCCESSFUL_LOGIN_CANDIDATES_FILE) > 0:
            with open(SUCCESSFUL_LOGIN_CANDIDATES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list) and data:  # Ensure it's a non-empty list
                    login_candidates = data
                    print(f"[信息] 从 {SUCCESSFUL_LOGIN_CANDIDATES_FILE} 加载了 {len(login_candidates)} 个登录候选。")
                elif isinstance(data, list) and not data:
                    print(f"[错误] {SUCCESSFUL_LOGIN_CANDIDATES_FILE} 为空。没有可用的登录凭据。")
                    login_candidates = []
                else:
                    print(f"[警告] {SUCCESSFUL_LOGIN_CANDIDATES_FILE} 内容格式不正确 (不是列表)，或为空。")
                    login_candidates = []
        else:
            print(f"[错误] {SUCCESSFUL_LOGIN_CANDIDATES_FILE} 未找到或为空。没有可用的登录凭据。")
            login_candidates = []

    except json.JSONDecodeError:
        corrupt_file_path = SUCCESSFUL_LOGIN_CANDIDATES_FILE + ".corrupt." + time.strftime("%Y%m%d-%H%M%S")
        print(f"[警告] {SUCCESSFUL_LOGIN_CANDIDATES_FILE} 内容损坏或非JSON格式。")
        try:
            if os.path.exists(SUCCESSFUL_LOGIN_CANDIDATES_FILE):
                os.rename(SUCCESSFUL_LOGIN_CANDIDATES_FILE, corrupt_file_path)
                print(f"[信息] 已将损坏文件备份为: {corrupt_file_path}")
        except Exception as backup_e:
            print(f"[错误] 备份损坏文件 {SUCCESSFUL_LOGIN_CANDIDATES_FILE} 失败: {backup_e}")
        login_candidates = []
    except Exception as e:
        print(f"[错误] 加载 {SUCCESSFUL_LOGIN_CANDIDATES_FILE} 时发生未知错误: {e}。")
        login_candidates = []

    if not login_candidates:
        print("[严重] 由于未能加载任何登录候选，脚本无法继续。程序将退出。")
        sys.exit(1)


# --- Core Login/Logout Logic ---
def attempt_login(account, iTermType, current_ip, password_to_use):
    login_url = LOGIN_URL_TEMPLATE.format(account=account, iTermType=iTermType, local_ip=current_ip,
                                          password=password_to_use)
    try:
        response = requests.get(login_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        if LOGIN_SUCCESS_TITLE in response.text:
            return True
        else:
            return False
    except requests.exceptions.Timeout:
        print(f"[调试] 登录请求超时 (账号: {account}, 类型: {iTermType})")
        return False
    except requests.exceptions.RequestException as e:
        print(f"[调试] 登录网络请求异常 (账号: {account}, 类型: {iTermType}): {e}")
        return False
    except Exception as e:
        print(f"[调试] 登录时发生未知错误 (账号: {account}, 类型: {iTermType}): {e}")
        return False


def perform_logout(current_ip, logged_in_account_info="N/A", logged_in_iTermType=None):
    if not LOGOUT_URL_TEMPLATE:
        print("[警告] LOGOUT_URL_TEMPLATE 未配置，跳过下线操作。")
        return True
    if logged_in_iTermType is None:
        print(f"[警告] 执行下线操作 (针对: {logged_in_account_info}) 需要 iTermType，但未提供。跳过此特定下线。")
        return True

    logout_url = LOGOUT_URL_TEMPLATE.format(local_ip=current_ip, iTermType=logged_in_iTermType)

    logout_retry_count = 2
    logout_retry_delay = 5

    for attempt in range(logout_retry_count + 1):
        try:
            print(
                f"[信息] 发送下线请求 (尝试 {attempt + 1}/{logout_retry_count + 1}) IP: {current_ip} (信息: {logged_in_account_info}, iTermType: {logged_in_iTermType})")
            response = requests.get(logout_url, timeout=LOGOUT_REQUEST_TIMEOUT)
            response.raise_for_status()
            print(f"[信息] 下线请求已处理 (服务器响应 {response.status_code}) (尝试 {attempt + 1})。")
            return True
        except requests.exceptions.Timeout:
            print(
                f"[错误] 下线请求超时 (尝试 {attempt + 1}/{logout_retry_count + 1}) IP: {current_ip}, iTermType: {logged_in_iTermType}")
            if attempt < logout_retry_count:
                print(f"[信息] {logout_retry_delay}秒后重试下线...")
                time.sleep(logout_retry_delay)
        except requests.exceptions.RequestException as e:
            print(f"[错误] 下线网络请求异常 (尝试 {attempt + 1}/{logout_retry_count + 1}): {e}")
            if attempt < logout_retry_count:
                print(f"[信息] {logout_retry_delay}秒后重试下线...")
                time.sleep(logout_retry_delay)
        except Exception as e:
            print(f"[错误] 下线时发生未知错误 (尝试 {attempt + 1}/{logout_retry_count + 1}): {e}")
            return False

    print(f"[严重错误] 下线操作最终失败 (信息: {logged_in_account_info}, iTermType: {logged_in_iTermType})。")
    return False


# --- Main Program ---
if __name__ == "__main__":
    fix_cmd_encoding()

    print("=== 校园网自动登录脚本 (使用 'successful.json' 中凭据) ===")

    load_login_candidates()

    local_ip = get_local_ip_address()
    if not local_ip:
        print("[错误] 自动获取IP失败，无法进行登录操作。程序将退出。")
        sys.exit(1)  # Exit if IP cannot be obtained automatically
    print(f"\n[信息] 当前使用的IP地址: {local_ip}")

    # --- Perform Pre-Logout (Single round, iterating through iTermTypes) ---
    print("\n[信息] 开始执行预下线操作...")
    any_pre_logout_signal_sent_successfully = False
    for itype in ITERM_TYPES_FOR_PRE_LOGOUT:
        if perform_logout(local_ip, logged_in_account_info="预下线操作", logged_in_iTermType=itype):
            any_pre_logout_signal_sent_successfully = True
            # Optional: could print success for this specific itype here if verbose logging is desired
            # print(f"  [预下线] 成功为 iTermType {itype} 发送下线信号。")

    if any_pre_logout_signal_sent_successfully:
        print(f"  [预下线] 预下线信号已为各类型尝试发送，并至少有一个类型发送成功。")
    else:
        print(f"  [预下线警告] 预下线操作为所有类型尝试发送，但似乎均未成功响应。")

    print(f"  [信息] {POST_LOGOUT_DELAY}秒后继续登录尝试...")
    time.sleep(POST_LOGOUT_DELAY)
    print("[信息] 预下线操作完成。\n")

    # --- Attempt Login using candidates from successful.json ---
    random.shuffle(login_candidates)

    logged_in_successfully = False
    print(f"[信息] 开始尝试使用 {len(login_candidates)} 个已存储的凭据进行登录 (密码: '{PASSWORD}')")
    # Removed input("按 Enter 开始登录尝试...\n") for full automation

    for candidate_index, candidate in enumerate(login_candidates):
        account = candidate.get('account')
        login_type = candidate.get('type')

        if not account or login_type is None:
            print(f"[警告] 跳过格式不正确的候选条目 (索引 {candidate_index}): {candidate}")
            continue

        print(f"\n--- 尝试候选 {candidate_index + 1}/{len(login_candidates)} ---")
        print(f"[尝试] 账号: {account}, 类型(iTermType): {login_type}")

        if attempt_login(account, login_type, local_ip, PASSWORD):
            print(f"[成功] 登录成功! 账号: {account}, 类型: {login_type}")
            logged_in_successfully = True
            break
        else:
            print(f"[失败] 账号: {account}, 类型: {login_type} 登录失败。")
            if candidate_index < len(login_candidates) - 1:
                print(f"[信息] {INTER_LOGIN_ATTEMPT_DELAY}秒后尝试下一个候选凭据...")
                time.sleep(INTER_LOGIN_ATTEMPT_DELAY)

    if logged_in_successfully:
        print("\n[完成] 已成功登录校园网。脚本将退出。")
    else:
        print(
            f"\n[错误] 尝试了 {len(login_candidates)} 个来自 '{SUCCESSFUL_LOGIN_CANDIDATES_FILE}' 的凭据，均未能成功登录。")
        print("       请检查网络状态、IP地址、密码以及文件中的条目是否仍然有效。")

    print("\n脚本执行完毕。")