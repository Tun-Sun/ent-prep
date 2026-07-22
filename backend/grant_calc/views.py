from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from .models import University
from .serializers import UniversitySerializer, GrantCalcRequestSerializer


class GrantCalcView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        score_param = request.query_params.get('score', '')
        search = request.query_params.get('search', '').strip().lower()
        uni_type = request.query_params.get('uni_type', 'all')

        qs = University.objects.all()

        if uni_type != 'all':
            qs = qs.filter(uni_type=uni_type)

        if search:
            qs = qs.filter(
                name__icontains=search
            ) | qs.filter(
                city__icontains=search
            ) | qs.filter(
                specializations__icontains=search
            )

        universities = list(qs)

        # Если есть score — вычисляем шансы
        try:
            score = int(score_param)
        except (ValueError, TypeError):
            score = None

        result = []
        for u in universities:
            item = UniversitySerializer(u).data
            if score is not None:
                gap = score - u.min_score
                if gap >= 15:
                    chance = 'high'
                elif gap >= 0:
                    chance = 'mid'
                else:
                    chance = 'low'
                item['gap'] = gap
                item['chance'] = chance
            else:
                item['gap'] = None
                item['chance'] = None
            result.append(item)

        # Сортируем: high → mid → low, внутри по gap
        if score is not None:
            chance_order = {'high': 0, 'mid': 1, 'low': 2}
            result.sort(key=lambda x: (chance_order.get(x['chance'], 9), -x['gap']))

        # Лучшие варианты
        top = {'safe': None, 'realistic': None, 'dream': None}
        if score is not None:
            for u in result:
                if u['chance'] == 'high' and not top['safe']:
                    top['safe'] = u
                if u['chance'] == 'mid' and not top['realistic']:
                    top['realistic'] = u
            # Dream: низкий шанс, но самый близкий к проходному
            low_chances = [u for u in result if u['chance'] == 'low']
            if low_chances:
                top['dream'] = low_chances[0]

        return Response({
            'universities': result,
            'total': len(result),
            'top': top,
            'score': score,
        })


class UniversityTypeListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        types = [{'id': t[0], 'label': t[1]} for t in University.TYPE_CHOICES]
        return Response(types)
