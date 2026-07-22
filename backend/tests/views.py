import json
import urllib.request
import urllib.error
from django.conf import settings

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.utils import timezone
from django.shortcuts import get_object_or_404

from subjects.models import Question, Answer, Subject, Topic
from subjects.serializers import QuestionDetailSerializer
from subjects.permissions import IsTeacherOrAdmin
from .models import TestSession, TestSectionResult, AnswerRecord
from .serializers import (
    StartTestSerializer, StartEntSerializer, AnswerBulkSerializer,
    AnswerRecordCreateSerializer,
    TestSessionListSerializer, TestSessionDetailSerializer,
    TeacherTestSessionListSerializer, TeacherTestSessionDetailSerializer,
)


ENT_SECTION_CONFIG = {
    'history':  {'count': 20, 'section_label': 'История Казахстана', 'subject_slug': 'history'},
    'reading':  {'count': 10, 'section_label': 'Грамотность чтения', 'subject_slug': 'reading'},
    'math_lit': {'count': 10, 'section_label': 'Математическая грамотность', 'subject_slug': 'math_profile'},
}


def _build_question_data(questions, request):
    request_scheme = request.scheme
    host = request.get_host()

    def build_url(image_field):
        if not image_field:
            return None
        return f'{request_scheme}://{host}{image_field.url}'

    result = []
    for q in questions:
        answers = q.answers.all()
        result.append({
            'id': q.id,
            'text': q.text,
            'question_type': q.question_type,
            'points': q.points,
            'section': q.section,
            'topic': q.topic.name,
            'difficulty': q.difficulty,
            'image': build_url(q.image) if q.image else None,
            'answers': [
                {'id': a.id, 'text': a.text, 'image': build_url(a.image) if a.image else None}
                for a in answers
            ],
        })
    return result


def _score_single_choice(question, selected_id):
    correct = question.answers.filter(is_correct=True)
    if correct and correct.first().id == selected_id:
        return question.points, question.points
    return 0, question.points


def _score_multiple_choice(question, selected_ids):
    correct_ids = set(question.answers.filter(is_correct=True).values_list('id', flat=True))
    selected = set(selected_ids)
    if not correct_ids:
        return 0, question.points
    correct_selected = len(correct_ids & selected)
    wrong_selected = len(selected - correct_ids)
    points_per_correct = question.points / len(correct_ids)
    earned = max(0, (correct_selected - wrong_selected) * points_per_correct)
    return round(earned, 1), question.points


def _score_matching(question, pairs):
    correct_ids = set(question.answers.filter(is_correct=True).values_list('id', flat=True))
    total_pairs = max(len(pairs), max(correct_ids) if correct_ids else 0)
    if total_pairs == 0:
        return 0, question.points
    correct_count = 0
    for key, val in pairs.items():
        expected = question.answers.filter(id=int(key), is_correct=True).first()
        if expected:
            correct_count += 1
    earned = (correct_count / len(correct_ids)) * question.points if correct_ids else 0
    return round(earned, 1), question.points


def _score_question(question, selected_answer=None, selected_answers=None, matching_pairs=None):
    if question.question_type == 'single_choice':
        return _score_single_choice(question, selected_answer)
    if question.question_type == 'multiple_choice':
        return _score_multiple_choice(question, selected_answers or [])
    if question.question_type == 'matching':
        return _score_matching(question, matching_pairs or {})
    return 0, question.points


class StartTestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = StartTestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        subject_id = serializer.validated_data['subject_id']
        subject = get_object_or_404(Subject, id=subject_id)

        # Ученики не стартуют скрытые предметы (учителя/админы — могут для проверки)
        if getattr(request.user, 'role', '') == 'student' and not subject.is_visible:
            return Response(
                {'error': 'Этот предмет сейчас недоступен'},
                status=status.HTTP_403_FORBIDDEN,
            )

        num_questions = serializer.validated_data.get('num_questions') or subject.question_count
        time_limit = subject.time_limit

        # Предпочитаем проверенные вопросы; если их мало — добираем остальные
        base_qs = Question.objects.filter(topic__subject_id=subject_id)
        questions = list(base_qs.filter(verification_status='verified').order_by('?')[:num_questions])
        if len(questions) < num_questions:
            extra = num_questions - len(questions)
            questions.extend(
                base_qs.exclude(id__in=[q.id for q in questions]).order_by('?')[:extra]
            )

        if len(questions) < num_questions:
            return Response(
                {'error': f'Недостаточно вопросов. Доступно: {len(questions)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        session = TestSession.objects.create(
            student=request.user,
            subject_id=subject_id,
            total_questions=num_questions,
            time_limit=time_limit,
        )

        question_data = _build_question_data(questions, request)

        return Response({
            'session_id': session.id,
            'total_questions': num_questions,
            'questions': question_data,
            'time_limit': time_limit,
        })


class StartEntView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = StartEntSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        profile1_id = serializer.validated_data['profile1_id']
        profile2_id = serializer.validated_data['profile2_id']

        try:
            profile1_subj = Subject.objects.get(id=profile1_id)
            profile2_subj = Subject.objects.get(id=profile2_id)
        except Subject.DoesNotExist:
            return Response({'error': 'Предмет не найден'}, status=status.HTTP_400_BAD_REQUEST)

        selected = {}
        sections_order = ['history', 'reading', 'math_lit', 'profile1', 'profile2']

        # Фиксированные секции — предпочитаем verified, но берём любые
        for sect, cfg in ENT_SECTION_CONFIG.items():
            qs = list(Question.objects.filter(
                topic__subject__slug=cfg['subject_slug'],
                verification_status='verified',
            ).order_by('?')[:cfg['count']])
            if len(qs) < cfg['count']:
                extra = cfg['count'] - len(qs)
                extra_qs = Question.objects.filter(
                    topic__subject__slug=cfg['subject_slug'],
                ).exclude(id__in=[q.id for q in qs]).order_by('?')[:extra]
                qs.extend(extra_qs)
            selected[sect] = qs

        # Профильные предметы
        for sect, subj_id, subj_obj in [
            ('profile1', profile1_id, profile1_subj),
            ('profile2', profile2_id, profile2_subj),
        ]:
            qs = list(Question.objects.filter(
                topic__subject_id=subj_id,
                verification_status='verified',
            ).order_by('?')[:40])
            if len(qs) < 40:
                extra = 40 - len(qs)
                extra_qs = Question.objects.filter(
                    topic__subject_id=subj_id,
                ).exclude(id__in=[q.id for q in qs]).order_by('?')[:extra]
                qs.extend(extra_qs)
            selected[sect] = qs

        # Проверка
        for sect, qs in selected.items():
            expected = 20 if sect == 'history' else 10 if sect in ('reading', 'math_lit') else 40
            if len(qs) < expected:
                return Response({
                    'error': f'Недостаточно вопросов для секции "{sect}". Нужно {expected}, доступно {len(qs)}'
                }, status=status.HTTP_400_BAD_REQUEST)

        # Создаём сессию
        all_questions = []
        for sect in sections_order:
            all_questions.extend(selected[sect])

        session = TestSession.objects.create(
            student=request.user,
            total_questions=len(all_questions),
            time_limit=14400,
            is_ent=True,
            total_points=sum(q.points for q in all_questions),
            ent_data={
                'profile1': {'id': profile1_id, 'name': profile1_subj.name},
                'profile2': {'id': profile2_id, 'name': profile2_subj.name},
            },
        )

        # Создаём section results
        for sect in sections_order:
            qs = selected[sect]
            subj = profile1_subj if sect == 'profile1' else profile2_subj if sect == 'profile2' else None
            TestSectionResult.objects.create(
                session=session,
                section=sect,
                subject=subj,
                total_questions=len(qs),
                points_max=sum(q.points for q in qs),
            )

        question_data = _build_question_data(all_questions, request)

        # Добавляем информацию о секциях
        sections_info = []
        idx = 0
        for sect in sections_order:
            qs = selected[sect]
            sections_info.append({
                'id': sect,
                'label': dict(Question.SECTION_CHOICES).get(sect, sect),
                'start': idx + 1,
                'end': idx + len(qs),
                'count': len(qs),
                'points_max': sum(q.points for q in qs),
            })
            idx += len(qs)

        return Response({
            'session_id': session.id,
            'total_questions': len(all_questions),
            'total_points': session.total_points,
            'time_limit': session.time_limit,
            'sections': sections_info,
            'questions': question_data,
        })


def _save_answer_record(session, question, selected_answer=None, selected_answers=None, matching_pairs=None):
    earned, max_pts = _score_question(question, selected_answer, selected_answers, matching_pairs)
    is_correct = earned >= max_pts and max_pts > 0

    record, created = AnswerRecord.objects.update_or_create(
        session=session,
        question=question,
        defaults={
            'selected_answer_id': selected_answer,
            'selected_answers': selected_answers or [],
            'matching_pairs': matching_pairs or {},
            'is_correct': is_correct,
            'points_earned': earned,
            'points_max': max_pts,
        },
    )
    return record


def _recalc_session(session):
    answers = session.answers.all()
    correct_count = answers.filter(is_correct=True).count()
    earned = sum(a.points_earned for a in answers)
    total = sum(a.points_max for a in answers)

    session.correct_answers = correct_count
    session.earned_points = earned
    session.total_points = total or session.total_points
    session.calculate_score()

    # Обновляем section results
    for sr in session.section_results.all():
        qs = answers.filter(question__section=sr.section)
        sr.answered = qs.count()
        sr.correct_answers = qs.filter(is_correct=True).count()
        sr.points_earned = sum(a.points_earned for a in qs)
        sr.points_max = sum(a.points_max for a in qs)
        sr.save()


class SubmitAnswerView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        try:
            session = TestSession.objects.get(id=session_id, student=request.user)
        except TestSession.DoesNotExist:
            return Response({'error': 'Сессия не найдена'}, status=status.HTTP_404_NOT_FOUND)

        if session.is_completed:
            return Response({'error': 'Тест уже завершён'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = AnswerRecordCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        question = serializer.validated_data['question']
        selected_answer = serializer.validated_data.get('selected_answer')
        selected_answers = serializer.validated_data.get('selected_answers', [])
        matching_pairs = serializer.validated_data.get('matching_pairs', {})

        if question.question_type == 'single_choice' and selected_answer:
            selected_answers = [selected_answer]

        _save_answer_record(session, question, selected_answer, selected_answers, matching_pairs)
        _recalc_session(session)

        return Response({
            'answered': session.answers.count(),
            'total': session.total_questions,
            'correct': session.correct_answers,
            'earned_points': session.earned_points,
        })


class SubmitBulkAnswersView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        try:
            session = TestSession.objects.get(id=session_id, student=request.user)
        except TestSession.DoesNotExist:
            return Response({'error': 'Сессия не найдена'}, status=status.HTTP_404_NOT_FOUND)

        if session.is_completed:
            return Response({'error': 'Тест уже завершён'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = AnswerBulkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        for ans_data in serializer.validated_data['answers']:
            question = ans_data['question']
            selected_answer = ans_data.get('selected_answer')
            selected_answers = ans_data.get('selected_answers', [])
            matching_pairs = ans_data.get('matching_pairs', {})
            _save_answer_record(session, question, selected_answer, selected_answers, matching_pairs)

        _recalc_session(session)

        return Response({
            'answered': session.answers.count(),
            'total': session.total_questions,
            'correct': session.correct_answers,
            'earned_points': session.earned_points,
        })


class FinishTestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        try:
            session = TestSession.objects.get(id=session_id, student=request.user)
        except TestSession.DoesNotExist:
            return Response({'error': 'Сессия не найдена'}, status=status.HTTP_404_NOT_FOUND)

        if session.is_completed:
            return Response({'error': 'Тест уже завершён'}, status=status.HTTP_400_BAD_REQUEST)

        _recalc_session(session)
        session.completed_at = timezone.now()
        session.is_completed = True
        session.save()

        return Response({
            'session_id': session.id,
            'total_questions': session.total_questions,
            'correct_answers': session.correct_answers,
            'score_percent': session.score_percent,
            'earned_points': session.earned_points,
            'total_points': session.total_points,
        })


class TestStateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        try:
            session = TestSession.objects.get(id=session_id, student=request.user)
        except TestSession.DoesNotExist:
            return Response({'error': 'Сессия не найдена'}, status=status.HTTP_404_NOT_FOUND)

        answers = session.answers.all()
        time_elapsed = (timezone.now() - session.started_at).total_seconds()
        time_left = max(0, session.time_limit - int(time_elapsed))

        answered_ids = set()
        flagged_ids = []
        answer_map = {}
        for a in answers:
            answered_ids.add(a.question_id)
            answer_map[a.question_id] = {
                'selected_answer': a.selected_answer_id,
                'selected_answers': a.selected_answers,
                'matching_pairs': a.matching_pairs,
            }

        return Response({
            'session_id': session.id,
            'is_completed': session.is_completed,
            'time_left': time_left,
            'answered': list(answered_ids),
            'flagged': flagged_ids,
            'answer_map': answer_map,
            'earned_points': session.earned_points,
            'total_points': session.total_points,
            'correct_answers': session.correct_answers,
            'total_questions': session.total_questions,
        })


class TestResultView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        try:
            session = TestSession.objects.get(id=session_id, student=request.user)
        except TestSession.DoesNotExist:
            return Response({'error': 'Сессия не найдена'}, status=status.HTTP_404_NOT_FOUND)

        serializer = TestSessionDetailSerializer(session)
        return Response(serializer.data)


class StudentTestHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sessions = TestSession.objects.filter(
            student=request.user, is_completed=True
        ).select_related('subject')
        serializer = TestSessionListSerializer(sessions, many=True)
        return Response(serializer.data)


class TeacherTestHistoryView(APIView):
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]

    def get(self, request):
        sessions = TestSession.objects.filter(
            is_completed=True
        ).select_related('subject', 'student')

        student_id = request.query_params.get('student')
        subject_id = request.query_params.get('subject')

        if student_id:
            sessions = sessions.filter(student_id=student_id)
        if subject_id:
            sessions = sessions.filter(subject_id=subject_id)

        sessions = sessions.order_by('-completed_at')
        serializer = TeacherTestSessionListSerializer(sessions, many=True)
        return Response(serializer.data)


class TeacherTestResultView(APIView):
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]

    def get(self, request, session_id):
        try:
            session = TestSession.objects.get(id=session_id)
        except TestSession.DoesNotExist:
            return Response({'error': 'Сессия не найдена'}, status=status.HTTP_404_NOT_FOUND)

        serializer = TeacherTestSessionDetailSerializer(session)
        return Response(serializer.data)


class TestPreviewView(APIView):
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]

    def post(self, request):
        subject_id = request.data.get('subject_id')
        num_questions = request.data.get('num_questions', 24)
        topic_id = request.data.get('topic_id')
        source_type = request.data.get('source_type')

        try:
            subject_id = int(subject_id)
        except (TypeError, ValueError):
            return Response({'error': 'subject_id required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            num_questions = max(1, min(100, int(num_questions)))
        except (TypeError, ValueError):
            num_questions = 24

        qs = Question.objects.filter(topic__subject_id=subject_id)
        if topic_id:
            qs = qs.filter(topic_id=topic_id)
        if source_type:
            qs = qs.filter(source_type=source_type)

        questions = list(qs.order_by('?')[:num_questions])

        if not questions:
            return Response({'error': 'Нет вопросов по заданным фильтрам'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = QuestionDetailSerializer(questions, many=True, context={'request': request})
        return Response({
            'subject_id': subject_id,
            'total_questions': len(questions),
            'questions': serializer.data,
        })


class AuthorialTestListView(APIView):
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]

    def get(self, request):
        from collections import defaultdict
        qs = Question.objects.filter(source_type='authorial').select_related('topic')
        groups = defaultdict(lambda: {'topic': '', 'subject': '', 'count': 0, 'form_id': ''})
        for q in qs:
            parts = q.external_id.rsplit('/', 1)
            form_id = parts[0] if len(parts) > 1 else q.external_id
            groups[form_id]['topic'] = q.topic.name
            groups[form_id]['subject'] = q.topic.subject.name
            groups[form_id]['count'] += 1
            groups[form_id]['form_id'] = form_id

        result = sorted(groups.values(), key=lambda x: -x['count'])
        return Response(result)


class AuthorialTestDetailView(APIView):
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]

    def get(self, request, form_id):
        from subjects.serializers import QuestionDetailSerializer
        qs = Question.objects.filter(source_type='authorial').select_related('topic')
        questions = []
        for q in qs:
            parts = q.external_id.rsplit('/', 1)
            q_form_id = parts[0] if len(parts) > 1 else q.external_id
            if q_form_id == form_id:
                questions.append(q)
        serializer = QuestionDetailSerializer(questions, many=True)
        topic_name = questions[0].topic.name if questions else ''
        subject_name = questions[0].topic.subject.name if questions else ''
        return Response({
            'form_id': form_id,
            'subject': subject_name,
            'topic': topic_name,
            'count': len(questions),
            'questions': serializer.data,
        })


class AuthorialTestDeleteView(APIView):
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]

    def delete(self, request, form_id):
        qs = Question.objects.filter(source_type='authorial')
        deleted = 0
        for q in qs:
            parts = q.external_id.rsplit('/', 1)
            q_form_id = parts[0] if len(parts) > 1 else q.external_id
            if q_form_id == form_id:
                q.delete()
                deleted += 1
        if deleted:
            return Response({'deleted': deleted, 'form_id': form_id})
        return Response({'error': 'Тест не найден'}, status=status.HTTP_404_NOT_FOUND)


class AIExplainView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        answer_id = request.data.get('answer_record_id')
        try:
            session = TestSession.objects.get(id=session_id)
            # Студент может разбирать только свои тесты
            if request.user.role == 'student' and session.student != request.user:
                return Response({'error': 'Доступ запрещён'}, status=403)
            record = AnswerRecord.objects.get(id=answer_id, session=session)
        except (TestSession.DoesNotExist, AnswerRecord.DoesNotExist):
            return Response({'error': 'Не найдено'}, status=404)

        question = record.question

        # Формируем текст ответа ученика
        if record.selected_answer:
            selected_text = record.selected_answer.text
        elif record.selected_answers:
            selected_text = ', '.join(
                Answer.objects.filter(id__in=record.selected_answers).values_list('text', flat=True)
            )
        elif record.matching_pairs:
            selected_text = ', '.join(f'{k}→{v}' for k, v in record.matching_pairs.items())
        else:
            selected_text = '—'

        # Формируем текст правильного ответа
        if question.question_type == 'single_choice':
            correct = question.answers.filter(is_correct=True).first()
            correct_text = correct.text if correct else '—'
        elif question.question_type == 'multiple_choice':
            correct_text = ', '.join(
                question.answers.filter(is_correct=True).values_list('text', flat=True)
            )
        elif question.question_type == 'matching':
            correct_text = ', '.join(
                question.answers.filter(is_correct=True).values_list('text', flat=True)
            )
        else:
            correct_text = '—'

        prompt = (
            f"Вопрос: {question.text}\n"
            f"Правильный ответ: {correct_text}\n"
            f"Ответ ученика: {selected_text}\n\n"
            f"Объясни на русском, почему ответ ученика неверный. "
            f"Дай краткое пояснение (3-5 предложений) и подсказку к правильному решению."
        )

        hf_token = getattr(settings, 'HF_API_TOKEN', '')
        gemini_key = getattr(settings, 'GEMINI_API_KEY', '')
        ai_explanation = ''

        system_prompt = 'Ты репетитор по подготовке к ЕНТ. Отвечай кратко, понятно, на русском языке.'
        full_prompt = f'{system_prompt}\n\n{prompt}'

        # Сначала пробуем Gemini (основной)
        if gemini_key:
            try:
                data = json.dumps({
                    'contents': [{
                        'parts': [{'text': full_prompt}]
                    }],
                    'generationConfig': {
                        'maxOutputTokens': 500,
                        'temperature': 0.7,
                    },
                }).encode('utf-8')
                url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}'
                req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    result = json.loads(resp.read())
                    ai_explanation = result['candidates'][0]['content']['parts'][0]['text'].strip()
            except Exception:
                ai_explanation = ''  # fallback to HF

        # Если Gemini не сработал — пробуем Hugging Face
        if not ai_explanation and hf_token:
            try:
                data = json.dumps({
                    'inputs': f'<s>[INST] {full_prompt} [/INST]',
                    'parameters': {'max_new_tokens': 500, 'temperature': 0.7},
                }).encode('utf-8')
                req = urllib.request.Request(
                    'https://router.huggingface.co/hf-inference/models/mistralai/Mistral-7B-Instruct-v0.3',
                    data=data, headers={
                        'Content-Type': 'application/json',
                        'Authorization': f'Bearer {hf_token}',
                    },
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    result = json.loads(resp.read())
                    ai_explanation = result[0]['generated_text'].strip()
                    if '[/INST]' in ai_explanation:
                        ai_explanation = ai_explanation.split('[/INST]')[-1].strip()
            except urllib.error.HTTPError as e:
                body = e.read().decode('utf-8')[:200]
                ai_explanation = f'⚠️ Ошибка AI ({e.code}): {body}'
            except Exception as e:
                ai_explanation = f'⚠️ Ошибка AI-разбора: {str(e)[:100]}'

        return Response({
            'answer_record_id': answer_id,
            'question_text': question.text,
            'correct_answer': correct_text,
            'selected_answer': selected_text,
            'explanation': ai_explanation,
        })
