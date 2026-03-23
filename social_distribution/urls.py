from django.urls import path
from . import views

app_name = "social_distribution"
urlpatterns = [
    # Web UI - General 
    path("", views.index, name="index"),
    path("<int:pk>/", views.DetailView.as_view(), name="detail"),
    path("authors/<str:author_username>/entries/<int:pk>/", views.DetailView.as_view(), name="author_entry_detail_web"),
    path("profiles/<str:username>/", views.profile_view, name="profile"),
    path("authors/<str:username>/", views.profile_view, name="author_profile"),
    path("login/", views.login_view, name="login"),
    path("newentry/",views.newentry_view,name="newentry"),
    path("changeprofile/",views.changeprofile_view,name="changeprofile"),
    path("nodes/", views.nodes_view, name="nodes"),
    path("discover/", views.discover_remote_authors, name="discover"),

    # Web UI - Social (Follow, Unfollow)
    path("follow/<str:username>/", views.follow_author, name="follow_author"),
    path("follow_by_serial/<uuid:serial>/", views.follow_by_serial, name="follow_by_serial"),
    path("unfollow/<str:username>/", views.unfollow, name="unfollow"),
    path("follow_requests/", views.follow_requests, name="follow_requests"),
    path("approve_follow/<uuid:serial>/", views.approve_follow, name="approve_follow"),
    path("reject_follow/<uuid:serial>/", views.reject_follow, name="reject_follow"),

    # Web UI - List views
    path("authors/", views.author_list, name="author_list"),
    path("followers/", views.followers_list, name="followers_list"),
    path("following/", views.following_list, name="following_list"),
    path("friends/", views.friends_list, name="friends_list"),

    
    #Web UI - General - API helper endpoints (local only) 
    path("api/editprofile/", views.editprofile,name="editprofile"),
    path("api/addentry/", views.addentry,name="addentry"),
    path("api/signout/", views.signout, name="signout"),
    path("api/loginregister/", views.loginregister, name="loginregister"),
    path("api/entries/", views.get_entries, name="get_entries"), # gets local feed 

    # Likes on an Authors Entry, likes on a comment that was posted on an Authors entry 
    path("api/authors/<uuid:author_serial>/entries/<int:entry_serial>/likes/", views.api_entry_likes, name="api_entry_likes"),
    path("api/authors/<uuid:author_serial>/entries/<int:entry_serial>/comments/<path:comment_fqid>/likes/", views.api_comment_likes, name="api_comment_likes"),


    # Authors or singular Author 
    path("api/authors/", views.api_authors, name="api_authors"), # All authors
    path("api/authors/<uuid:author_serial>/", views.api_single_author, name="api_single_author"), # Specific Author 

    # Author followers, following, follow requests. 
    path("api/authors/<uuid:author_serial>/followers/", views.api_author_followers, name="api_author_followers"),
    path("api/authors/<uuid:author_serial>/followers/<path:foreign_author_fqid>/", views.api_author_follower_detail, name="api_author_follower_detail"),
    path("api/authors/<uuid:author_serial>/following/", views.api_author_following, name="api_author_following"),
    path("api/authors/<uuid:author_serial>/following/<path:foreign_author_fqid>/", views.api_author_following_detail, name="api_author_following_detail"),
    path("api/authors/<uuid:author_serial>/follow_requests/", views.api_follow_requests, name="api_follow_requests"),

    # Inbox API
    path("api/authors/<uuid:author_serial>/inbox/", views.api_inbox, name="api_inbox"),
    
    # Authors entries, specific Author entry, specific Author entry image. 
    path("api/authors/<uuid:author_serial>/entries/", views.api_author_entries, name="api_author_entries"),
    path("api/authors/<uuid:author_serial>/entries/<int:entry_serial>/", views.api_author_entry_detail, name="api_author_entry_detail"),
    path("api/authors/<uuid:author_serial>/entries/<int:entry_serial>/image/", views.api_entry_image, name="api_entry_image"),

    # Comments on a specific Entry or a specific Comment from a specific Entry. 
    path("api/authors/<uuid:author_serial>/entries/<int:entry_serial>/comments/", views.api_entry_comments, name="api_entry_comments"),
    path("api/authors/<uuid:author_serial>/entries/<int:entry_serial>/comments/<path:comment_fqid>/", views.api_entry_comment_detail, name="api_entry_comment_detail"),

    # Comments made by an Author
    path("api/authors/<uuid:author_serial>/commented/", views.api_author_commented, name="api_author_commented"),
    path("api/authors/<uuid:author_serial>/commented/<int:comment_serial>/", views.api_author_comment_by_serial, name="api_author_comment_by_serial"),
    path("api/commented/<path:comment_fqid>/", views.api_comment_fqid, name="api_comment_fqid"),

    # Likes made by an Author 
    path("api/authors/<uuid:author_serial>/liked/", views.api_author_liked, name="api_author_liked"),
    path("api/authors/<uuid:author_serial>/liked/<int:like_serial>/", views.api_author_like_by_serial, name="api_author_like_by_serial"),
    path("api/liked/<path:like_fqid>/", views.api_like_fqid, name="api_like_fqid"),

    # FQID-based liked and commented
    path("api/authors/<path:author_fqid>/liked/", views.api_author_liked_fqid, name="api_author_liked_fqid"),
    path("api/authors/<path:author_fqid>/commented/", views.api_author_commented_fqid, name="api_author_commented_fqid"),

    # FQID-based single author lookup
    path("api/authors/<path:author_fqid>/", views.api_single_author_fqid, name="api_single_author_fqid"),

    # Global FQID-based entry endpoints
    path("api/entries/<path:entry_fqid>/image/", views.api_entry_fqid_image, name="api_entry_fqid_image"),
    path("api/entries/<path:entry_fqid>/comments/", views.api_entry_fqid_comments, name="api_entry_fqid_comments"),
    path("api/entries/<path:entry_fqid>/likes/", views.api_entry_fqid_likes, name="api_entry_fqid_likes"),
    path("api/entries/<path:entry_fqid>/", views.api_entry_fqid, name="api_entry_fqid"),
]