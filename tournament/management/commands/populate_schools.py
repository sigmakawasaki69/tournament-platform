import requests
from django.core.management.base import BaseCommand
from tournament.models import School

class Command(BaseCommand):
    help = 'Populates the database with schools from the official EDBO API'

    def handle(self, *args, **options):
        url = "https://registry.edbo.gov.ua/api/institutions/?ut=3&exp=json"
        self.stdout.write(f"Fetching data from {url}...")
        
        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            self.stderr.write(f"Error fetching data: {e}")
            return

        self.stdout.write(f"Found {len(data)} institutions. Importing...")
        
        schools_to_create = []
        seen_names = set(School.objects.values_list('name', flat=True))
        
        count = 0
        for item in data:
            name = item.get('institution_name', '').strip()
            short_name = item.get('short_name', '').strip()
            city = item.get('region_name', '').strip()
            
            if not name or name in seen_names:
                continue
                
            schools_to_create.append(School(
                name=name,
                short_name=short_name,
                city=city
            ))
            seen_names.add(name)
            count += 1
            
            if len(schools_to_create) >= 1000:
                School.objects.bulk_create(schools_to_create)
                schools_to_create = []
                self.stdout.write(f"Imported {count} schools...")

        if schools_to_create:
            School.objects.bulk_create(schools_to_create)
            self.stdout.write(f"Imported {count} schools total.")
        
        self.stdout.write(self.style.SUCCESS('Successfully populated schools.'))
