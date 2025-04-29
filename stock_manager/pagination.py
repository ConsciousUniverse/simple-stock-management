from .models import Admin
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

class CustomPagination(PageNumberPagination):
    def get_page_size(self, request):
        # Use the admin-configured value unless overridden by query param
        try:
            return int(request.query_params.get('page_size', Admin.get_records_per_page()))
        except Exception:
            return 25
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            'results': data,
            'current_page': self.page.number,
            'total_pages': self.page.paginator.num_pages,
            'previous': self.get_previous_link(),
            'next': self.get_next_link(),
            'previous_page_number': self.page.previous_page_number() if self.page.has_previous() else None,
            'next_page_number': self.page.next_page_number() if self.page.has_next() else None,
        })
