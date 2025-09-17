from rest_framework import viewsets
from .models import Paper, SavedPaper
from .serializers import PaperSerializer, SavedPaperSerializer

class PaperViewSet(viewsets.ModelViewSet):
    queryset = Paper.objects.all()
    serializer_class = PaperSerializer

class SavedPaperViewSet(viewsets.ModelViewSet):
    queryset = SavedPaper.objects.all()
    serializer_class = SavedPaperSerializer
