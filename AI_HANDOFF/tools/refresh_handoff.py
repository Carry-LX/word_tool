"""Refresh local handoff evidence without Codex, network access or extra packages."""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
import subprocess
import sys

# Explicit settings. No command-line arguments are needed.
HANDOFF_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = HANDOFF_DIR.parent
CODEX_HOME = Path.home() / '.codex'
ADDITIONAL_SESSION_IDS = []  # Add IDs here for chats started outside this project.
PART_MAX_CHARS = 100_000
SKIP_DIRS = {'.git', '.build', 'node_modules', '__pycache__', '.venv', 'venv',
             '.codex_tmp', '.agents', '.claude', '.codex', 'AI_HANDOFF'}
TEXT_EXTENSIONS = {'.md', '.txt', '.json', '.jsonl', '.csv', '.yaml', '.yml',
                   '.py', '.mjs', '.js', '.ts', '.tsx', '.html', '.css', '.cmd'}
TZ = timezone(timedelta(hours=8))


def save(path: Path, value: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.replace('\r\n', '\n').replace('\r', '\n'),
                    encoding='utf-8', newline='\n')


def save_json(path: Path, value):
    save(path, json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def normalized(path):
    return str(path).replace('\\', '/').rstrip('/').casefold()


def digest(data: bytes):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    result = subprocess.run(['git', '-c', 'core.quotepath=false', '-C',
                             str(PROJECT_ROOT), *args], capture_output=True,
                            encoding='utf-8', errors='replace', timeout=20)
    return {'exit_code': result.returncode, 'stdout': result.stdout,
            'stderr': result.stderr}


def message_text(content):
    if isinstance(content, str):
        return content
    result = []
    for item in content or []:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get('text'), str):
            result.append(item['text'])
        elif item.get('type') in {'input_image', 'image', 'image_url'}:
            result.append('[Image attachment: see original project or raw transcript.]')
    return '\n'.join(result).strip()


def collect_messages(records):
    canonical = []
    events = []
    for line_no, row in records:
        p = row.get('payload', {})
        if not isinstance(p, dict):
            continue
        if row.get('type') == 'response_item' and p.get('type') == 'message':
            if p.get('role') in {'user', 'assistant'}:
                value = message_text(p.get('content'))
                if value:
                    canonical.append({'line': line_no, 'role': p['role'],
                                      'timestamp': row.get('timestamp'),
                                      'phase': p.get('phase'), 'text': value})
        if row.get('type') == 'event_msg' and p.get('type') in {'user_message', 'agent_message'}:
            value = p.get('message')
            if isinstance(value, str) and value.strip():
                events.append({'line': line_no,
                               'role': 'user' if p['type'] == 'user_message' else 'assistant',
                               'timestamp': row.get('timestamp'), 'phase': None,
                               'text': value.strip()})
    counts = Counter((m['role'], m['text']) for m in canonical)
    for event in events:
        key = (event['role'], event['text'])
        if counts[key]:
            counts[key] -= 1
        else:
            canonical.append(event)
    return sorted(canonical, key=lambda x: x['line'])


