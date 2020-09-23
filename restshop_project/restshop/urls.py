from os import listdir
from os.path import join, isdir
from django.conf.urls import include, url
from rest_framework import routers
from restshop.api.cart.views import CartView
from restshop_project.settings import BASE_DIR
from rest_framework_swagger.views import get_swagger_view



API_DIR = 'restshop/api/'
entities = [directory
            for directory in listdir(join(BASE_DIR, API_DIR))
            if (isdir(join(BASE_DIR, API_DIR, directory))
                and directory != '__pycache__')]


# router = routers.DefaultRouter()
# router.register(r'carts', CartView)
# urlpatterns = router.urls



schema_view = get_swagger_view(title='Pastebin API')

# urlpatterns = [
#     url(r'^$', schema_view)
# ]

urlpatterns = [
    url(r'^', include('restshop.api.{}.urls'.format(entity)))
    for entity in entities
]