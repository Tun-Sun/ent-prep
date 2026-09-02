from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Avg, Count, Max, Prefetch, Q, Sum
from django.db.models import Case, When, F, FloatField
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.utils import timezone
from datetime import timedelta

from users.models import User
from subjects.models import Subject
from subjects.permissions import IsTeacherOrAdmin
from tests.models import TestSession, TestSectionResult, AnswerRecord


class StudentDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        student = request.user
        completed_sessions = TestSession.objects.filter(
            student=student, is_completed=True
        ).select_related('subject')

        total_tests = completed_sessions.count()
        avg_score = completed_sessions.aggregate(
            avg=Avg('score_percent')
        )['avg'] or 0

        # Прогресс по каждому предмету (только выбранные + обязательные)
        profile_ids = student.profile_subjects.values_list('id', flat=True)
        all_subjects = Subject.objects.all()
        if profile_ids:
            subjects = all_subjects.filter(
                Q(subject_type='mandatory') | Q(id__in=profile_ids)
            )
        else:
            subjects = all_subjects
        subject_progress = []
        for subj in subjects:
            sessions = completed_sessions.filter(subject=subj)
            count = sessions.count()
            if count == 0:
                continue
            avg = sessions.aggregate(avg=Avg('score_percent'))['avg'] or 0
            best = sessions.aggregate(best=Max('score_percent'))['best'] or 0
            last_score = sessions.first().score_percent if sessions.exists() else None
            subject_progress.append({
                'id': subj.id,
                'name': subj.name,
                'icon': subj.icon,
                'tests_taken': count,
                'avg_score': round(avg, 1),
                'best_score': round(best, 1),
                'last_score': round(last_score, 1) if last_score else None,
            })

        # Последние 10 тестов для графика
        recent = completed_sessions[:10]
        chart_data = [
            {
                'date': s.started_at.strftime('%d.%m'),
                'subject': s.subject.name,
                'score': s.score_percent,
            }
            for s in reversed(list(recent))
        ]

        return Response({
            'total_tests': total_tests,
            'avg_score': round(avg_score, 1),
            'subject_progress': subject_progress,
            'recent_tests': chart_data,
        })


class TeacherDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ('teacher', 'admin'):
            return Response({'error': 'Доступ только для учителей'}, status=403)

        period = request.query_params.get('period', 'all')
        subject_id = request.query_params.get('subject_id')

        now = timezone.now()
        if period == 'week':
            start = now - timedelta(days=7)
        elif period == 'month':
            start = now - timedelta(days=30)
        else:
            start = None

        students = User.objects.filter(role='student')
        total_students = students.count()

        completed = TestSession.objects.filter(is_completed=True)
        total_tests = completed.count()
        avg_score = completed.aggregate(avg=Avg('score_percent'))['avg'] or 0

        # Топ учеников — по умолчанию только выбранные учителем предметы
        dashboard_ids = request.user.dashboard_subjects.values_list('id', flat=True)
        session_filter = Q(test_sessions__is_completed=True)
        if start:
            session_filter &= Q(test_sessions__started_at__gte=start)
        if subject_id:
            session_filter &= Q(test_sessions__subject_id=subject_id)
        elif dashboard_ids:
            session_filter &= Q(test_sessions__subject_id__in=dashboard_ids)

        top_students = students.annotate(
            test_count=Count('test_sessions', filter=session_filter),
            avg_score=Avg('test_sessions__score_percent', filter=session_filter),
        ).filter(test_count__gt=0).order_by('-avg_score')[:50]

        top_data = [
            {
                'id': s.id,
                'username': s.username,
                'full_name': s.full_name,
                'avg_score': round(s.avg_score or 0, 1),
                'test_count': s.test_count,
            }
            for s in top_students
        ]

        # Фильтр по выбранным предметам
        selected = request.user.dashboard_subjects.all()
        subjects_qs = selected if selected.exists() else Subject.objects.all()

        # Средний балл по предметам
        subject_stats = subjects_qs.annotate(
            avg_score=Avg('test_sessions__score_percent', filter=Q(test_sessions__is_completed=True)),
            test_count=Count('test_sessions', filter=Q(test_sessions__is_completed=True)),
        )

        subject_data = [
            {
                'id': s.id,
                'name': s.name,
                'icon': s.icon,
                'avg_score': round(s.avg_score or 0, 1),
                'test_count': s.test_count,
            }
            for s in subject_stats
        ]

        return Response({
            'total_students': total_students,
            'total_tests': total_tests,
            'avg_score': round(avg_score, 1),
            'top_students': top_data,
            'subject_stats': subject_data,
            'dashboard_subject_ids': list(selected.values_list('id', flat=True)),
        })


