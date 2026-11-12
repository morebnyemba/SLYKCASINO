"""Paging for affiliate lists: 25 a page by default, ?page_size= up to 200."""
from rest_framework.pagination import PageNumberPagination


class AffiliatePagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 200
