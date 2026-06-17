import io
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.http import HttpResponse

from .models import Subject, Topic, Question, Answer
from .permissions import IsTeacherOrAdmin


class ExcelTemplateView(APIView):
    """Скачивание пустого шаблона Excel для импорта вопросов"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wb = Workbook()
        ws = wb.active
        ws.title = 'Вопросы'

        headers = ['Тема', 'Текст вопроса', 'Сложность', 'Вариант A', 'Вариант B',
                   'Вариант C', 'Вариант D', 'Правильный ответ', 'Объяснение']
        ws.append(headers)

        # Стилизация заголовков
        header_fill = PatternFill(start_color='4F46E5', end_color='4F46E5', fill_type='solid')
        header_font = Font(color='FFFFFF', bold=True)
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center')

        # Пример строки
        example = ['Алгебра', 'Чему равно 2 + 2?', 'easy', '3', '4', '5', '6', 'B', '2 + 2 = 4']
        ws.append(example)

        # Инструкция
        ws2 = wb.create_sheet('Инструкция')
        instructions = [
            ['ИНСТРУКЦИЯ ПО ЗАПОЛНЕНИЮ', ''],
            ['', ''],
            ['1. Тема', 'Название темы (если темы нет — она создастся автоматически)'],
            ['2. Текст вопроса', 'Сам вопрос'],
            ['3. Сложность', 'easy (лёгкий), medium (средний), hard (сложный)'],
            ['4-7. Варианты', '4 варианта ответа (A, B, C, D)'],
            ['8. Правильный ответ', 'Буква правильного ответа: A, B, C или D'],
            ['9. Объяснение', 'Объяснение правильного ответа (необязательно)'],
            ['', ''],
            ['ВАЖНО:', ''],
            ['', '• Не удаляйте строку с заголовками'],
            ['', '• Не меняйте порядок столбцов'],
            ['', '• Правильный ответ — только одна буква: A, B, C или D'],
        ]
        for row in instructions:
            ws2.append(row)
        ws2['A1'].font = Font(bold=True, size=14)

        # Авто-ширина
        for ws_sheet in [ws, ws2]:
            for column in ws_sheet.columns:
                max_length = max(len(str(cell.value or '')) for cell in column)
                ws_sheet.column_dimensions[column[0].column_letter].width = min(max_length + 4, 50)

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        response = HttpResponse(
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="ent_questions_template.xlsx"'
        return response


class ExcelImportView(APIView):
    """Импорт вопросов из Excel файла"""
    permission_classes = [IsTeacherOrAdmin]
    parser_classes = [MultiPartParser]

    def post(self, request):
        file = request.FILES.get('file')
        subject_id = request.data.get('subject_id')

        if not file:
            return Response({'error': 'Файл не загружен'}, status=status.HTTP_400_BAD_REQUEST)
        if not subject_id:
            return Response({'error': 'Не выбран предмет'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            subject = Subject.objects.get(id=subject_id)
        except Subject.DoesNotExist:
            return Response({'error': 'Предмет не найден'}, status=status.HTTP_404_NOT_FOUND)

        try:
            wb = Workbook()
            wb = wb.load_workbook(file, data_only=True)
        except Exception:
            return Response({'error': 'Не удалось прочитать Excel-файл. Убедитесь, что это .xlsx'}, status=400)

        ws = wb.active
        rows = list(ws.iter_rows(min_row=2, values_only=True))

        created = 0
        errors = []
        difficulty_map = {'easy': 'easy', 'medium': 'medium', 'hard': 'hard',
                          'лёгкий': 'easy', 'легкий': 'easy', 'средний': 'medium', 'сложный': 'hard'}

        for idx, row in enumerate(rows, start=2):
            # Пропускаем пустые строки
            if not row or not any(str(c).strip() for c in row if c is not None):
                continue

            try:
                # Распаковываем с учётом возможных пустых ячеек
                topic_name = str(row[0] or '').strip()
                question_text = str(row[1] or '').strip()
                difficulty_raw = str(row[2] or 'medium').strip().lower()
                ans_a = str(row[3] or '').strip()
                ans_b = str(row[4] or '').strip()
                ans_c = str(row[5] or '').strip()
                ans_d = str(row[6] or '').strip()
                correct_raw = str(row[7] or '').strip().upper()
                explanation = str(row[8] or '').strip()

                # Валидация
                if not question_text:
                    errors.append(f'Строка {idx}: пустой текст вопроса')
                    continue
                if not topic_name:
                    errors.append(f'Строка {idx}: не указана тема')
                    continue
                if correct_raw not in ('A', 'B', 'C', 'D'):
                    errors.append(f'Строка {idx}: правильный ответ должен быть A, B, C или D (получено "{correct_raw}")')
                    continue

                answers_texts = {'A': ans_a, 'B': ans_b, 'C': ans_c, 'D': ans_d}
                if not answers_texts[correct_raw]:
                    errors.append(f'Строка {idx}: не заполнен правильный вариант ({correct_raw})')
                    continue

                difficulty = difficulty_map.get(difficulty_raw, 'medium')

                # Создаём или берём тему
                topic, _ = Topic.objects.get_or_create(
                    name=topic_name, subject=subject
                )

                # Создаём вопрос
                question = Question.objects.create(
                    text=question_text,
                    topic=topic,
                    difficulty=difficulty,
                    explanation=explanation,
                )

                # Создаём ответы
                for letter, text in answers_texts.items():
                    if text:  # создаём только непустые варианты
                        Answer.objects.create(
                            question=question,
                            text=text,
                            is_correct=(letter == correct_raw),
                        )

                created += 1

            except Exception as e:
                errors.append(f'Строка {idx}: {str(e)}')
                continue

        return Response({
            'created': created,
            'errors': errors,
            'errors_count': len(errors),
            'message': f'Импортировано {created} вопросов' + (f', ошибок: {len(errors)}' if errors else ''),
        }, status=status.HTTP_200_OK)
