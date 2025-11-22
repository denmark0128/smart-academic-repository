from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse
from papers.models import Tag
from papers.utils.nlp import get_mpnet_model
from django.core.cache import cache
import numpy as np

@staff_member_required
def staff_tags_generate_embedding(request, tag_id):
    """Generate embedding for a single tag"""
    if request.method == 'POST':
        tag = get_object_or_404(Tag, id=tag_id)
        
        try:
            print(f"[Embedding] Generating embedding for tag: {tag.name}")
            model = get_mpnet_model()
            embedding = model.encode(tag.name)
            
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
    
    # Return updated tags list
    tags = Tag.objects.all().annotate(
        paper_count=models.Count('paper')
    ).order_by('-created_at')
    
    return render(request, 'staff/tags_table.html', {'tags': tags})


@staff_member_required
def staff_tags_bulk_embed(request):
    """Generate embeddings for multiple tags at once"""
    if request.method == 'POST':
        tag_ids = request.POST.getlist('tag_ids')
        
        if not tag_ids:
            messages.warning(request, "No tags selected")
            return redirect('staff_tags')
        
        try:
            model = get_mpnet_model()
            tags = Tag.objects.filter(id__in=tag_ids)
            
            success_count = 0
            error_count = 0
            
            for tag in tags:
                try:
                    print(f"[Bulk Embedding] Processing tag: {tag.name}")
                    embedding = model.encode(tag.name)
                    tag.embedding = embedding
                    tag.save(update_fields=['embedding'])
                    success_count += 1
                except Exception as e:
                    print(f"[Bulk Embedding Error] Tag {tag.id}: {e}")
                    error_count += 1
            
            # Clear cache
            cache.delete('active_tags_with_embeddings')
            
            if success_count > 0:
                messages.success(request, f"Generated embeddings for {success_count} tag(s)")
            if error_count > 0:
                messages.warning(request, f"Failed to generate {error_count} embedding(s)")
                
            print(f"[Bulk Embedding] Success: {success_count}, Errors: {error_count}")
            
        except Exception as e:
            messages.error(request, f"Bulk embedding error: {str(e)}")
            print(f"[Bulk Embedding Error] {e}")
    
    # Return updated tags list
    tags = Tag.objects.all().annotate(
        paper_count=models.Count('paper')
    ).order_by('-created_at')
    
    return render(request, 'staff/tags_table.html', {'tags': tags})