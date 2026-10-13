import re
from django.shortcuts import render, redirect, get_object_or_404
from .models import Category
from django.utils import timezone
from django.contrib import messages
from admin_side.views import is_admin, admin_required
from django.contrib.auth.decorators import user_passes_test
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.views.decorators.cache import never_cache
from functools import wraps


import base64
from django.core.files.base import ContentFile
from django.http import JsonResponse


def get_image_from_request(request):
    if request.FILES.get('image'):
        return request.FILES.get('image')
    cropped_b64 = request.POST.get('cropped_image_base64', '').strip()
    if cropped_b64 and ';base64,' in cropped_b64:
        try:
            format_part, imgstr = cropped_b64.split(';base64,')
            ext = 'jpg'
            if 'png' in format_part.lower():
                ext = 'png'
            elif 'webp' in format_part.lower():
                ext = 'webp'
            file_data = base64.b64decode(imgstr)
            return ContentFile(file_data, name=f"category_{int(timezone.now().timestamp())}.{ext}")
        except Exception:
            return None
    return None


def validate_category_image(image_file):
    if not image_file:
        return True, None
    if image_file.size > 5 * 1024 * 1024:
        return False, "Category image size must not exceed 5MB."
    allowed_exts = ('.jpg', '.jpeg', '.png', '.webp')
    if not any(image_file.name.lower().endswith(ext) for ext in allowed_exts):
        return False, "Allowed image formats are JPG, JPEG, PNG, and WebP."
    if hasattr(image_file, 'content_type') and image_file.content_type not in ['image/jpeg', 'image/png', 'image/webp']:
        return False, "Invalid image format uploaded."
    return True, None


def validate_category_name(name):
    if not name:
        return False, "Category name is required and cannot be empty or only spaces."
    if len(name) < 2 or len(name) > 50:
        return False, "Category name must be between 2 and 50 characters."
    if not re.match(r'^[A-Za-z0-9\s&-]+$', name):
        return False, "Category name can only contain letters, numbers, spaces, hyphens, and &."
    return True, None


"""
CATEGORY MANAGEMENT
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def category_management(request):
    search_query = request.GET.get('search', '').strip()
    is_ajax = (request.headers.get('x-requested-with') == 'XMLHttpRequest' or 
               request.headers.get('Accept') == 'application/json' or
               request.POST.get('ajax') == 'true')

    if request.method == 'POST':
        category_name = request.POST.get('category_name', '').strip()
        category_image = get_image_from_request(request)

        is_valid_name, name_err = validate_category_name(category_name)
        if not is_valid_name:
            if is_ajax:
                return JsonResponse({'success': False, 'error': name_err})
            messages.error(request, name_err)
            return redirect('category_management')
        elif Category.objects.filter(category_name__iexact=category_name).exists():
            msg = f"A category with name '{category_name}' already exists."
            if is_ajax:
                return JsonResponse({'success': False, 'error': msg})
            messages.error(request, msg)
            return redirect('category_management')
        else:
            is_valid_img, img_err = validate_category_image(category_image)
            if not is_valid_img:
                if is_ajax:
                    return JsonResponse({'success': False, 'error': img_err})
                messages.error(request, img_err)
                return redirect('category_management')
            else:
                Category.objects.create(
                    category_name=category_name,
                    created_at=timezone.now(),
                    image=category_image
                )
                if is_ajax:
                    return JsonResponse({'success': True, 'message': 'Category created successfully!'})
                messages.success(request, "Category created successfully!")
                return redirect('category_management')

    # Search categories based on the search query
    if search_query:
        categories = Category.objects.filter(category_name__icontains=search_query).order_by('-id')
    else:
        categories = Category.objects.all().order_by('-id')

    page = request.GET.get('page', 1)
    paginator = Paginator(categories, 10)

    try:
        categories = paginator.page(page)
    except PageNotAnInteger:
        categories = paginator.page(1)
    except EmptyPage:
        categories = paginator.page(paginator.num_pages)

    return render(request, 'admin/category.html', {
        'categories': categories,
        'search_query': search_query,
    })




"""
EDIT CATEGORY
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def edit_category(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    is_ajax = (request.headers.get('x-requested-with') == 'XMLHttpRequest' or 
               request.headers.get('Accept') == 'application/json' or
               request.POST.get('ajax') == 'true')

    if request.method == 'GET' and (is_ajax or request.GET.get('format') == 'json'):
        return JsonResponse({
            'success': True,
            'id': category.id,
            'category_name': category.category_name,
            'image_url': category.image.url if category.image else '',
        })

    if request.method == 'POST':
        category_name = request.POST.get('category_name', '').strip()
        category_image = get_image_from_request(request)

        is_valid_name, name_err = validate_category_name(category_name)
        if not is_valid_name:
            if is_ajax:
                return JsonResponse({'success': False, 'error': name_err})
            messages.error(request, name_err)
            return redirect('category_management')
        elif Category.objects.filter(category_name__iexact=category_name).exclude(id=category_id).exists():
            msg = f"Another category with name '{category_name}' already exists."
            if is_ajax:
                return JsonResponse({'success': False, 'error': msg})
            messages.error(request, msg)
            return redirect('category_management')
        else:
            is_valid_img, img_err = validate_category_image(category_image)
            if not is_valid_img:
                if is_ajax:
                    return JsonResponse({'success': False, 'error': img_err})
                messages.error(request, img_err)
                return redirect('category_management')
            else:
                category.category_name = category_name
                if category_image:
                    category.image = category_image
                category.save()
                if is_ajax:
                    return JsonResponse({'success': True, 'message': 'Category updated successfully!'})
                messages.success(request, 'Category updated successfully')
                return redirect('category_management')

    return render(request, 'admin/edit_category.html', {'category': category})





"""
CATEGORY ACTIVATE/DEACTIVATE
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def toggle_listing(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    category.is_listed = not category.is_listed
    category.save()
    messages.success(request, f"Category {'unlisted' if not category.is_listed else 'relisted'} successfully!")
    return redirect('category_management')


"""
DELETE CATEGORY
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def delete_category(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    category_name = category.category_name
    is_ajax = (request.headers.get('x-requested-with') == 'XMLHttpRequest' or 
               request.headers.get('Accept') == 'application/json' or
               request.POST.get('ajax') == 'true')

    category.delete()

    if is_ajax:
        return JsonResponse({'success': True, 'message': f"Category '{category_name}' deleted successfully!"})

    messages.success(request, f"Category '{category_name}' deleted successfully!")
    return redirect('category_management')

    

