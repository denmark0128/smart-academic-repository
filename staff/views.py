from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test
from papers.models import Paper
from django.http import HttpResponse
from django.contrib import messages
from django.db import transaction
from papers.utils.nlp import extract_tags
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from .models import SearchSettings
from .forms import SearchSettingsForm

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
    return render(request, 'staff/main.html')

def extract_tags_view(request):

    """Extract tags for all papers"""
    
    if request.method == 'POST':
        papers = Paper.objects.all()
        updated_count = 0
        error_count = 0
        errors = []

        with transaction.atomic():
            for paper in papers:
                try:
                    combined_text = " ".join([
                        paper.title or "",
                    ]).strip()

                    if not combined_text:
                        continue

                    tags = extract_tags(combined_text)
                    paper.tags = tags
                    paper.save(update_fields=["tags"])
                    updated_count += 1

                except Exception as e:
                    error_count += 1
                    errors.append(f"{paper.title}: {str(e)}")

        # Show results
        messages.success(request, f"✅ Successfully updated {updated_count} papers!")
        if error_count > 0:
            messages.warning(request, f"⚠️ {error_count} errors occurred.")
            for error in errors[:10]:  # Show first 10 errors
                messages.error(request, error)
        
        return redirect('extract_tags')
    
    # GET request - show confirmation page
    papers_count = Paper.objects.count()
    context = {
        'papers_count': papers_count,
    }
    return render(request, 'papers/extract_tags.html', context)

