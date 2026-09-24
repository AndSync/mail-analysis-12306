#!/usr/bin/env python3
"""ZCode MCP server：12306 邮件分析（stdio JSON-RPC，仅标准库）。

配置来源（优先级从高到低）：
1. 环境变量 MAIL12306_* —— 由 ZCode 客户端从插件的 userConfig 展开注入
   （用户在 插件管理 → 插件详情 → 高级设置 中填写，即可视化配置界面）。
2. 用户配置文件 ~/.zcode/mail-analysis-12306/config.json（save_mail_config 工具写入）。

`analyze_12306_mail` 在邮箱信息未配置时直接返回错误，强制先配置后使用。
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_PY = os.path.join(PLUGIN_DIR, 'main.py')

CONFIG_DIR = os.environ.get(
    'MAIL12306_CONFIG_DIR',
    os.path.join(os.path.expanduser('~'), '.zcode', 'mail-analysis-12306'),
)
CONFIG_PATH = os.environ.get('MAIL12306_CONFIG') or os.path.join(CONFIG_DIR, 'config.json')

RUN_CONFIG_PATH = os.path.join(CONFIG_DIR, 'run-config.json')
RUN_LOG_PATH = os.path.join(CONFIG_DIR, 'run.log')

TERMINAL_MARKERS = [
    '所有任务完成', '邮件发送失败', '程序运行出错', '邮箱尚未配置',
    '无法连接到邮箱服务器', '未找到任何12306相关邮件',
    '未能从邮件中提取到任何票务记录', '分析报告为空', '用户中断程序',
]

SERVER_INFO = {"name": "mail-analysis-12306", "version": "0.6.1"}

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

ENV_FOR = {
    'sender_email': 'MAIL12306_SENDER_EMAIL',
    'sender_password': 'MAIL12306_SENDER_PASSWORD',
    'recipient_email': 'MAIL12306_RECIPIENT_EMAIL',
    'imap_server': 'MAIL12306_IMAP_SERVER',
    'smtp_server': 'MAIL12306_SMTP_SERVER',
    'imap_port': 'MAIL12306_IMAP_PORT',
    'smtp_port': 'MAIL12306_SMTP_PORT',
    'mailbox_name': 'MAIL12306_MAILBOX_NAME',
}

UI_HINT = (
    '设置 → 插件管理 → 12306邮件分析 → 详情 → 高级设置（Advanced）'
    '，填写邮箱地址、授权码、报告收件人后重启会话'
)


def _log(msg):
    print(msg, file=sys.stderr, flush=True)


def _is_placeholder(value):
    if value is None:
        return True
    if isinstance(value, str):
        s = value.strip()
        return not s or s.startswith('your_') or s.endswith('@example.com')
    return False


def get_env(key):
    v = os.environ.get(ENV_FOR[key], '').strip()
    if not v:
        return None
    # 其他 agent（Claude Code / Codex / Trae 等）不会展开 ${user_config.*} 模板，
    # 字面量模板值按未配置处理，回退到配置文件。
    if v.startswith('${') and v.endswith('}') and 'user_config' in v:
        return None
    return v


def load_file_config():
    if not os.path.exists(CONFIG_PATH):
        return None
    try:
        with open(CONFIG_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        _log(f'load_file_config failed: {e}')
        return None


def effective_config():
    """合并 环境变量(userConfig) 与配置文件，返回 main.py 格式的配置字典。"""
    cfg = load_file_config() or {}
    email = cfg.setdefault('email', {})

    env_email = get_env('sender_email')
    if env_email:
        email['sender_email'] = env_email
    env_pw = get_env('sender_password')
    if env_pw:
        email['sender_password'] = env_pw
    env_recv = get_env('recipient_email')
    if env_recv:
        email['recipient_email'] = [r.strip() for r in re.split('[,;]', env_recv) if r.strip()]
    if get_env('imap_server'):
        cfg['imap_server'] = get_env('imap_server')
    if get_env('smtp_server'):
        cfg['smtp_server'] = get_env('smtp_server')
    for port_key in ('imap_port', 'smtp_port'):
        raw = get_env(port_key)
        if raw:
            try:
                cfg[port_key] = int(raw)
            except ValueError:
                pass
    if get_env('mailbox_name'):
        cfg.setdefault('analysis', {})['mailbox_name'] = get_env('mailbox_name')
    return cfg


def config_source():
    if any(get_env(k) for k in ('sender_email', 'sender_password', 'recipient_email')):
        return 'plugin_settings'  # 插件高级设置（可视化界面）
    if load_file_config():
        return 'config_file'
    return 'none'


def missing_fields(config):
    missing = []
    email_cfg = (config or {}).get('email', {})
    if _is_placeholder(email_cfg.get('sender_email')):
        missing.append('email.sender_email')
    if _is_placeholder(email_cfg.get('sender_password')):
        missing.append('email.sender_password')
    recipients = email_cfg.get('recipient_email')
    if isinstance(recipients, list):
        recipients = recipients[0] if recipients else None
    if _is_placeholder(recipients):
        missing.append('email.recipient_email')
    return missing


# ---------------------------------------------------------------- tools

def tool_get_status(_args):
    config = effective_config()
    email_cfg = config.get('email', {})
    missing = missing_fields(config)
    recipients = email_cfg.get('recipient_email')
    if isinstance(recipients, list):
        recipients = ', '.join(r for r in recipients if isinstance(r, str))
    text = json.dumps({
        'configured': not missing,
        'source': config_source(),
        'missing_fields': missing,
        'config_file_path': CONFIG_PATH,
        'sender_email': email_cfg.get('sender_email') if not _is_placeholder(email_cfg.get('sender_email')) else None,
        'recipient_email': recipients,
        'imap_server': config.get('imap_server'),
        'smtp_server': config.get('smtp_server'),
    }, ensure_ascii=False, indent=2)
    return {'text': text, 'isError': False}


def tool_save_config(args):
    sender_email = (args.get('sender_email') or '').strip()
    sender_password = args.get('sender_password') or ''
    recipient_email = args.get('recipient_email')
    if isinstance(recipient_email, str):
        recipient_email = [r.strip() for r in recipient_email.replace(';', ',').split(',') if r.strip()]
    if not isinstance(recipient_email, list) or not recipient_email:
        return {'text': '参数错误：recipient_email 必须为邮箱地址或地址列表', 'isError': True}

    problems = []
    if _is_placeholder(sender_email):
        problems.append('sender_email 是占位值，请填写真实邮箱地址')
    elif not EMAIL_RE.match(sender_email):
        problems.append('sender_email 格式不正确')
    if not sender_password or _is_placeholder(sender_password):
        problems.append('sender_password 是占位值，请填写 IMAP/SMTP 授权码')
    for r in recipient_email:
        if not EMAIL_RE.match(r):
            problems.append(f'收件人 {r} 格式不正确')
    if problems:
        return {'text': '配置未保存：\n- ' + '\n- '.join(problems), 'isError': True}

    config = load_file_config() or {}
    config['email'] = {
        'sender_email': sender_email,
        'sender_password': sender_password,
        'recipient_email': recipient_email,
    }
    config['imap_server'] = (args.get('imap_server') or config.get('imap_server') or 'imap.qq.com').strip()
    config['smtp_server'] = (args.get('smtp_server') or config.get('smtp_server') or 'smtp.qq.com').strip()
    config['imap_port'] = int(args.get('imap_port') or config.get('imap_port') or 993)
    config['smtp_port'] = int(args.get('smtp_port') or config.get('smtp_port') or 465)
    analysis = config.setdefault('analysis', {})
    if args.get('mailbox_name'):
        analysis['mailbox_name'] = args['mailbox_name'].strip()

    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    return {'text': (
        '邮箱配置已保存到: ' + CONFIG_PATH + '\n'
        'sender_email: ' + sender_email + '\n'
        'recipient_email: ' + ', '.join(recipient_email) + '\n'
        'IMAP: ' + config['imap_server'] + ':' + str(config['imap_port']) + '  SMTP: '
        + config['smtp_server'] + ':' + str(config['smtp_port']) + '\n'
        '（授权码已保存但不会在此显示）接下来可调用 analyze_12306_mail 运行分析。'
    ), 'isError': False}


def tool_analyze(args):
    missing = missing_fields(effective_config())
    if missing:
        return {'text': (
            '❌ 邮箱尚未配置，无法运行分析（缺少: ' + ', '.join(missing) + '）。\n'
            '请在可视化配置界面填写：' + UI_HINT + '。\n'
            '也可以调用 save_mail_config 工具保存配置（写入 ' + CONFIG_PATH + '），然后重试本工具。'
        ), 'isError': True}

    config = effective_config()
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(RUN_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    kwargs = {}
    if os.name == 'nt':
        kwargs['creationflags'] = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
            | getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
    else:
        kwargs['start_new_session'] = True

    with open(RUN_LOG_PATH, 'a', encoding='utf-8') as logf:
        logf.write('\n===== 分析任务启动 ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ' =====\n')
        logf.flush()
        proc = subprocess.Popen(
            [sys.executable, MAIN_PY, '--config', RUN_CONFIG_PATH],
            cwd=PLUGIN_DIR, stdout=logf, stderr=subprocess.STDOUT, **kwargs,
        )
    _log(f'analyze: started background pid={proc.pid}')
    return {'text': (
        '✅ 分析已在后台启动（进程 PID ' + str(proc.pid) + '）。\n'
        '邮件量大时耗时较长，请稍后调用 get_analysis_status 查看进度与最终结果（报告由后台任务自动发送）。\n'
        '运行日志: ' + RUN_LOG_PATH
    ), 'isError': False}


def tool_get_analysis_status(_args):
    if not os.path.exists(RUN_LOG_PATH):
        return {'text': json.dumps(
            {'state': '无运行记录', 'hint': '先调用 analyze_12306_mail 启动一次分析'},
            ensure_ascii=False, indent=2), 'isError': False}
    try:
        with open(RUN_LOG_PATH, encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception:
        content = ''
    marker = next((m for m in TERMINAL_MARKERS if m in content), None)
    lines = [l for l in content.strip().splitlines() if l.strip()]
    tail = '\n'.join(lines[-40:]) if lines else '(日志为空)'
    if marker == '所有任务完成':
        state = '已完成，报告已发送到收件邮箱'
    elif marker:
        state = '已结束：' + marker
    else:
        state = '运行中'
    return {'text': json.dumps({'state': state, 'log_tail': tail}, ensure_ascii=False, indent=2), 'isError': False}


TOOLS = [
    {
        'name': 'get_mail_config_status',
        'description': '查看 12306 邮件分析的邮箱配置状态：是否已配置、配置来源（插件高级设置界面或配置文件）、缺少哪些字段、当前发件/收件邮箱与服务器地址（不会返回授权码）。',
        'inputSchema': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'save_mail_config',
        'description': (
            '保存邮箱配置到用户配置文件（备用方式；首选是插件详情→高级设置的可视化界面）。'
            '需要：sender_email（读取 12306 邮件的邮箱）、sender_password（IMAP/SMTP 授权码，非登录密码）、'
            'recipient_email（报告收件人，单个邮箱字符串或列表）。可选：imap_server、imap_port、smtp_server、smtp_port、mailbox_name。'
            '未提供服务器参数时默认 QQ 邮箱（imap.qq.com:993 / smtp.qq.com:465）。'
        ),
        'inputSchema': {
            'type': 'object',
            'properties': {
                'sender_email': {'type': 'string', 'description': '邮箱地址'},
                'sender_password': {'type': 'string', 'description': 'IMAP/SMTP 授权码或应用专用密码'},
                'recipient_email': {
                    'anyOf': [
                        {'type': 'string'},
                        {'type': 'array', 'items': {'type': 'string'}},
                    ],
                    'description': '报告收件人邮箱，可多个',
                },
                'imap_server': {'type': 'string'},
                'imap_port': {'type': 'integer'},
                'smtp_server': {'type': 'string'},
                'smtp_port': {'type': 'integer'},
                'mailbox_name': {'type': 'string', 'description': 'IMAP 文件夹名，QQ 邮箱常用"网上购票"'},
            },
            'required': ['sender_email', 'sender_password', 'recipient_email'],
        },
    },
    {
        'name': 'analyze_12306_mail',
        'description': (
            '后台启动 12306 邮件分析：读取邮箱中的 12306 购票/退票/改签邮件 → 解析票务记录 → 生成 HTML 出行统计报告 → 通过 SMTP 发送到收件人邮箱。'
            '立即返回不等待完成，调用后请用 get_analysis_status 轮询进度和最终结果。邮箱未配置时直接拒绝执行并提示去插件高级设置界面配置。'
        ),
        'inputSchema': {
            'type': 'object',
            'properties': {},
        },
    },
    {
        'name': 'get_analysis_status',
        'description': '查看最近一次 12306 邮件分析任务的运行状态（运行中/已完成/已结束）与运行日志末尾。analyze_12306_mail 启动的是后台任务，用本工具轮询进度直到完成。',
        'inputSchema': {
            'type': 'object',
            'properties': {},
        },
    },
]


def call_tool(params):
    name = (params or {}).get('name')
    arguments = (params or {}).get('arguments') or {}
    if name == 'get_mail_config_status':
        return tool_get_status(arguments)
    if name == 'save_mail_config':
        return tool_save_config(arguments)
    if name == 'analyze_12306_mail':
        return tool_analyze(arguments)
    if name == 'get_analysis_status':
        return tool_get_analysis_status(arguments)
    return {'text': '未知工具: ' + str(name), 'isError': True}


# ---------------------------------------------------------------- protocol

def handle_request(msg_id, method, params):
    if method == 'initialize':
        return {
            'protocolVersion': '2024-11-05',
            'capabilities': {'tools': {}},
            'serverInfo': SERVER_INFO,
        }
    if method == 'ping':
        return {}
    if method == 'tools/list':
        return {'tools': TOOLS}
    if method == 'tools/call':
        result = call_tool(params)
        return {
            'content': [{'type': 'text', 'text': result['text']}],
            'isError': result['isError'],
        }
    raise ValueError('未知方法: ' + str(method))


def main():
    sys.stdin.reconfigure(encoding='utf-8', errors='replace')
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    _log(f'mail-analysis-12306 MCP server started, config file: {CONFIG_PATH}')
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception as e:
            _log(f'bad input: {e}')
            continue
        msg_id = msg.get('id')
        method = msg.get('method')
        params = msg.get('params') or {}
        if msg_id is None:
            continue  # notification
        try:
            result = handle_request(msg_id, method, params)
            response = {'jsonrpc': '2.0', 'id': msg_id, 'result': result}
        except Exception as e:
            _log(f'request {method} failed: {e}')
            response = {'jsonrpc': '2.0', 'id': msg_id, 'error': {'code': -32603, 'message': str(e)}}
        print(json.dumps(response, ensure_ascii=False), flush=True)
    _log('stdin closed, exiting')


if __name__ == '__main__':
    main()
