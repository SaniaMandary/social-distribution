from django.urls import path
from . import views

app_name = "social_distribution"
urlpatterns = [
    path("", views.index, name="index"),
    path("<int:pk>/", views.DetailView.as_view(), name="detail"),
    path("profiles/<str:username>", views.profile_view, name="profile"),

    path("login/", views.login_view, name="login"),
    path("newentry/",views.newentry_view,name="newentry"),
    path("changeprofile/",views.changeprofile_view,name="changeprofile"),
    
    path("api/editprofile/", views.editprofile,name="editprofile"),
    path("api/addentry/", views.addentry,name="addentry"),
    path("api/signout/", views.signout, name="signout"),
    path("api/loginregister/", views.loginregister, name="loginregister"),
    path("api/entries/", views.get_entries, name="get_entries"),
]