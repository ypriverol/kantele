from django.conf.urls import url
from dashboard import views


app_name = 'dash'
urlpatterns = [
    url(r'^$', views.dashboard, name='dash'),
    url(r'^longqc/(?P<instrument_id>[0-9]+)$', views.show_qc, name='longqc'),
]