class TeacherStudentsView(APIView):
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]

    def get(self, request):
        # Filters
        group_id = request.query_params.get('group_id')
        subject_id = request.query_params.get('subject_id')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')

        # Base student query
        students = User.objects.filter(role='student')

        # Filter by group membership
        if group_id:
            students = students.filter(student_groups__id=group_id)

        # Annotate with overall stats (may be further filtered by session filters)
        session_filter = Q(test_sessions__is_completed=True)
        if subject_id:
            session_filter &= Q(test_sessions__subject_id=subject_id)
        if date_from:
            session_filter &= Q(test_sessions__started_at__date__gte=date_from)
        if date_to:
            session_filter &= Q(test_sessions__started_at__date__lte=date_to)

        student_sessions = TestSession.objects.filter(
            is_completed=True
        ).select_related('subject')
        if subject_id:
            student_sessions = student_sessions.filter(subject_id=subject_id)
        if date_from:
            student_sessions = student_sessions.filter(started_at__date__gte=date_from)
        if date_to:
            student_sessions = student_sessions.filter(started_at__date__lte=date_to)

        students = students.annotate(
            total_tests=Count('test_sessions', filter=session_filter),
            avg_score=Avg('test_sessions__score_percent', filter=session_filter),
        ).prefetch_related(
            Prefetch('test_sessions', queryset=student_sessions, to_attr='filtered_sessions'),
            'student_groups',
            'profile_subjects',
        ).order_by('-avg_score')

        data = []
        for s in students:
            by_subject = {}
            for sess in s.filtered_sessions:
                if not sess.subject:
                    continue
                if sess.subject.name not in by_subject:
                    by_subject[sess.subject.name] = []
                by_subject[sess.subject.name].append(sess.score_percent)

            subject_progress = {
                name: round(sum(scores) / len(scores), 1)
                for name, scores in by_subject.items()
            }

            groups_info = [{'id': group.id, 'name': group.name} for group in s.student_groups.all()]

            data.append({
                'id': s.id,
                'username': s.username,
                'full_name': s.full_name,
                'school': s.school,
                'total_tests': s.total_tests,
                'avg_score': round(s.avg_score or 0, 1),
                'subject_progress': subject_progress,
                'groups': groups_info,
                'profile_subjects': [subject.id for subject in s.profile_subjects.all()],
            })

        return Response(data)


class TeacherAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ('teacher', 'admin'):
            return Response({'error': 'Доступ только для учителей'}, status=403)
        return self._analytics_response(request)

    def _analytics_response(self, request):
        qs = self._filtered_queryset(request)

        # Общий средний балл
        agg = qs.aggregate(avg=Avg('score_percent'))
        avg_score = round(agg['avg'] or 0, 1)

        # Результаты (с пагинацией)
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        total_count = qs.count()
        start = (page - 1) * page_size
        end = start + page_size

        results = []
        for s in qs[start:end].select_related('student', 'subject'):
            results.append({
                'id': s.id,
                'timestamp': s.started_at.strftime('%Y-%m-%d %H:%M'),
                'group': None,
                'subject': s.subject.name if s.subject else '',
                'student_name': s.student.full_name or s.student.username,
                'score': s.earned_points,
                'max_score': s.total_points,
                'score_percent': s.score_percent,
                'is_ent': s.is_ent,
                'ent_question_count': s.subject.ent_question_count if s.subject else None,
                'ent_max_score': s.subject.ent_max_score if s.subject else None,
                'ent_threshold': s.subject.ent_threshold if s.subject else None,
            })

        # Ежедневная статистика (для графика)
        daily = qs.annotate(
            date=TruncDate('started_at')
        ).values('date').annotate(
            count=Count('id'),
            avg_score=Avg('score_percent'),
            max_score=Max('score_percent'),
        ).order_by('date')

        daily_data = [
            {
                'date': d['date'].strftime('%d.%m') if d['date'] else '',
                'count': d['count'],
                'avg_score': round(d['avg_score'] or 0, 1),
                'max_score': round(d['max_score'] or 0, 1),
            }
            for d in daily
        ]

        # Распределение по предметам (для круговой диаграммы)
        subject_dist = qs.values('subject__id', 'subject__name', 'subject__slug').annotate(
            count=Count('id'),
            avg_score=Avg('score_percent'),
        ).order_by('-count')

        total = sum(d['count'] for d in subject_dist) or 1
        subject_qs = Subject.objects.all()
        ent_map = {s.slug: s for s in subject_qs}
        subject_data = []
        for d in subject_dist:
            slug = d.get('subject__slug')
            info = ent_map.get(slug)
            subject_data.append({
                'id': d['subject__id'],
                'name': d['subject__name'] or 'Без предмета',
                'count': d['count'],
                'percentage': round(d['count'] / total * 100, 1),
                'avg_score': round(d['avg_score'] or 0, 1),
                'ent_question_count': info.ent_question_count if info else None,
                'ent_max_score': info.ent_max_score if info else None,
                'ent_threshold': info.ent_threshold if info else None,
            })

        # Средний балл по каждому предмету
        subject_avgs = dict(
            qs.values('subject__slug', 'subject__name').annotate(
                avg=Avg('score_percent')
            ).values_list('subject__slug', 'avg')
        )

        # Ниже/выше среднего — сравниваем со средним баллом по предмету
        below = []
        above = []
        for s in qs.select_related('student', 'subject'):
            slug = s.subject.slug if s.subject else None
            subj_avg = subject_avgs.get(slug, avg_score)
            item = {
                'id': s.id,
                'timestamp': s.started_at.strftime('%Y-%m-%d %H:%M'),
                'group': None,
                'subject': s.subject.name if s.subject else '',
                'student_name': s.student.full_name or s.student.username,
                'score': s.earned_points,
                'max_score': s.total_points,
            }
            if s.score_percent < subj_avg:
                below.append(item)
            else:
                above.append(item)

        unique_students = qs.values('student').distinct().count()

        return Response({
            'results': results,
            'total_count': total_count,
            'unique_students': unique_students,
            'page': page,
            'page_size': page_size,
            'daily_stats': daily_data,
            'subject_distribution': subject_data,
            'average_score': avg_score,
            'below_average': below[:50],
            'above_average': above[:50],
        })

    def _filtered_queryset(self, request):
        qs = TestSession.objects.filter(is_completed=True)

        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        group_id = request.query_params.get('group_id')
        subject_id = request.query_params.get('subject_id')
        student_id = request.query_params.get('student_id')

        if date_from:
            qs = qs.filter(started_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(started_at__date__lte=date_to)
        if subject_id:
            qs = qs.filter(subject_id=subject_id)
        if student_id:
            qs = qs.filter(student_id=student_id)
        if group_id:
            from users.models import StudyGroup
            try:
                group = StudyGroup.objects.get(id=group_id)
                qs = qs.filter(student_id__in=group.students.values_list('id', flat=True))
            except StudyGroup.DoesNotExist:
                pass

        return qs


class LeaderboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Avg, Count
        from django.utils import timezone
        from datetime import timedelta
        from users.models import User

        period = request.query_params.get('period', 'all')
        subject_id = request.query_params.get('subject_id')

        now = timezone.now()
        if period == 'week':
            start = now - timedelta(days=7)
        elif period == 'month':
            start = now - timedelta(days=30)
        else:
            start = None

        students = User.objects.filter(role='student')
        rankings = []
        for s in students:
            sessions = TestSession.objects.filter(student=s, is_completed=True)
            if start:
                sessions = sessions.filter(started_at__gte=start)
            if subject_id:
                sessions = sessions.filter(subject_id=subject_id)
            count = sessions.count()
            if count == 0:
                continue
            avg = sessions.aggregate(avg=Avg('score_percent'))['avg'] or 0
            rankings.append({
                'id': s.id,
                'username': s.username,
                'full_name': s.full_name or s.username,
                'tests_taken': count,
                'avg_score': round(avg, 1),
            })
        rankings.sort(key=lambda r: -r['avg_score'])
        return Response(rankings[:100])


class DashboardSubjectsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ('teacher', 'admin'):
            return Response({'error': 'Доступ только для учителей'}, status=403)
        selected = request.user.dashboard_subjects.all()
        all_subjects = Subject.objects.filter(is_visible=True)
        data = [
            {
                'id': s.id,
                'name': s.name,
                'icon': s.icon,
                'selected': selected.filter(id=s.id).exists(),
            }
            for s in all_subjects
        ]
        return Response(data)

    def put(self, request):
        if request.user.role not in ('teacher', 'admin'):
            return Response({'error': 'Доступ только для учителей'}, status=403)
        subject_ids = request.data.get('subject_ids', [])
        subjects = Subject.objects.filter(id__in=subject_ids)
        request.user.dashboard_subjects.set(subjects)
        return Response({'dashboard_subject_ids': list(subjects.values_list('id', flat=True))})


# ─── Слабые темы ──────────────────────────────────────────────────────────

def _student_subjects(student):
    subjects = Subject.objects.filter(is_visible=True)
    profile_ids = list(student.profile_subjects.values_list('id', flat=True))
    if profile_ids:
        subjects = subjects.filter(Q(subject_type='mandatory') | Q(id__in=profile_ids))
    return subjects


def _weak_topics_for(student, limit=10, min_answers=3, max_accuracy=50.0):
    """Темы с точностью ниже порога, отсортированные по худшей точности."""
    subjects = _student_subjects(student)
    rows = (
        AnswerRecord.objects
        .filter(
            session__student=student,
            session__is_completed=True,
            session__is_ent=False,
            question__topic__subject__in=subjects,
        )
        .values(
            'question__topic_id',
            'question__topic__name',
            'question__topic__subject_id',
            'question__topic__subject__name',
            'question__topic__subject__icon',
        )
        .annotate(
            total=Count('id'),
            correct=Sum(Case(When(is_correct=True, then=1), default=0)),
        )
        .filter(total__gte=min_answers)
    )
    topics = []
    for r in rows:
        accuracy = round(r['correct'] / r['total'] * 100, 1)
        if accuracy < max_accuracy:
            topics.append({
                'topic_id': r['question__topic_id'],
                'topic': r['question__topic__name'],
                'subject_id': r['question__topic__subject_id'],
                'subject': r['question__topic__subject__name'],
                'icon': r['question__topic__subject__icon'],
                'total': r['total'],
                'correct': r['correct'],
                'accuracy': accuracy,
            })
    topics.sort(key=lambda t: (t['accuracy'], -t['total']))
    return topics[:limit]


class WeakTopicsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        topics = _weak_topics_for(request.user, limit=int(request.query_params.get('limit', 10)))
        by_subject = {}
        for t in topics:
            key = (t['subject_id'], t['subject'], t['icon'])
            by_subject.setdefault(key, []).append(t)
        grouped = [
            {
                'subject_id': key[0],
                'subject': key[1],
                'icon': key[2],
                'topics': [
                    {'topic_id': t['topic_id'], 'topic': t['topic'],
                     'accuracy': t['accuracy'], 'total': t['total']}
                    for t in items
                ],
                'topic_ids': [t['topic_id'] for t in items],
            }
            for key, items in by_subject.items()
        ]
        return Response({'groups': grouped})


# ─── Прогноз балла ЕНТ ────────────────────────────────────────────────────

def _ent_forecast_for(student):
    """Прогноз по шкале ЕНТ: 20+10+10+50+50 = 140.

    Считается по завершённым симуляциям ЕНТ (каждая секция масштабируется
    к максимуму шкалы). Если симуляций нет — оценка по средним предметным
    тестам.
    """
    ent_sessions = (
        TestSession.objects
        .filter(student=student, is_ent=True, is_completed=True)
        .prefetch_related('section_results__subject')
        .order_by('completed_at')
    )

    SECTION_MAX = {'history': 20.0, 'reading': 10.0, 'math_lit': 10.0}

    history = []
    for s in ent_sessions:
        total = 0.0
        has_data = False
        for sr in s.section_results.all():
            if sr.points_max and sr.points_max > 0:
                if sr.section in SECTION_MAX:
                    scale = SECTION_MAX[sr.section]
                elif sr.section.startswith('profile') and sr.subject:
                    scale = float(sr.subject.ent_max_score)
                else:
                    continue
                total += float(sr.points_earned) / float(sr.points_max) * scale
                has_data = True
        if has_data:
            history.append(round(total, 1))

    result = {
        'has_ent_sessions': bool(history),
        'max_score': 140,
        'history': [],
        'score': None,
        'trend': None,
        'sections': [],
    }

    if history:
        # Даты для графика
        dates = [
            s.completed_at.strftime('%d.%m') for s in ent_sessions
            if s.section_results.exists()
        ]
        result['history'] = [
            {'date': d, 'score': h} for d, h in zip(dates, history)
        ]
        if len(history) >= 4:
            recent, prev = history[-3:], history[:-3]
        elif len(history) >= 2:
            recent, prev = history[-1:], history[:-1]
        else:
            recent, prev = history, []
        result['score'] = round(sum(recent) / len(recent), 1)
        if prev:
            delta = sum(recent) / len(recent) - sum(prev) / len(prev)
            result['trend'] = 'rising' if delta >= 2 else ('falling' if delta <= -2 else 'stable')

        # Разбивка по секциям последней симуляции
        last = ent_sessions.last()
        sections = []
        for sr in last.section_results.all().select_related('subject'):
            if not sr.points_max:
                continue
            if sr.section in SECTION_MAX:
                scale, name = SECTION_MAX[sr.section], sr.get_section_display()
                threshold = None
            elif sr.subject:
                scale = float(sr.subject.ent_max_score)
                name = sr.subject.name
                threshold = float(sr.subject.ent_threshold)
            else:
                continue
            score = round(float(sr.points_earned) / float(sr.points_max) * scale, 1)
            sections.append({
                'name': name,
                'score': score,
                'max': scale,
                'threshold': threshold,
                'passes': (threshold is None) or score >= threshold,
            })
        result['sections'] = sections
        return result

    # Оценка по предметным тестам, если симуляций нет
    subjects = _student_subjects(student)
    profile_ids = list(student.profile_subjects.values_list('id', flat=True))
    estimate = 0.0
    sections = []
    has_any = False
    for subj in subjects:
        sessions = TestSession.objects.filter(
            student=student, subject=subj, is_completed=True, is_ent=False,
        )
        count = sessions.count()
        if not count:
            continue
        avg = sessions.aggregate(a=Avg('score_percent'))['a'] or 0
        scale = float(subj.ent_max_score) if subj.subject_type == 'profile' else (
            SECTION_MAX.get(
                'history' if subj.slug == 'history'
                else 'reading' if subj.slug == 'reading'
                else 'math_lit' if subj.slug == 'math_profile'
                else None, 10.0
            )
        )
        score = round(avg / 100 * scale, 1)
        if profile_ids and subj.id in profile_ids or subj.subject_type == 'mandatory':
            estimate += score
            has_any = True
        sections.append({
            'name': subj.name,
            'score': score,
            'max': scale,
            'threshold': float(subj.ent_threshold) if subj.subject_type == 'profile' else None,
            'passes': (subj.subject_type != 'profile') or score >= float(subj.ent_threshold),
        })
    if has_any:
        result['score'] = round(min(estimate, 140), 1)
        result['sections'] = sections
    return result


class EntForecastView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(_ent_forecast_for(request.user))


# ─── PDF-отчёт по ученику ─────────────────────────────────────────────────

class StudentReportView(APIView):
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]

    def get(self, request, student_id):
        try:
            student = User.objects.get(id=student_id, role='student')
        except User.DoesNotExist:
            return Response({'error': 'Ученик не найден'}, status=404)

        from .reports import build_student_report
        from gamification.services import get_streak

        sessions = TestSession.objects.filter(
            student=student, is_completed=True,
        ).select_related('subject')

        total_tests = sessions.count()
        avg_score = sessions.aggregate(a=Avg('score_percent'))['a'] or 0
        best_score = sessions.aggregate(m=Max('score_percent'))['m'] or 0

        subjects = []
        for subj in Subject.objects.filter(test_sessions__in=sessions).distinct():
            ss = sessions.filter(subject=subj)
            subjects.append({
                'name': subj.name,
                'tests': ss.count(),
                'avg': round(ss.aggregate(a=Avg('score_percent'))['a'] or 0, 1),
                'best': round(ss.aggregate(m=Max('score_percent'))['m'] or 0, 1),
            })
        subjects.sort(key=lambda s: -s['avg'])

        weak_topics = _weak_topics_for(student, limit=5)
        forecast = _ent_forecast_for(student)
        if not forecast.get('score'):
            forecast = None
        else:
            forecast = {'score': forecast['score'], 'trend': forecast['trend'],
                        'max_score': forecast['max_score'],
                        'sections': forecast.get('sections', [])}

        recent = [
            {
                'date': s.completed_at.strftime('%d.%m.%Y') if s.completed_at else '—',
                'label': ('Симуляция ЕНТ' if s.is_ent
                          else s.subject.name if s.subject
                          else {'rush': 'Question Rush', 'duel': 'Дуэль'}.get(s.mode, 'Тест')),
                'score': f"{round(s.score_percent, 1)}%"
                         + (f" ({round(s.earned_points, 1)}/{round(s.total_points, 1)} б.)"
                            if s.is_ent else ''),
            }
            for s in sessions.order_by('-completed_at')[:10]
        ]

        stats = {
            'total_tests': total_tests,
            'avg_score': round(avg_score, 1),
            'best_score': round(best_score, 1),
            'streak': get_streak(student)['current'],
        }

        try:
            pdf_bytes = build_student_report(student, stats, subjects, weak_topics, forecast, recent)
        except RuntimeError as e:
            return Response({'error': str(e)}, status=500)

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        filename = f"report_{student.username}_{timezone.localdate().strftime('%Y%m%d')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
