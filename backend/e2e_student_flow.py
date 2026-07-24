"""E2E smoke: registration → login → test → finish → result → history."""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = 'http://127.0.0.1:8000/api'
results = []


def req(method, path, data=None, token=None):
    url = BASE + path
    body = None
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    if data is not None:
        body = json.dumps(data).encode('utf-8')
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as resp:
            raw = resp.read().decode('utf-8')
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8')
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {'raw': raw[:500]}
        return e.code, payload
    except Exception as e:
        return 0, {'error': str(e)}


def step(name, ok, detail=''):
    results.append((name, ok, detail))
    mark = 'OK' if ok else 'FAIL'
    print(f'[{mark}] {name}' + (f' — {detail}' if detail else ''))


def main():
    # 1. Public subjects for registration
    code, data = req('GET', '/subjects/for-registration/')
    step(
        'for-registration',
        code == 200 and isinstance(data, list) and len(data) > 0,
        f'status={code} n={len(data) if isinstance(data, list) else data}',
    )
    subjects = data if isinstance(data, list) else []
    subj = next(
        (s for s in subjects if s.get('slug') in ('math', 'history', 'physics', 'biology')),
        subjects[0] if subjects else None,
    )
    step('pick subject', bool(subj), subj.get('name') if subj else None)

    # 2. Register (role teacher must be forced to student)
    uname = f'e2e_student_{int(time.time())}'
    prof_ids = [s['id'] for s in subjects if s.get('subject_type') == 'profile'][:2]
    if not prof_ids and subj:
        prof_ids = [subj['id']]

    code, data = req('POST', '/auth/register/', {
        'username': uname,
        'email': f'{uname}@test.local',
        'password': 'TestPass123!',
        'password_confirm': 'TestPass123!',
        'full_name': 'E2E Student',
        'school': 'Test School',
        'role': 'teacher',
        'profile_subjects': prof_ids,
    })
    reg_user = data.get('user') or {}
    step('register', code == 201, f'status={code} body={str(data)[:220]}')
    step('register forces student role', reg_user.get('role') == 'student', f'got {reg_user.get("role")}')

    # 3. Login
    code, data = req('POST', '/auth/login/', {
        'username': uname,
        'password': 'TestPass123!',
    })
    token = data.get('access')
    step('login', code == 200 and bool(token), f'status={code}')

    # 4. Profile
    code, data = req('GET', '/auth/profile/', token=token)
    step('profile', code == 200 and data.get('role') == 'student',
         f'status={code} role={data.get("role")}')

    # 5. Subjects list
    code, data = req('GET', '/subjects/', token=token)
    if isinstance(data, dict) and 'results' in data:
        subjects_auth = data['results']
    else:
        subjects_auth = data if isinstance(data, list) else []
    step('subjects list', code == 200 and len(subjects_auth) > 0,
         f'status={code} n={len(subjects_auth)}')
    kazakh = [s.get('name') for s in subjects_auth if 'Казахская литература' in (s.get('name') or '')]
    step('kazakh lit hidden', len(kazakh) == 0, str(kazakh))

    # 6. Start short subject test
    test_subj = next(
        (s for s in subjects_auth if s.get('slug') == 'history' or 'История Казахстана' in (s.get('name') or '')),
        subjects_auth[0] if subjects_auth else subj,
    )
    code, data = req('POST', '/tests/start/', {
        'subject_id': test_subj['id'],
        'num_questions': 5,
    }, token=token)
    session_id = data.get('session_id')
    questions = data.get('questions') or []
    step(
        'start test',
        code == 200 and bool(session_id) and len(questions) == 5,
        f'status={code} err={data.get("error")} session={session_id} nq={len(questions)} tl={data.get("time_limit")}',
    )

    # 7. Answer each question
    answered_ok = 0
    for q in questions:
        answers = q.get('answers') or []
        if not answers:
            print(f'  question {q.get("id")} has no answers')
            continue
        aid = answers[0].get('id')
        code, ad = req('POST', f'/tests/{session_id}/answer/', {
            'question': q['id'],
            'selected_answer': aid,
        }, token=token)
        if code == 200:
            answered_ok += 1
        else:
            print(f'  answer fail q={q["id"]}: {code} {ad}')
    step('submit answers', answered_ok == len(questions) and len(questions) > 0,
         f'{answered_ok}/{len(questions)}')

    # 8. State mid-test
    code, data = req('GET', f'/tests/{session_id}/state/', token=token)
    step(
        'test state',
        code == 200 and data.get('is_completed') is False and len(data.get('answered') or []) == 5,
        f'status={code} answered={data.get("answered")} left={data.get("time_left")}',
    )

    # 9. Finish
    code, data = req('POST', f'/tests/{session_id}/finish/', token=token)
    step(
        'finish test',
        code == 200 and data.get('session_id') == session_id,
        f'status={code} score={data.get("score_percent")} '
        f'correct={data.get("correct_answers")}/{data.get("total_questions")}',
    )

    # 10. Result detail
    code, data = req('GET', f'/tests/{session_id}/result/', token=token)
    step('result', code == 200, f'status={code} keys={list(data.keys()) if isinstance(data, dict) else data}')
    review_fields = []
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, list) and v:
                sample = v[0]
                review_fields.append(k)
                if isinstance(sample, dict):
                    print(f'  result.{k}: n={len(v)} keys={list(sample.keys())}')
    has_review = any(k in review_fields for k in ('answers', 'answer_records', 'details', 'questions'))
    # Also accept nested under session detail serializer field names
    if not has_review and isinstance(data, dict):
        has_review = 'answers' in data or 'score_percent' in data
    step('result usable for ResultsPage', code == 200 and isinstance(data, dict) and 'score_percent' in data,
         f'review_lists={review_fields}')

    # 11. History
    code, data = req('GET', '/tests/history/', token=token)
    hist = data if isinstance(data, list) else (data.get('results') if isinstance(data, dict) else [])
    hist = hist or []
    step('history', code == 200 and any(s.get('id') == session_id for s in hist),
         f'status={code} n={len(hist)}')

    # 12. Student dashboard
    code, data = req('GET', '/dashboard/student/', token=token)
    step('student dashboard', code == 200,
         f'status={code} keys={list(data.keys())[:12] if isinstance(data, dict) else type(data)}')

    # 13. Bulk answer path
    code, data = req('POST', '/tests/start/', {
        'subject_id': test_subj['id'],
        'num_questions': 3,
    }, token=token)
    sid2 = data.get('session_id')
    qs2 = data.get('questions') or []
    bulk = []
    for q in qs2:
        ans = (q.get('answers') or [{}])[0]
        aid = ans.get('id')
        if aid:
            bulk.append({
                'question': q['id'],
                'selected_answer': aid,
                'selected_answers': [aid],
            })
    code, data = req('POST', f'/tests/{sid2}/answers/bulk/', {'answers': bulk}, token=token)
    step('bulk answers', code == 200, f'status={code} body={data}')
    code, data = req('POST', f'/tests/{sid2}/finish/', token=token)
    step('finish bulk session', code == 200, f'score={data.get("score_percent")}')

    # 14. Double finish should fail
    code, data = req('POST', f'/tests/{sid2}/finish/', token=token)
    step('double finish rejected', code == 400, f'status={code} {data}')

    # 15. ENT start (may fail if not enough questions — report only)
    profiles = [s for s in subjects_auth if s.get('subject_type') == 'profile' and s.get('show_in_profiles', True)]
    if len(profiles) >= 2:
        code, data = req('POST', '/tests/start-ent/', {
            'profile1_id': profiles[0]['id'],
            'profile2_id': profiles[1]['id'],
        }, token=token)
        step(
            'start ENT',
            code == 200 and data.get('session_id'),
            f'status={code} err={data.get("error")} nq={data.get("total_questions")} '
            f'sections={len(data.get("sections") or [])}',
        )
        # don't finish full ENT in smoke — just ensure start works, then abandon
    else:
        step('start ENT', False, 'not enough profile subjects')

    print()
    fails = [r for r in results if not r[1]]
    print(f'SUMMARY: {len(results) - len(fails)}/{len(results)} passed')
    if fails:
        print('FAILURES:')
        for name, _ok, detail in fails:
            print(f'  - {name}: {detail}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
