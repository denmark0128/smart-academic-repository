from django.core.management.base import BaseCommand
from papers.models import Tag
import os
import json

class Command(BaseCommand):
    help = 'Import tags from a JSON file into database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default='F:\\python\\thesis\\paperrepo\\bank_of_words.json',
            help='Path to JSON file containing tags'
        )   

    def handle(self, *args, **options):
        file_path = options['file']
        
        if not os.path.exists(file_path):
            self.stderr.write(self.style.ERROR(f"File not found: {file_path}"))
            return
        
        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                tags_data = json.load(f)
            except json.JSONDecodeError as e:
                self.stderr.write(self.style.ERROR(f"Invalid JSON: {e}"))
                return
        
        created_count = 0
        existing_count = 0
        
        for tag_dict in tags_data:
            name = tag_dict.get('name', '').strip()
            description = tag_dict.get('description', '').strip()
            if not name:
                continue
            
            tag, created = Tag.objects.get_or_create(
                name=name.lower(),
                defaults={
                    'description': description,
                    'is_active': True  # if your model has this field
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(f"✅ Created: {name}")
            else:
                # Update description if empty or changed
                if description and tag.description != description:
                    tag.description = description
                    tag.save()
                existing_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f"\n✅ Import complete!\n"
                f"   Created: {created_count} new tags\n"
                f"   Existing: {existing_count} tags\n"
                f"   Total: {Tag.objects.count()} tags in database"
            )
        )
