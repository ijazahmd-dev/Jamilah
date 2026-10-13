import os
import sys
import time
import django
from concurrent.futures import ThreadPoolExecutor, as_completed

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mainproject.settings')
django.setup()

import cloudinary
import cloudinary.uploader
from django.conf import settings

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.ico', '.bmp')

def get_resource_type_and_id(prefix, rel_path):
    ext = os.path.splitext(rel_path)[1].lower()
    if ext in IMAGE_EXTENSIONS:
        # In Cloudinary, image public_ids omit extension
        rel_no_ext = os.path.splitext(rel_path)[0]
        public_id = f"{prefix}/{rel_no_ext}"
        resource_type = "image"
    else:
        # Raw assets (css, js, svg, fonts) retain extension in public_id
        public_id = f"{prefix}/{rel_path}"
        resource_type = "raw"
    return resource_type, public_id

def main():
    print("=" * 65)
    print("    ZAYRAH HIGH-PERFORMANCE CLOUDINARY ASSET SYNC")
    print("=" * 65)

    cloud_name = settings.CLOUDINARY_STORAGE.get('CLOUD_NAME')
    print(f"Target Cloudinary Account: {cloud_name}")

    BASE_DIR = settings.BASE_DIR
    STATIC_DIR = os.path.join(BASE_DIR, 'static')
    MEDIA_DIR = os.path.join(BASE_DIR, 'media')

    tasks = []

    # 1. Scan static files
    print("\nScanning static files in:", STATIC_DIR)
    for root, _, files in os.walk(STATIC_DIR):
        for f in files:
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, STATIC_DIR)
            resource_type, public_id = get_resource_type_and_id("static", rel_path)
            tasks.append(("STATIC", rel_path, full_path, public_id, resource_type, "static"))

    # 2. Scan media files
    if os.path.exists(MEDIA_DIR):
        print("Scanning media files in:", MEDIA_DIR)
        for root, _, files in os.walk(MEDIA_DIR):
            for f in files:
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, MEDIA_DIR)
                resource_type, public_id = get_resource_type_and_id("media", rel_path)
                tasks.append(("MEDIA", rel_path, full_path, public_id, resource_type, "media"))

    print(f"Total files queued for sync: {len(tasks)}")

    def upload_worker(item):
        cat, rel_path, full_path, public_id, resource_type, tag = item
        try:
            res = cloudinary.uploader.upload(
                full_path,
                public_id=public_id,
                resource_type=resource_type,
                overwrite=True,
                tags=tag,
                timeout=15
            )
            return (True, cat, rel_path, res.get('secure_url'))
        except Exception as e:
            return (False, cat, rel_path, str(e))

    start_time = time.time()
    success_count = 0
    fail_count = 0

    print("\nStarting concurrent uploads (max_workers=10)...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(upload_worker, task) for task in tasks]
        total = len(futures)

        for i, fut in enumerate(as_completed(futures), 1):
            success, cat, rel_path, info = fut.result()
            if success:
                success_count += 1
                if i % 50 == 0 or i == total or "assets/img" in rel_path or cat == "MEDIA":
                    print(f"[{i:4d}/{total}] OK ({cat}): {rel_path} -> {info}")
            else:
                fail_count += 1
                print(f"[{i:4d}/{total}] ERR ({cat}): {rel_path} -> {info}")

    elapsed = time.time() - start_time
    print("\n" + "=" * 65)
    print(f"SYNC FINISHED in {elapsed:.1f} seconds!")
    print(f"Successfully Synced: {success_count} | Failed: {fail_count}")
    print("=" * 65)

if __name__ == "__main__":
    main()
