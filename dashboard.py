"""Run with: python -m streamlit run dashboard.py"""
import json
import os
from pathlib import Path

import requests
import streamlit as st
from workbench import parse_dataset

ROOT = Path(__file__).resolve().parent
API = os.environ.get('EVALFORGE_API_URL', 'http://127.0.0.1:8000').rstrip('/')
st.set_page_config(page_title='EvalForge | AI evaluation workbench', page_icon='◈', layout='wide')
st.title('EvalForge')
st.markdown('### Know how your AI actually performs.')
st.caption('Evaluate supplied responses • Inspect the evidence • Catch regressions')


def api(method, path, **kwargs):
    try:
        response = requests.request(method, API + path, timeout=30, **kwargs)
        if not response.ok:
            st.error(f'API error {response.status_code}: {response.json().get("detail", response.text)}')
            return None
        return response.json()
    except (requests.RequestException, ValueError):
        st.error('Cannot reach the evaluation API. Start it with: python -m uvicorn main:app --reload')
        return None


with st.sidebar:
    st.header('Evaluation workbench')
    st.info('Local MVP · Supplied responses')
    st.write('Checks are deterministic rules. A passing result does not establish factual accuracy or safety.')
    st.caption('All bundled examples are synthetic.')
    st.link_button('API documentation', API + '/docs')

run_tab, inspect_tab, compare_tab = st.tabs(['01 · Run evaluations', '02 · Inspect results', '03 · Compare runs'])
with run_tab:
    st.subheader('Start an evaluation run')
    source = st.radio('Dataset', ['Sample baseline', 'Sample candidate', 'Upload JSON or CSV'], horizontal=True)
    raw, filename = None, None
    if source.startswith('Sample'):
        filename = 'baseline.json' if source == 'Sample baseline' else 'candidate.json'
        raw = (ROOT / 'data' / filename).read_bytes()
        st.download_button('Download this dataset', raw, file_name=filename, mime='application/json')
    else:
        uploaded = st.file_uploader('Evaluation dataset', type=['json', 'csv'])
        if uploaded:
            raw, filename = uploaded.getvalue(), uploaded.name
    cases = None
    if raw is not None:
        try:
            cases = parse_dataset(raw, filename)
            st.caption(f'{len(cases)} validated cases · Every check must pass for a case to pass.')
            with st.expander('Preview dataset'):
                st.dataframe([{'case_id': c.case_id, 'prompt': c.prompt, 'response': c.response,
                               'checks': len(c.checks)} for c in cases], hide_index=True, width='stretch')
        except (ValueError, TypeError, RecursionError) as exc:
            st.error(f'Dataset validation failed: {exc}')
    with st.form('new_run'):
        name = st.text_input('Run name', value='My evaluation run', max_chars=100)
        version = st.text_input('Agent / response version', value='v1', max_chars=100)
        submitted = st.form_submit_button('Evaluate and save', type='primary', disabled=cases is None)
    if submitted and cases is not None:
        result = api('POST', '/runs', json={'name': name, 'agent_version': version,
                                          'cases': [c.model_dump() for c in cases]})
        if result:
            st.success(f'Saved {result["name"]}: {result["passed"]}/{result["total"]} cases passed.')
            st.session_state['last_run'] = result['run_id']

runs = api('GET', '/runs')
if runs is not None:
    labels = {r['run_id']: f'{r["name"]} · {r["agent_version"]} · {r["created_at"][:19]} UTC · {r["run_id"][:8]}' for r in runs}
    ids = list(labels)
    with inspect_tab:
        st.subheader('Results and evidence')
        if not runs:
            st.info('Save a run to inspect its results here.')
        else:
            selected = st.selectbox('Saved run', ids, format_func=labels.get)
            run = api('GET', '/runs/' + selected)
            if run:
                cols = st.columns(4)
                for col, label, value in zip(cols, ['Cases', 'Passed', 'Failed', 'Pass rate'],
                                             [run['total'], run['passed'], run['failed'], f'{run["pass_rate_percent"]}%']):
                    col.metric(label, value)
                st.download_button('Export full results (JSON)', json.dumps(run, indent=2),
                                   file_name=f'evalforge-{selected}.json', mime='application/json')
                failures_only = st.checkbox('Show only failing cases')
                shown = [r for r in run['results'] if not failures_only or r['status'] == 'fail']
                st.dataframe([{'Case': r['case_id'], 'Status': r['status'],
                               'Checks passed': f'{sum(c["passed"] for c in r["checks"])}/{len(r["checks"])}'}
                              for r in shown], hide_index=True, width='stretch')
                for row in shown:
                    with st.expander(f'{row["case_id"]} · {row["status"].upper()}'):
                        st.caption('Prompt')
                        st.text(row['prompt'])
                        st.caption('Supplied response')
                        st.code(row['response'], language=None)
                        st.dataframe(row['checks'], hide_index=True, width='stretch')
    with compare_tab:
        st.subheader('Did the candidate improve?')
        st.caption('Comparisons require identical test definitions. Delta is candidate minus baseline.')
        if len(runs) < 2:
            st.info('Save both sample runs to compare them.')
        else:
            base = st.selectbox('Baseline run', ids, index=1, format_func=labels.get)
            options = [r for r in ids if r != base]
            candidate = st.selectbox('Candidate run', options, format_func=labels.get)
            if st.button('Compare selected runs', type='primary'):
                comparison = api('GET', '/compare', params={'baseline_id': base, 'candidate_id': candidate})
                if comparison:
                    a, b, c = st.columns(3)
                    a.metric('Pass-rate change', f'{comparison["delta_percentage_points"]:+.2f} pp')
                    b.metric('Regressions', comparison['regressions'])
                    c.metric('Improvements', comparison['improvements'])
                    st.dataframe(comparison['cases'], hide_index=True, width='stretch')
