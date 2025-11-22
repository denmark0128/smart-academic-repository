from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test
from papers.models import Paper, Tag
from .models import SearchSettings, LlamaSettings
from .forms import SearchSettingsForm, LlamaSettingsForm
from django.http import HttpResponse
from django.core.cache import cache
from django.contrib import messages
from django.core.paginator import Paginator
from utils.tagging import get_embedding_model, extract_tags
import re

def staff_table_partial(request):
    papers = Paper.objects.order_by('-uploaded_at')[:5]
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

def staff_dashboard_partial(request):
    return render(request, 'staff/partials/dashboard.html')

def staff_tags_partial(request):
    """Main tags management page"""
    return render(request, 'staff/partials/tags_partial.html')

def staff_tags_table(request):
    """Tags table partial with search and filtering"""
    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')
    
    # Base queryset
    tags_list = Tag.objects.all()
    
    # Apply search filter
    if query:
        tags_list = tags_list.filter(name__icontains=query)
    
    # Apply status filter
    if status_filter == 'active':
        tags_list = tags_list.filter(is_active=True)
    elif status_filter == 'inactive':
        tags_list = tags_list.filter(is_active=False)
    
    # Order by active status and name
    tags_list = tags_list.order_by('name')
    
    # Add paper count to each tag
    for tag in tags_list:
        tag.paper_count = Paper.objects.filter(tags__contains=[tag.name]).count()
    
    # Highlight search term in results (optional)
    if query:
        for tag in tags_list:
            # Highlight the search term
            pattern = re.compile(f'({re.escape(query)})', re.IGNORECASE)
            tag.name = pattern.sub(r'<mark class="bg-yellow-200">\1</mark>', tag.name)
    
    # Pagination
    page_number = request.GET.get('page', 1)
    paginator = Paginator(tags_list, 50)  # 20 tags per page
    tags = paginator.get_page(page_number)
    
    context = {
        'tags': tags,
        'query': query,
        'status_filter': status_filter,
    }

    return render(request, 'staff/partials/tags_table_partial.html', context)

def staff_tags_create(request):
    """Create new tag"""
    if request.method == 'POST':
        tag_name = request.POST.get('tag_name', '').strip().lower()
        tag_description = request.POST.get('tag_description', '').strip()  # NEW: get description
        
        if tag_name:
            tag, created = Tag.objects.get_or_create(
                name=tag_name,
                defaults={
                    'description': tag_description,  # NEW: store description
                    'is_active': True
                }
            )
            if created:
                cache.delete('active_tags_list')  # Clear cache
                messages.success(request, f'Tag "{tag_name}" created successfully!')
            else:
                messages.info(request, f'Tag "{tag_name}" already exists.')
    
    return staff_tags_table(request)


def staff_tags_update(request, tag_id):
    """Update tag name"""
    if request.method == 'POST':
        tag = get_object_or_404(Tag, id=tag_id)
        new_name = request.POST.get('tag_name', '').strip().lower()
        
        if new_name and new_name != tag.name:
            # Check if new name already exists
            if Tag.objects.filter(name=new_name).exclude(id=tag_id).exists():
                messages.error(request, f'Tag "{new_name}" already exists.')
            else:
                old_name = tag.name
                tag.name = new_name
                tag.save()
                cache.delete('active_tags_list')  # Clear cache
                messages.success(request, f'Tag renamed from "{old_name}" to "{new_name}"')
    
    return staff_tags_table(request)

def staff_tags_toggle(request, tag_id):
    """Toggle tag active status"""
    tag = get_object_or_404(Tag, id=tag_id)
    tag.is_active = not tag.is_active
    tag.save()
    cache.delete('active_tags_list')  # Clear cache
    
    status = "activated" if tag.is_active else "deactivated"
    messages.success(request, f'Tag "{tag.name}" {status}')
    
    return staff_tags_table(request)

def staff_tags_delete(request, tag_id):

    """Delete tag"""
    tag = get_object_or_404(Tag, id=tag_id)
    tag_name = tag.name
    tag.delete()
    cache.delete('active_tags_list')  # Clear cache
    
    messages.success(request, f'Tag "{tag_name}" deleted successfully')
    
    return staff_tags_table(request)

def staff_tags_generate_embedding(request, tag_id):
    """Generate embedding for a single tag using the tag description"""
    if request.method == 'POST':
        tag = get_object_or_404(Tag, id=tag_id)
        
        try:
            print(f"[Embedding] Generating embedding for tag: {tag.name}")
            model = get_embedding_model()
            
            # Use description for embedding if available, otherwise fallback to name
            text_to_embed = tag.description or tag.name
            embedding = model.encode(text_to_embed)
            
            # Store as numpy array (pgvector handles this)
            tag.embedding = embedding
            tag.save(update_fields=['embedding'])
            
            # Clear cache
            cache.delete('active_tags_with_embeddings')
            
            messages.success(request, f"Generated embedding for '{tag.name}'")
            print(f"[Embedding] Successfully generated for tag ID {tag.id}")
            
        except Exception as e:
            messages.error(request, f"Error generating embedding: {str(e)}")
            print(f"[Embedding Error] {e}")
    
    # Return the existing partial table
    return staff_tags_table(request)

