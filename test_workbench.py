import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
import database
import workbench as w
from main import app

ROOT = Path(__file__).resolve().parent


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'test.db')
    with TestClient(app) as client:
        yield client


def payload(name='baseline'):
    return {'name': name, 'agent_version': name,
            'cases': json.loads((ROOT / 'data' / f'{name}.json').read_text())}


def test_sample_comparison_and_restart_persistence(client):
    a = client.post('/runs', json=payload())
    b = client.post('/runs', json=payload('candidate'))
    assert a.status_code == b.status_code == 201
    a, b = a.json(), b.json()
    assert (a['total'], a['passed'], b['passed']) == (12, 7, 11)
    comparison = client.get('/compare', params={'baseline_id': a['run_id'], 'candidate_id': b['run_id']}).json()
    assert comparison['regressions'] == 1
    assert comparison['improvements'] == 5
    assert comparison['delta_percentage_points'] == 33.33
    assert next(c for c in comparison['cases'] if c['change'] == 'regression')['case_id'] == 'TC-007'
    with TestClient(app) as restarted:
        assert len(restarted.get('/runs').json()) == 2
        assert restarted.get('/runs/' + a['run_id']).json() == a
    assert client.get('/evaluations').json() == []


@pytest.mark.parametrize('response,check,expected', [
    (' YES ', {'kind':'exact_match','value':'yes'}, True),
    ('YES', {'kind':'exact_match','value':'yes','case_sensitive':True}, False),
    ('yesterday', {'kind':'exact_match','value':'yes'}, False),
    ('A café', {'kind':'contains','value':'CAFÉ'}, True),
    ('not a guaranteed cure', {'kind':'not_contains','value':'guaranteed cure'}, False),
    ('', {'kind':'contains','value':'hello'}, False),
    ('{"a":1}', {'kind':'valid_json'}, True),
    ('NaN', {'kind':'valid_json'}, False),
    ('{"a":Infinity}', {'kind':'valid_json'}, False),
    ('```json\n{}\n```', {'kind':'valid_json'}, False),
])
def test_checks(response,check,expected):
    assert w.check_response(response,w.Check(**check))['passed'] is expected


@pytest.mark.parametrize('mutation', ['duplicate','blank','invalid_check','no_cases','extra','bad_type'])
def test_invalid_run_not_saved(client, mutation):
    data = payload()
    if mutation == 'duplicate': data['cases'].append(data['cases'][0])
    if mutation == 'blank': data['name'] = ' '
    if mutation == 'invalid_check': data['cases'][0]['checks'][0]['value'] = ''
    if mutation == 'no_cases': data['cases'] = []
    if mutation == 'extra': data['unknown'] = True
    if mutation == 'bad_type': data['cases'][0]['checks'][0]['case_sensitive'] = 'false'
    assert client.post('/runs', json=data).status_code == 422
    assert client.get('/runs').json() == []


def test_compare_rejects_changed_definitions(client):
    a = client.post('/runs', json=payload()).json()['run_id']
    data = payload('candidate')
    data['cases'][0]['prompt'] = 'A different task'
    b = client.post('/runs', json=data).json()['run_id']
    assert client.get('/compare',params={'baseline_id':a,'candidate_id':b}).status_code == 422
    assert client.get('/compare',params={'baseline_id':a,'candidate_id':a}).status_code == 422
    assert client.get('/runs/missing').status_code == 404
    assert client.get('/compare',params={'baseline_id':a,'candidate_id':'missing'}).status_code == 404


def test_dataset_imports_match():
    a = w.parse_dataset((ROOT/'data/baseline.json').read_bytes(),'baseline.json')
    b = w.parse_dataset((ROOT/'data/baseline.csv').read_bytes(),'baseline.csv')
    assert a == b


@pytest.mark.parametrize('data,name', [(b'{}','a.json'), (b'[]','a.json'), (b'bad','a.json'),
    (b'case_id,prompt,response,checks\na,b,c,invalid','a.csv'), (b'other\n1','a.csv'),
    (b'hello','a.txt'), pytest.param(b'x'*5_000_001, 'a.json', id='oversized-dataset')])
def test_bad_dataset(data,name):
    with pytest.raises(ValueError): w.parse_dataset(data,name)


def test_database_error_is_useful(client, monkeypatch):
    def fail(_): raise sqlite3.OperationalError('locked')
    monkeypatch.setattr(w,'create_run',fail)
    result = client.post('/runs',json=payload())
    assert result.status_code == 503
    assert 'Database unavailable' in result.json()['detail']


def test_all_checks_must_pass(client):
    data = payload()
    data['cases'] = data['cases'][:1]
    data['cases'][0]['checks'].append({'kind':'contains','value':'wrong'})
    result = client.post('/runs',json=data).json()
    assert result['passed'] == 0
    assert result['results'][0]['score'] == 0.5
