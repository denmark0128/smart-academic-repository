from rest_framework import serializers
from .models import Paper, SavedPaper

class PaperSerializer(serializers.ModelSerializer):
    class Meta:
        model = Paper
        fields = '__all__'

class SavedPaperSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedPaper
        fields = '__all__'
