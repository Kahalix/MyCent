from django.urls import path
from rest_framework.routers import DefaultRouter
from saved.api_views import MySavedListingsViewSet, MySavedSearchesViewSet

router = DefaultRouter()
router.register(r'api/users/me/saved/listings', MySavedListingsViewSet, basename='my-saved-listings')
router.register(r'api/users/me/saved/searches', MySavedSearchesViewSet, basename='my-saved-searches')
urlpatterns = router.urls