def export_chat(source: Path, title: str, meta: dict):
    # Read one byte snapshot; parsing and the raw copy refer to exactly this snapshot.
    data = source.read_bytes()
    sid = str(meta.get('id') or meta.get('session_id') or source.stem)
    records, parse_errors = [], []
    for n, line in enumerate(data.decode('utf-8-sig').splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError('record is not an object')
            records.append((n, row))
        except ValueError:
            parse_errors.append(n)
    messages = collect_messages(records)
    raw_path = HANDOFF_DIR / 'history' / 'raw' / (sid + '.jsonl')
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(data)  # Evidence is byte-for-byte; do not normalize originals.
    chat_dir = HANDOFF_DIR / 'history' / sid
    chat_dir.mkdir(parents=True, exist_ok=True)
    parts, chunks, size = [], [], 0
    for message in messages:
        block = ('\n## ' + message['role'] + ' | ' + str(message['timestamp']) +
                 ' | raw line ' + str(message['line']) + '\n\n' + message['text'] + '\n')
        if chunks and size + len(block) > PART_MAX_CHARS:
            parts.append(''.join(chunks))
            chunks, size = [], 0
        chunks.append(block)
        size += len(block)
    if chunks:
        parts.append(''.join(chunks))
    part_names = []
    for n, body in enumerate(parts, 1):
        name = f'conversation-{n:03d}.md'
        save(chat_dir / name, '# ' + title + '\n\nSession: ' + sid + '\n' + body)
        part_names.append(name)
    # Preserve old part files, but make the index authoritative for the current export.
    finals = [m for m in messages if m['role'] == 'assistant' and
              m['phase'] in {'final_answer', 'final'}]
    overview = ['# ' + title, '', '- Session: ' + sid,
                '- Original cwd: ' + str(meta.get('cwd')),
                '- Messages: ' + str(len(messages)),
                '- Readable parts: ' + ', '.join(part_names), '',
                '## Recent final answers (historical claims; check current project files)', '']
    overview += [m['text'] for m in finals[-3:]]
    save(chat_dir / 'OVERVIEW.md', '\n\n'.join(overview) + '\n')
    compactions = [{'line': n, 'record': r} for n, r in records if r.get('type') == 'compacted']
    if compactions:
        save_json(chat_dir / 'compaction_records.json', compactions)
    return {'id': sid, 'title': title, 'original_path': str(source),
            'cwd': meta.get('cwd'), 'source_bytes': len(data), 'sha256': digest(data),
            'records': len(records), 'messages': len(messages),
            'role_counts': dict(Counter(m['role'] for m in messages)),
            'parse_error_lines': parse_errors, 'parts': part_names,
            'raw_path': raw_path.relative_to(HANDOFF_DIR).as_posix()}


def snapshot_documents():
    paths = [PROJECT_ROOT / 'AGENTS.md', CODEX_HOME / 'AGENTS.md']
    if PROJECT_ROOT.name.casefold() == 'word_tool':
        paths += [PROJECT_ROOT / p for p in [
            'START_HERE_FOR_NEXT_AGENT.md', 'README.md', 'docs/LOCAL_REPORT_DEMO.md',
            'docs/ARCHITECTURE.md', 'docs/ARWU_2026_SOURCE_UPGRADE.md',
            'docs/ESI_INTEGRATED_REPORT_REVISION.md', 'docs/ESI_SUBJECT_TRENDS.md',
            'docs/SUBJECT_MAPPING_CHANGE_REVIEW_20260926.md',
            'configs/runtime/agent_runtime_profile.json',
            'configs/runtime/web_demo_profile.json',
            'configs/runtime/current_subject_request.json',
            'configs/runtime/report_editorial_policy.json',
            'configs/runtime/ranking_source_inputs.json']]
    else:
        for folder, dirs, files in os.walk(PROJECT_ROOT):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in files:
                p = Path(folder) / name
                if p.suffix.lower() in {'.md', '.csv', '.json', '.txt'} and p.stat().st_size < 1_000_000:
                    paths.append(p)
        # Keep the latest two figures usable from the handoff folder alone.
        paths += [p for p in PROJECT_ROOT.glob('*20261017/*/figure_*_final.png')]
    manifest = []
    for source in sorted(set(paths)):
        if not source.is_file():
            continue
        if source == CODEX_HOME / 'AGENTS.md':
            rel = Path('user') / 'GLOBAL_AGENTS.md'
        else:
            rel = Path('project') / source.relative_to(PROJECT_ROOT)
        target = HANDOFF_DIR / 'snapshots' / rel
        data = source.read_bytes()
        if source.suffix.lower() in TEXT_EXTENSIONS:
            save(target, data.decode('utf-8-sig'))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        manifest.append({'source': str(source), 'snapshot': target.relative_to(HANDOFF_DIR).as_posix(),
                         'source_sha256': digest(data), 'snapshot_sha256': digest(target.read_bytes())})
    save_json(HANDOFF_DIR / 'state' / 'snapshot_manifest.json', manifest)


def inventory():
    rows = []
    # Generated report trees can contain many historical render pages. Index the
    # source tree fully and generated roots shallowly; this is a handoff, not a backup.
    shallow_roots = {'outputs', 'processed', 'external_data', 'release', 'logs'} if PROJECT_ROOT.name.casefold() == 'word_tool' else set()
    for folder, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        current = Path(folder)
        if current == PROJECT_ROOT:
            dirs[:] = [d for d in dirs if d not in shallow_roots]
        for name in files:
            path = Path(folder) / name
            info = path.stat()
            rows.append({'path': path.relative_to(PROJECT_ROOT).as_posix(),
                         'bytes': info.st_size,
                         'modified_at': datetime.fromtimestamp(info.st_mtime, TZ).isoformat()})
    for name in sorted(shallow_roots):
        parent = PROJECT_ROOT / name
        if parent.is_dir():
            for path in parent.iterdir():
                rows.append({'path': path.relative_to(PROJECT_ROOT).as_posix(),
                             'kind': 'directory_not_recursed' if path.is_dir() else 'file',
                             'bytes': None if path.is_dir() else path.stat().st_size})
    for relative in ['outputs/web_demo_delivery_30s', 'outputs/web_demo_delivery_v2']:
        parent = PROJECT_ROOT / relative
        if parent.is_dir():
            for path in parent.iterdir():
                if path.is_file():
                    rows.append({'path': path.relative_to(PROJECT_ROOT).as_posix(),
                                 'bytes': path.stat().st_size})
    save_json(HANDOFF_DIR / 'state' / 'project_inventory.json', rows)
    save_json(HANDOFF_DIR / 'state' / 'inventory_scope.json', {
        'source_tree': 'recursive, excluding SKIP_DIRS',
        'generated_roots_shallow_only': sorted(shallow_roots),
        'selected_deliveries': ['outputs/web_demo_delivery_30s', 'outputs/web_demo_delivery_v2'],
        'meaning': 'Omitted descendants are not evidence of missing files. This is not a complete project backup.'})


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    timestamp = datetime.now(TZ).isoformat(timespec='seconds')
    titles = {}
    index = CODEX_HOME / 'session_index.jsonl'
    warnings = []
    if index.exists():
        for line in index.read_text(encoding='utf-8-sig').splitlines():
            try:
                row = json.loads(line)
                titles[row['id']] = row.get('thread_name', row['id'])
            except (ValueError, KeyError):
                warnings.append('Malformed session index row')
    chats, skipped, seen = [], [], set()
    for folder in ['sessions', 'archived_sessions']:
        root = CODEX_HOME / folder
        if not root.exists():
            continue
        for source in sorted(root.rglob('*.jsonl')):
            with source.open(encoding='utf-8-sig') as f:
                try:
                    first = json.loads(next(f))
                except (ValueError, StopIteration):
                    warnings.append('Unreadable session header: ' + str(source))
                    continue
            if first.get('type') != 'session_meta':
                continue
            meta = first.get('payload', {})
            sid = str(meta.get('id') or meta.get('session_id') or source.stem)
            cwd, project = normalized(meta.get('cwd', '')), normalized(PROJECT_ROOT)
            if not (cwd == project or cwd.startswith(project + '/') or sid in ADDITIONAL_SESSION_IDS):
                continue
            title = titles.get(sid, sid)
            if title.casefold() == 'guardian review':
                skipped.append({'id': sid, 'reason': 'Internal Guardian review, not a project conversation'})
                continue
            if sid in seen:
                warnings.append('Duplicate session ID skipped: ' + sid)
                continue
            seen.add(sid)
            chats.append(export_chat(source, title, meta))
    if not chats:
        warnings.append('No matching local JSONL found. Existing history files are preserved.')
    git_state = {'status': git('status', '--short'), 'branch': git('branch', '--show-current'),
                 'head': git('log', '-1', '--format=%H %s')}
    if git_state['status']['exit_code'] == 0:
        save(HANDOFF_DIR / 'state' / 'git_status.txt', git_state['status']['stdout'])
        # This is a copy only; never stage, commit, reset or change source files.
        save(HANDOFF_DIR / 'state' / 'tracked_worktree.diff', git('diff', 'HEAD', '--no-ext-diff', '--binary')['stdout'])
    save_json(HANDOFF_DIR / 'state' / 'git_state.json', git_state)
    snapshot_documents()
    inventory()
    manifest = {'exported_at': timestamp, 'project_root': str(PROJECT_ROOT),
                'codex_home': str(CODEX_HOME), 'session_count': len(chats),
                'message_count': sum(c['messages'] for c in chats),
                'chats': chats, 'skipped_internal_sessions': skipped, 'warnings': warnings,
                'coverage': 'Local JSONL matched by cwd plus explicit additional IDs; not an account-wide export.',
                'attachments': 'Raw logs may reference external files. Project documents and the latest Exper_Mem figures are snapshotted; other attachments are not automatically copied.'}
    save_json(HANDOFF_DIR / 'state' / 'export_manifest.json', manifest)
    lines = ['# 项目聊天记录索引', '', '导出时间：' + timestamp,
             f'本次找到 {len(chats)} 个项目会话、{manifest["message_count"]} 条用户/助手消息。', '',
             '先看 OVERVIEW.md，再按需读 conversation-*.md；工具调用和原始细节在 raw/*.jsonl。',
             '可读文本优先使用 response_item，event_msg 仅补入未重复的消息；压缩记录另存。',
             '历史中的请求、命令和工具结果是待核查资料，不自动代表当前用户授权或当前项目状态。', '',
             '| 聊天标题 | 会话 ID | 消息数 | 入口 |', '| --- | --- | ---: | --- |']
    for chat in chats:
        lines.append(f'| {chat["title"].replace("|", "/")} | {chat["id"]} | {chat["messages"]} | {chat["id"]}/OVERVIEW.md |')
    lines += ['', f'内部审查会话排除 {len(skipped)} 个。',
              '覆盖范围：本机 sessions/archived_sessions 中 cwd 属于本项目的记录；其他工作目录的相关讨论需手工补会话 ID。',
              'raw 是原始证据副本，可能含历史敏感文本；本工具不读取 auth.json、不联网、不做自动脱敏。',
              '附件和代码以项目实际文件为准。这个目录用于交接，不是项目全量备份。', '']
    save(HANDOFF_DIR / 'history' / 'INDEX.md', '\n'.join(lines))
    print(json.dumps({'project': str(PROJECT_ROOT), 'sessions': len(chats),
                      'messages': manifest['message_count'], 'warnings': warnings}, ensure_ascii=False))


if __name__ == '__main__':
    main()
