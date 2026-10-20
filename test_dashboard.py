"""Exercise the Streamlit UI against a real local API and temporary database."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import requests
from streamlit.testing.v1 import AppTest


def test_dashboard_workflow(tmp_path, monkeypatch):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    monkeypatch.setenv('EVALFORGE_API_URL', url)
    env = {**os.environ, 'EVALFORGE_DB': str(tmp_path/'dashboard.db')}
    root = Path(__file__).resolve().parent
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'main:app', '--port', str(port)],
                               cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                if requests.get(url+'/health', timeout=1).ok: break
            except requests.RequestException: pass
            time.sleep(.1)
        else: raise AssertionError('API did not start')
        at = AppTest.from_file(str(root/'dashboard.py'), default_timeout=20).run()
        assert not at.exception and not at.error
        at.button(key='FormSubmitter:new_run-Evaluate and save').click().run()
        assert at.success and not at.error and not at.exception
        at.radio[0].set_value('Sample candidate').run()
        at.button(key='FormSubmitter:new_run-Evaluate and save').click().run()
        assert at.success and not at.error and not at.exception
        next(b for b in at.button if b.label=='Compare selected runs').click().run()
        assert not at.exception and not at.error
        assert any(m.value == '+33.33 pp' for m in at.metric)
        assert any(m.label == 'Regressions' and m.value == '1' for m in at.metric)
        at.checkbox[0].check().run()
        assert not at.exception
    finally:
        process.terminate()
        process.wait(timeout=10)
    at.run()
    assert any('Cannot reach' in error.value for error in at.error)
    assert not at.exception
