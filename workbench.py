"""Deterministic, supplied-response evaluation. No model or judge calls."""
import csv
import hashlib
import io
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import database


class Check(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    kind: Literal['exact_match', 'contains', 'not_contains', 'valid_json']
    value: str = Field(default='', max_length=10000)
    case_sensitive: bool = False

    @model_validator(mode='after')
    def valid_value(self):
        if self.kind != 'valid_json' and not self.value.strip():
            raise ValueError('Text checks need a nonblank value.')
        if self.kind == 'valid_json' and self.value:
            raise ValueError('valid_json does not accept a value.')
        return self


class Case(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    case_id: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=10000)
    response: str = Field(max_length=20000)
    checks: list[Check] = Field(min_length=1, max_length=20)

    @field_validator('case_id', 'prompt')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Must not be blank.')
        return value


class RunInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    name: str = Field(min_length=1, max_length=100)
    agent_version: str = Field(min_length=1, max_length=100)
    cases: list[Case] = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def validate_run(self):
        if not self.name.strip() or not self.agent_version.strip():
            raise ValueError('Run name and agent version must not be blank.')
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError('Case IDs must be unique within a run.')
        return self


def parse_dataset(raw: bytes, filename: str) -> list[Case]:
    if len(raw) > 5_000_000:
        raise ValueError('Dataset exceeds the 5 MB limit.')
    content = raw.decode('utf-8-sig')
    if filename.lower().endswith('.json'):
        rows = json.loads(content)
    elif filename.lower().endswith('.csv'):
        reader = csv.DictReader(io.StringIO(content))
        if reader.fieldnames != ['case_id', 'prompt', 'response', 'checks']:
            raise ValueError('CSV headers must be case_id,prompt,response,checks in that order.')
        rows = []
        for row in reader:
            row['checks'] = json.loads(row['checks'])
            rows.append(row)
    else:
        raise ValueError('Choose a JSON or CSV file.')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 500:
        raise ValueError('Dataset must contain 1–500 cases.')
    cases = [Case.model_validate(row) for row in rows]
    RunInput(name='validation', agent_version='validation', cases=cases)
    return cases


def initialize_runs():
    database.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database.DB_PATH)) as connection:
        connection.execute('''CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            payload TEXT NOT NULL
        )''')
        connection.commit()


def reject_constant(value):
    raise ValueError(f'Nonstandard JSON constant: {value}')


def check_response(response: str, check: Check) -> dict:
    actual = response if check.case_sensitive else response.casefold()
    expected = check.value if check.case_sensitive else check.value.casefold()
    if check.kind == 'exact_match':
        passed = actual.strip() == expected.strip()
        evidence = f'Expected whole response: {check.value!r} (outer whitespace ignored).'
    elif check.kind == 'contains':
        passed = expected in actual
        evidence = f'Required substring: {check.value!r}.'
    elif check.kind == 'not_contains':
        passed = expected not in actual
        evidence = f'Forbidden substring: {check.value!r}.'
    else:
        try:
            json.loads(response, parse_constant=reject_constant)
            passed, evidence = True, 'Response parses as JSON.'
        except (ValueError, RecursionError):
            passed, evidence = False, 'Response is not valid JSON.'
    return {**check.model_dump(), 'passed': passed, 'evidence': evidence}


def create_run(request: RunInput) -> dict:
    results = []
    for case in request.cases:
        checks = [check_response(case.response, check) for check in case.checks]
        passed = all(check['passed'] for check in checks)
        results.append({**case.model_dump(), 'checks': checks,
                        'status': 'pass' if passed else 'fail',
                        'score': sum(c['passed'] for c in checks) / len(checks)})
    # Definition hash excludes responses, run name, and agent version. Order is irrelevant.
    definition = sorted([{'case_id': c.case_id, 'prompt': c.prompt,
                          'checks': [x.model_dump() for x in c.checks]}
                         for c in request.cases], key=lambda c: c['case_id'])
    fingerprint = hashlib.sha256(json.dumps(definition, sort_keys=True).encode()).hexdigest()
    passed_count = sum(r['status'] == 'pass' for r in results)
    run = {'run_id': str(uuid4()), 'name': request.name,
           'agent_version': request.agent_version,
           'created_at': datetime.now(timezone.utc).isoformat(),
           'evaluator_version': 'deterministic-v1', 'mode': 'supplied_responses',
           'dataset_fingerprint': fingerprint, 'total': len(results),
           'passed': passed_count, 'failed': len(results) - passed_count,
           'pass_rate_percent': round(100 * passed_count / len(results), 2),
           'results': results}
    with closing(sqlite3.connect(database.DB_PATH)) as connection:
        with connection:
            connection.execute('INSERT INTO runs VALUES (?, ?, ?)',
                               (run['run_id'], run['created_at'], json.dumps(run)))
    return run


def list_runs():
    with closing(sqlite3.connect(database.DB_PATH)) as connection:
        rows = connection.execute('SELECT payload FROM runs ORDER BY created_at DESC').fetchall()
    return [{k: v for k, v in json.loads(row[0]).items() if k != 'results'} for row in rows]


def get_run(run_id):
    with closing(sqlite3.connect(database.DB_PATH)) as connection:
        row = connection.execute('SELECT payload FROM runs WHERE run_id = ?', (run_id,)).fetchone()
    if row is None:
        raise KeyError(run_id)
    return json.loads(row[0])


def compare_runs(baseline_id, candidate_id):
    baseline, candidate = get_run(baseline_id), get_run(candidate_id)
    if baseline_id == candidate_id:
        raise ValueError('Select two different runs.')
    if (baseline['dataset_fingerprint'], baseline['evaluator_version']) != (
            candidate['dataset_fingerprint'], candidate['evaluator_version']):
        raise ValueError('Runs must use identical case IDs, prompts, checks, and evaluator versions.')
    previous = {r['case_id']: r for r in baseline['results']}
    changes = [{'case_id': r['case_id'], 'baseline': previous[r['case_id']]['status'],
                'candidate': r['status'],
                'change': ('unchanged' if previous[r['case_id']]['status'] == r['status'] else
                           'regression' if r['status'] == 'fail' else 'improvement')}
               for r in candidate['results']]
    return {'baseline_id': baseline_id, 'candidate_id': candidate_id,
            'delta_percentage_points': round(100 * (candidate['passed'] / candidate['total'] - baseline['passed'] / baseline['total']), 2),
            'regressions': sum(c['change'] == 'regression' for c in changes),
            'improvements': sum(c['change'] == 'improvement' for c in changes), 'cases': changes}
