# Web UI pages
from .webpages import (
    index, profile_view, DetailView, login_view,
    newentry_view, changeprofile_view, nodes_view,
    discover_remote_authors, author_list,
    followers_list, following_list, friends_list,
)
 
# Auth and form submissions
from .auth import loginregister, signout, editprofile, addentry
 
# Social web UI actions
from .social import (
    follow_requests, follow_author, follow_by_serial,
    approve_follow, reject_follow, unfollow,
)
 
# Entry API endpoints
from .api.entries import (
    get_entries, api_author_entries, api_author_entry_detail,
    api_entry_image, api_entry_fqid, api_entry_fqid_image,
)
 
# Social API endpoints (authors, followers, likes, comments, inbox)
from .api.social import (
    api_authors, api_single_author, api_single_author_fqid,
    api_author_followers, api_author_follower_detail,
    api_author_following, api_author_following_detail,
    api_follow_requests,
    api_entry_likes, api_comment_likes,
    api_author_liked, api_author_like_by_serial, api_like_fqid,
    api_author_liked_fqid,
    api_entry_comments, api_entry_comment_detail,
    api_author_commented, api_author_comment_by_serial,
    api_comment_fqid, api_author_commented_fqid,
    api_entry_fqid_comments, api_entry_fqid_likes,
    api_inbox,
)
 