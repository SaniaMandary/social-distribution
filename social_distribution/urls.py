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

    path("api/likes/add/<int:entry_id>/", views.add_like_entry, name="add_like_entry"),
    path("api/likes/", views.add_like, name="add_like"),
    path("api/likes/<path:object_id>/", views.get_likes, name="get_likes"),

    path("follow/<str:username>/", views.follow_author, name="follow_author"),
    path("unfollow/<str:username>/", views.unfollow, name="unfollow"),
    path("follow_requests/", views.follow_requests, name="follow_requests"),
    path("approve_follow/<str:username>/", views.approve_follow, name="approve_follow"),
    path("reject_follow/<str:username>/", views.reject_follow, name="reject_follow"),

    path("authors/", views.author_list, name="author_list"),
    path("followers/", views.followers_list, name="followers_list"),
    path("following/", views.following_list, name="following_list"),
    path("friends/", views.friends_list, name="friends_list"),

    # Authors REST API
    path("api/authors/", views.api_authors, name="api_authors"),
    path("api/authors/<str:username>/followers/", views.api_author_followers, name="api_author_followers"),
    path("api/authors/<str:username>/following/", views.api_author_following, name="api_author_following"),

    # Entry REST API
    path("api/entries/<int:entry_id>/comments/add/", views.post_entry_comment, name="add_comment"),
    path("api/entries/<int:entry_id>/comments/", views.get_comments, name="get_comments"),
    path("api/entries/<int:entry_id>/", views.api_entry_detail, name="api_entry_detail"),

    path("api/comments/<int:comment_id>/likes/", views.add_like_comment, name="add_like_comment"),

    # Author-scoped entry API
    path("api/authors/<str:username>/entries/<int:entry_id>", views.public_user_entry, name="public_user_entry"),
    path("api/entries/<int:entry_id>", views.public_get_entry, name="public_get_entry"),
    path("api/authors/<str:username>/entries/", views.public_user_entries, name="public_user_entries"),
    path("api/authors/<str:username>/entries/<int:entry_id>/image", views.get_entry_image, name="get_entry_image"),
    # 
]
