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
    path("editentry/<int:entry_id>/", views.editentry, name="editentry"),
    path("deleteentry/<int:entry_id>/", views.deleteentry, name="deleteentry"),
    
    path("api/editprofile/", views.editprofile,name="editprofile"),
    path("api/addentry/", views.addentry,name="addentry"),
    path("api/signout/", views.signout, name="signout"),
    path("api/loginregister/", views.loginregister, name="loginregister"),
    path("api/entries/", views.get_entries, name="get_entries"),

    path("api/likes/add/<int:entry_id>/", views.add_like_entry, name="add_like_entry"),
    path("api/likes/", views.add_like, name="add_like"),
    path("api/likes/<path:object_id>/", views.get_likes, name="get_likes"),

    path("follow/<str:username>/", views.follow_author, name="follow_author"),
    path("unfollow/<str:username>/", views.unfollow, name="unfollow"),
    path("follow_requests/", views.follow_requests, name="follow_request"),
    path("approve_follow/<str:username>/", views.approve_follow, name="approve_follow"),

    path("authors/", views.author_list, name="author_list"),

    path("api/entries/<int:entry_id>/comments/", views.get_comments, name="get_comments"),
    path("api/entries/<int:entry_id>/comments/add/", views.post_entry_comment, name="add_comment"),
]
