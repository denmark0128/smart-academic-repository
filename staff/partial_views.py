from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test
from papers.models import Paper
from django.http import HttpResponse

def staff_table_partial(request):
    papers = Paper.objects.all()
    return render(request, "staff/partials/paper_table.html", {"papers": papers})

def staff_stats_partial(request):
    pending = Paper.objects.filter(is_registered=False).count()
    registered = Paper.objects.filter(is_registered=True).count()
    total = Paper.objects.count()

    stats = {
        'pending': pending,
        'registered': registered,
        'total': total
    }

    return render(request, 'staff/partials/stats_partial.html', {'stats': stats})