from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.views import generic
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import TextEntry
from .serializers import EntrySerializer

class IndexView(generic.ListView):
    template_name = "social_distribution/index.html"
    context_object_name = "latest_entry_list"

    def get_queryset(self):
        """Return the last five published entries."""
        return TextEntry.objects.order_by("-pub_date")[:5]

class DetailView(generic.DetailView):
    model = TextEntry
    context_object_name = "entry"
    template_name = "social_distribution/detail.html"

@api_view(['GET'])
def get_entries(request):
    """
    Get the list of entries on our node
    """
    entries = TextEntry.objects.all()
    serializer = EntrySerializer(entries, many=True)
    return Response(serializer.data)