from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Avg, Count, Max, Q
from django.db.models.functions import TruncDate

from users.models import User
from subjects.models import Subject
from tests.models import TestSession


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

        # Прогресс по каждому предмету
        subjects = Subject.objects.all()
        subject_progress = []
        for subj in subjects:
            sessions = completed_sessions.filter(subject=subj)
            count = sessions.count()
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
        if request.user.role != 'teacher':
            return Response({'error': 'Доступ только для учителей'}, status=403)

        students = User.objects.filter(role='student')
        total_students = students.count()

        completed = TestSession.objects.filter(is_completed=True)
        total_tests = completed.count()
        avg_score = completed.aggregate(avg=Avg('score_percent'))['avg'] or 0

        # Топ-5 учеников
        top_students = students.annotate(
            test_count=Count('test_sessions', filter=Q(test_sessions__is_completed=True)),
            avg_score=Avg('test_sessions__score_percent', filter=Q(test_sessions__is_completed=True)),
        ).order_by('-avg_score')[:5]

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

        # Средний балл по предметам
        subject_stats = Subject.objects.annotate(
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
        })


class TeacherStudentsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'teacher':
            return Response({'error': 'Доступ только для учителей'}, status=403)

        students = User.objects.filter(role='student').annotate(
            total_tests=Count('test_sessions', filter=Q(test_sessions__is_completed=True)),
            avg_score=Avg('test_sessions__score_percent', filter=Q(test_sessions__is_completed=True)),
        ).order_by('-avg_score')

        data = []
        for s in students:
            sessions = TestSession.objects.filter(
                student=s, is_completed=True
            ).select_related('subject')

            by_subject = {}
            for sess in sessions:
                if sess.subject.name not in by_subject:
                    by_subject[sess.subject.name] = []
                by_subject[sess.subject.name].append(sess.score_percent)

            subject_progress = {
                name: round(sum(scores) / len(scores), 1)
                for name, scores in by_subject.items()
            }

            data.append({
                'id': s.id,
                'username': s.username,
                'full_name': s.full_name,
                'school': s.school,
                'total_tests': s.total_tests,
                'avg_score': round(s.avg_score or 0, 1),
                'subject_progress': subject_progress,
            })

        return Response(data)


class TeacherAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'teacher':
            return Response({'error': 'Доступ только для учителей'}, status=403)

        completed = TestSession.objects.filter(is_completed=True)

        # Распределение баллов
        score_ranges = [
            ('0-20%', 0, 20), ('21-40%', 21, 40),
            ('41-60%', 41, 60), ('61-80%', 61, 80), ('81-100%', 81, 100),
        ]
        distribution = []
        for label, low, high in score_ranges:
            count = completed.filter(
                score_percent__gte=low, score_percent__lte=high
            ).count()
            distribution.append({
                'range': label,
                'count': count,
            })

        # Динамика по дням (последние 14 дней)
        daily = completed.annotate(
            date=TruncDate('started_at')
        ).values('date').annotate(
            avg_score=Avg('score_percent'),
            count=Count('id'),
        ).order_by('date')

        daily_data = [
            {
                'date': d['date'].strftime('%d.%m') if d['date'] else '',
                'avg_score': round(d['avg_score'] or 0, 1),
                'count': d['count'],
            }
            for d in daily[:14]
        ]

        return Response({
            'score_distribution': distribution,
            'daily_progress': daily_data,
        })
