from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test
from papers.models import Paper
from django.http import HttpResponse

def staff_required(view_func):
    return user_passes_test(lambda u: u.is_authenticated and u.is_staff)(view_func)

@staff_required
def dashboard(request):
    papers = Paper.objects.filter(is_registered=False)
    return render(request, 'staff/dashboard.html', {'papers': papers})

@staff_required
def approve_paper(request, pk):
    paper = get_object_or_404(Paper, pk=pk)

    if request.method == 'POST':
        doi = request.POST.get('doi')
        paper.local_doi = doi
        paper.is_registered = True
        paper.save()
        return redirect('staff_dashboard')

    return render(request, 'staff/approve_paper.html', {'paper': paper})

@staff_required
def reject_paper(request, pk):
    paper = get_object_or_404(Paper, pk=pk)
    paper.delete()
    return redirect('staff_dashboard')

@staff_required
def staff_dashboard(request):
    # Default view shows pending
    papers = Paper.objects.filter(is_registered=False)
    return render(request, "staff/dashboard.html", {"papers": papers})

@staff_required
def staff_pending_papers(request):
    papers = Paper.objects.filter(is_registered=False)
    return render(request, "staff/partials/paper_table.html", {"papers": papers})

@staff_required
def staff_registered_papers(request):
    papers = Paper.objects.filter(is_registered=True)
    return render(request, "staff/partials/paper_table.html", {"papers": papers})

def review_paper(request, pk):
    paper = get_object_or_404(Paper, pk=pk)
    return render(request, "staff/review_modal.html", {"paper": paper})

def approve_paper(request, pk):
    paper = get_object_or_404(Paper, pk=pk)
    paper.is_registered = True
    paper.save()
    return HttpResponse("<p class='text-green-600 font-semibold'>Paper approved and DOI assigned.</p>")

def staff_dashboard(request):
    pending = Paper.objects.filter(is_registered=False).count()
    registered = Paper.objects.filter(is_registered=True).count()
    total = Paper.objects.count()

    stats = {
        'pending': pending,
        'registered': registered,
        'total': total
    }

    papers = Paper.objects.filter(is_registered=False)  # default: pending list
    return render(request, 'staff/dashboard.html', {'stats': stats, 'papers': papers})