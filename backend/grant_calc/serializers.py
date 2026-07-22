from rest_framework import serializers
from .models import University


class UniversitySerializer(serializers.ModelSerializer):
    uni_type_display = serializers.CharField(source='get_uni_type_display', read_only=True)

    class Meta:
        model = University
        fields = ('id', 'name', 'city', 'uni_type', 'uni_type_display',
                  'icon', 'min_score', 'specializations', 'info')


class GrantCalcRequestSerializer(serializers.Serializer):
    score = serializers.IntegerField(min_value=50, max_value=140)
    search = serializers.CharField(required=False, default='')
    uni_type = serializers.CharField(required=False, default='all')
