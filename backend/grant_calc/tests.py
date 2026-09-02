from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from .models import University


class GrantCalcApiTest(TestCase):
    def setUp(self):
        call_command('seed_universities', verbosity=0)

    def test_universities_returned_with_chance(self):
        client = APIClient()
        response = client.get('/api/grant-calc/', {'score': 100})
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.data['total'], 0)
        self.assertEqual(len(response.data['universities']), response.data['total'])
        first = response.data['universities'][0]
        self.assertIn(first['chance'], ('high', 'mid', 'low'))
        self.assertIn('gap', first)
        # Отсортированы: high идут раньше low
        chances = [u['chance'] for u in response.data['universities']]
        self.assertEqual(chances, sorted(chances, key=lambda c: {'high': 0, 'mid': 1, 'low': 2}[c]))

    def test_search_filters_by_city(self):
        client = APIClient()
        response = client.get('/api/grant-calc/', {'search': 'Алмат'})
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.data['total'], 0)
        for u in response.data['universities']:
            self.assertEqual(u['city'], 'Алматы')

    def test_search_filters_by_name(self):
        client = APIClient()
        response = client.get('/api/grant-calc/', {'search': 'Сатпаева'})
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.data['total'], 0)
        for u in response.data['universities']:
            self.assertIn('Сатпаева', u['name'])

    def test_top_block_populated(self):
        client = APIClient()
        response = client.get('/api/grant-calc/', {'score': 100})
        self.assertEqual(response.status_code, 200)
        top = response.data['top']
        self.assertIn('safe', top)
        self.assertIn('realistic', top)
        self.assertIn('dream', top)

    def test_uni_type_filter(self):
        client = APIClient()
        response = client.get('/api/grant-calc/', {'uni_type': 'medical'})
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.data['total'], 0)
        for u in response.data['universities']:
            self.assertEqual(u['uni_type'], 'medical')

    def test_types_endpoint(self):
        client = APIClient()
        response = client.get('/api/grant-calc/types/')
        self.assertEqual(response.status_code, 200)
        labels = {t['id']: t['label'] for t in response.data}
        self.assertEqual(labels['medical'], 'Медицинский')