def staff_papers_partial(request):
    return render(request, 'staff/partials/papers_partial.html')

def staff_papers_table_partial(request, extra_context=None):
    """Main tags management page"""
    papers = Paper.objects.all()
    context = {'papers': papers}
    if extra_context:
        context.update(extra_context)
    return render(request, 'staff/partials/papers_table_partial.html', context)


def staff_paper_regenerate_tags(request, paper_id):
    """Regenerate tags for a paper using AI (optimized)"""
    if request.method == 'POST':
        paper = get_object_or_404(Paper, id=paper_id)
        
        try:
            print(f"[Regenerate Tags] Processing paper: {paper.title}")
            
            tags_with_scores = None

            # 1. ✅ FAST PATH: Try to use pre-computed abstract embedding
            if paper.abstract_embedding is not None:
                print("[Regenerate Tags] Using pre-computed abstract_embedding.")
                tags_with_scores = extract_tags(doc_emb=paper.abstract_embedding)
            
            # 2. ✅ FAST PATH 2: Try to use pre-computed title embedding
            elif paper.title_embedding is not None:
                print("[Regenerate Tags] Using pre-computed title_embedding.")
                tags_with_scores = extract_tags(doc_emb=paper.title_embedding)
            
            # 3. ✅ SLOW PATH (Fallback): No embeddings, use full text
            else:
                print("[Regenerate Tags] No pre-computed embeddings, falling back to full-text.")
                text_for_tagging = _get_paper_text_for_tagging(paper)
                
                if text_for_tagging and text_for_tagging.strip():
                    tags_with_scores = extract_tags(text=text_for_tagging)
                else:
                    messages.error(request, f'No text available for tag extraction')
                    return staff_papers_table_partial(request)
            
            # 4. Process the results
            if tags_with_scores:
                tag_names = [t['name'] for t in tags_with_scores]
                print(f"[Regenerate Tags] Extracted tag names: {tag_names}")
                
                # Save only tag names to database
                paper.tags = tag_names
                paper.save(update_fields=['tags'])
                
                # ✅ Set tags_with_scores temporarily for display (not saved to DB)
                paper.tags_with_scores = tags_with_scores
                
                messages.success(
                    request, 
                    f'✓ Regenerated {len(tag_names)} tag(s) for "{paper.title[:50]}..."'
                )
            else:
                print("[Regenerate Tags] No suitable tags found.")
                messages.warning(request, f'No suitable tags found')
                paper.tags = []
                paper.save(update_fields=['tags'])
                
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
            print(f"[Regenerate Tags Error] {e}")
            import traceback
            traceback.print_exc()
    
    # ✅ FIX: Fetch all papers and inject the updated paper with scores
    papers = Paper.objects.all()
    
    # Replace the paper in the queryset with our in-memory version that has tags_with_scores
    papers_list = list(papers)
    for i, p in enumerate(papers_list):
        if p.id == paper.id:
            papers_list[i] = paper  # Replace with our modified paper object
            break
    
    return render(request, 'staff/partials/papers_table_partial.html', {'papers': papers_list})

def _get_paper_text_for_tagging(paper):
    """Helper to safely extract text from paper for tagging"""
    text_parts = []
    
    if paper.title:
        text_parts.append(str(paper.title))
    
    if paper.abstract:
        text_parts.append(str(paper.abstract))
    
    if paper.authors:
        if isinstance(paper.authors, (list, tuple)):
            text_parts.append(" ".join(str(a) for a in paper.authors))
        else:
            text_parts.append(str(paper.authors))
    
    return " ".join(text_parts)


def search_settings_view(request):
    """View for managing search settings"""
    settings = SearchSettings.get_settings()
    
    if request.method == 'POST':
        form = SearchSettingsForm(request.POST, instance=settings)
        if form.is_valid():
            form.save()
            # ✅ CORRECTED: Use the same key defined in utils.py
            cache.delete('active_search_settings') 
            
            # ✅ For HTMX: return just the form fields with fresh data
            form = SearchSettingsForm(instance=settings)
            if request.headers.get('HX-Request'):
                return render(request, 'staff/partials/settings_search_form_fields.html', {
                    'form': form,
                    'success_message': '✅ Search Settings updated successfully!'
                })
    else:
        form = SearchSettingsForm(instance=settings)
    
    return render(request, 'staff/search_settings.html', {
        'form': form,
        'settings': settings
    })

# staff/views.py (add this function to the same file)

def llama_settings_view(request):
    """View for managing Llama settings"""
    settings = LlamaSettings.get_settings()
    
    if request.method == 'POST':
        form = LlamaSettingsForm(request.POST, instance=settings)
        if form.is_valid():
            form.save()
            # ✅ Use the correct cache key for Llama settings
            cache.delete('active_llama_settings') 
            
            # ✅ For HTMX: return just the form fields with fresh data
            form = LlamaSettingsForm(instance=settings)
            # You can reuse the same partial if its structure is generic
            return render(request, 'staff/partials/settings_llama_form_fields.html', {
                'form': form,
                'success_message': '✅ Llama Settings updated successfully!'
            })
    else:
        form = LlamaSettingsForm(instance=settings)
    
    # You'll need a separate template for the full page
    return render(request, 'staff/llama_settings.html', {
        'form': form,
        'settings': settings
    })