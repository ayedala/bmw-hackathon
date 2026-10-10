"""Local review interface. Run: python web.py"""
import json
import os
import subprocess
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'output'
LOCK = threading.Lock()
STATE = {'running': False, 'log': '', 'exit_code': None}


def execute_upload(upload, run):
    from upload_research import process
    def log(message):
        with LOCK:
            STATE['log'] = (STATE['log'] + message + '\n')[-30000:]
    try:
        code = process(upload, OUTPUT / run, log)
    except Exception as error:
        from agent import safe_error
        log(safe_error(error))
        code = 1
    finally:
        with LOCK:
            STATE.update(running=False, exit_code=locals().get('code', 1))


def run_directory(name):
    path = (OUTPUT / name).resolve()
    if not path.is_relative_to(OUTPUT.resolve()):
        raise ValueError('Invalid run path')
    return path


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else []


def execute(command):
    try:
        environment = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
        local_dependencies = ROOT / '.test-deps'
        if local_dependencies.is_dir():
            environment['PYTHONPATH'] = str(local_dependencies) + (
                os.pathsep + environment['PYTHONPATH'] if environment.get('PYTHONPATH') else '')
        process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                                   env=environment)
        for line in process.stdout:
            with LOCK:
                STATE['log'] = (STATE['log'] + line)[-30000:]
        with LOCK:
            STATE['exit_code'] = process.wait()
    except Exception as error:
        with LOCK:
            STATE.update(log=str(error), exit_code=1)
    finally:
        with LOCK:
            STATE['running'] = False


class Handler(BaseHTTPRequestHandler):
    def reply(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        try:
            if url.path == '/':
                body = (ROOT / 'frontend' / 'index.html').read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(body)
            elif url.path == '/api/runs':
                runs = sorted({str(p.parent.relative_to(OUTPUT)).replace('\\', '/')
                               for p in OUTPUT.rglob('sources.json')}) if OUTPUT.exists() else []
                self.reply(runs)
            elif url.path == '/api/results':
                path = run_directory(query.get('run', ['.'])[0])
                self.reply({'sources': read_json(path / 'sources.json'),
                            'evidence': read_json(path / 'evidence.json'),
                            'summary': (path / 'summary.md').read_text(encoding='utf-8')
                            if (path / 'summary.md').exists() else ''})
            elif url.path == '/api/transcript':
                video = query.get('video', [''])[0]
                if not video or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in video):
                    raise ValueError('Invalid video ID')
                path = run_directory(query.get('run', ['.'])[0])
                self.reply(read_json(path / 'transcripts' / (video + '.json')))
            elif url.path == '/api/status':
                with LOCK:
                    self.reply(dict(STATE))
            else:
                self.reply({'error': 'Not found'}, 404)
        except (ValueError, OSError) as error:
            self.reply({'error': str(error)}, 400)

    def do_POST(self):
        # Local browser only: reject cross-origin requests before starting work.
        if self.headers.get('Origin') != 'http://' + self.headers.get('Host', ''):
            self.reply({'error': 'Open the interface on this local server to start research.'}, 403)
            return
        if self.path == '/api/upload':
            try:
                from upload_research import Upload
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 34 * 1024 * 1024:
                    raise ValueError('Upload must be at most 24 MiB.')
                upload = Upload.parse(json.loads(self.rfile.read(length)))
                run = 'upload-' + uuid.uuid4().hex[:12]
                with LOCK:
                    if STATE['running']:
                        self.reply({'error': 'Research is already running'}, 409)
                        return
                    STATE.update(running=True, log='', exit_code=None, run=run)
                threading.Thread(target=execute_upload, args=(upload, run), daemon=True).start()
                self.reply({'started': True, 'run': run})
            except (ValueError, TypeError) as error:
                self.reply({'error': str(error)}, 400)
            return
        if self.path != '/api/run':
            self.reply({'error': 'Not found'}, 404)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length < 10000:
                raise ValueError('Invalid request size')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Expected form data')
            command = [sys.executable, '-u', str(ROOT / 'agent.py'), '--out', str(OUTPUT / 'browser')]
            fields = ('vehicle', 'generation', 'market', 'region', 'from-date', 'to-date', 'max-videos')
            for field in fields:
                value = str(data.get(field, '')).strip()
                if not value or value.startswith('-'):
                    raise ValueError(f'Please provide {field}')
                command.extend(['--' + field, value])
            languages = str(data.get('languages', '')).split()
            if not languages or any(not x.isalpha() or len(x) not in (2, 3) for x in languages):
                raise ValueError('Use language codes separated by spaces, such as en de')
            command.extend(['--languages', *languages])
            if data.get('probe'):
                command.append('--probe-only')
            with LOCK:
                if STATE['running']:
                    self.reply({'error': 'Research is already running'}, 409)
                    return
                STATE.update(running=True, log='', exit_code=None, run='browser')
            threading.Thread(target=execute, args=(command,), daemon=True).start()
            self.reply({'started': True})
        except (ValueError, TypeError) as error:
            self.reply({'error': str(error)}, 400)


if __name__ == '__main__':
    print('Open http://127.0.0.1:8765 to review your research.', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8765), Handler).serve_forever()
