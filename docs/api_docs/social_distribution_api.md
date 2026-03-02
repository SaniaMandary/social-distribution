Social Distribution API Documentation

**Base URL:** `/social_distribution/`  
**Authentication:** Django session cookies. Obtain a session via the login endpoint first. 

## Table of Contents 
- [Authentication](#authentication)
- [Profile](#profile) 
- [Entries](#entries)
- [Likes](#likes)
- [Comments](#comments)
- [Follow / Social](#follow--social)
- [Error Reference](#error-reference)

------------------------------------------

## Authentication 

## POST '/api/loginregsiter/' 

**When to use:** When a user wants to log in with existing credentials, or create a new account. Both flows are handled automatically by this single endpoint.

**How to use:** Send a POST request with form-encoded `username` and `password`. If the user exists and credentials match, the session is established. If the user does not exist, a new account is automatically created.

**Why to use:** Combines login and registration into one endpoint, reducing the number of calls needed for authentication flows.

**Why NOT to use:** Do not use for password changes or account management — this endpoint only handles initial authentication and registration.

**Auth Required:** no

#### Request Fields

Field: | 'username' | Type: | string |  Example: | '"john doe"'  | 
       | 'password' |       | string |           | '"hunter2"' | 

Description:
| `username` | string | `"john_doe"` | The unique username. Also used as the primary key for the Author model. |
| `password` | string | `"hunter2"` | The account password. Stored as a hash by Django. |


#### Response Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| redirect | HTTP 302 | `/social_distribution/` | On successful login, redirects to the home feed. |
| `message` | string | `"Created new user john_doe"` | On new registration, shows a confirmation message in the login page. |
| `message` | string | `"Invalid username or password"` | On failed login (wrong password), shows an error in the login page. |

#### Request Example

```
POST /social_distribution/api/loginregister/
Content-Type: application/x-www-form-urlencoded

username=john_doe&password=hunter2
```

#### Response Example

```json
// Success → HTTP 302 redirect to /social_distribution/

// New user created
{ "message": "Created new user john_doe" }

// Wrong password
{ "message": "Invalid username or password" }
```

### POST `/api/signout/`

**When to use:** When the authenticated user wants to log out and invalidate their session.

**How to use:** Send a POST request with the CSRF token. The server clears the session and redirects to the home page.

**Why to use:** Properly invalidates the server-side session, preventing unauthorized reuse of session cookies.

**Why NOT to use:** Do not call this on behalf of another user — it always signs out the currently authenticated session only.

**Auth Required:** Yes

#### Request Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `X-CSRFToken` | string (header) | `"abc123..."` | Required CSRF token from the session cookie. |

#### Response Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| redirect | HTTP 302 | `/social_distribution/` | Redirects to the home page after logout. |

#### Request Example

```
POST /social_distribution/api/signout/
X-CSRFToken: abc123...
```

## Profile

### POST `/api/editprofile/`

**When to use:** When the authenticated user wants to update their display name, bio, profile picture URL, or GitHub handle.

**How to use:** Send a POST request with all four form fields. All fields are required by the `ChangeProfileForm` validator.

**Why to use:** Allows users to personalize their public profile as seen by other users on the platform.

**Why NOT to use:** Do not use to change username or password. All four fields must be present or validation will fail.

**Auth Required:** Yes

#### Request Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `name` | string | `"John Doe"` | The user's display name shown on their profile and posts. |
| `description` | string | `"I love almonds!"` | A short bio displayed on the user's public profile page. |
| `picture` | string (URL) | `"https://example.com/pic.jpg"` | URL to the user's profile picture. Must be publicly accessible. |
| `github` | string (URL) | `"https://github.com/johndoe"` | The user's GitHub profile URL, displayed on their profile. |

#### Response Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| redirect | HTTP 302 | `/social_distribution/` | On success, redirects to the home feed. |
| `message` | string | `"Form requirements failed..."` | On validation error, re-renders the profile form with an error message. |

#### Request Example

```
POST /social_distribution/api/editprofile/
Content-Type: application/x-www-form-urlencoded

name=John+Doe&description=I+love+almonds&picture=https://example.com/pic.jpg&github=https://github.com/johndoe
```


## Entries

### GET `/api/entries/`

**When to use:** Use to retrieve all non-deleted entries on the node regardless of author. Useful for admin views or  feed aggregation.

**How to use:** Send a GET request. No authentication or parameters required. Returns a flat JSON array of entry objects.

**Why to use:** Provides a public feed of all content on the node, enabling other nodes or public clients to read posts.

**Why NOT to use:** Returns ALL entries without visibility filtering. Do not use to render a personal feed instead use the filtered index view.

**Auth Required:** No  
**Paginated:** No

#### Response Fields


| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `id` | integer | `42` | Unique identifier for the entry. |
| `belonging_url` | string | `"john_doe"` | Username of the author who owns this entry. |
| `entry_text` | string | `"Hello world!"` | The raw text content of the entry. |
| `pub_date` | datetime | `"2026-03-01T12:00:00Z"` | ISO 8601 timestamp of when the entry was published. |
| `content_type` | string | `"text/plain"` | MIME type. Either `text/plain` or `text/markdown`. |
| `visibility` | string | `"PUBLIC"` | Visibility setting: `PUBLIC` or `FRIENDS`. |

#### Response Example

```json
[
  {
    "id": 42,
    "belonging_url": "john_doe",
    "entry_text": "Hello world!",
    "pub_date": "2026-03-01T12:00:00Z",
    "content_type": "text/plain",
    "visibility": "PUBLIC"
  }
]
```

#### Response Examples

```json
// After liking
{ "success": true, "liked": true }

// After unliking
{ "success": true, "liked": false }
```

> **Note:** The liked object URL is constructed server-side as `{scheme}://{host}/social_distribution/entries/{entry_id}`


### POST `/api/addentry/`

**When to use:** When the authenticated user submits a new post via the new entry form.

**How to use:** POST with `entry_text`, `content_type`, and `visibility`. The `belonging_url` is automatically set from the logged-in user server-side.

**Why to use:** Creates a new post associated with the current user. The author is resolved server side.

**Why NOT to use:** Do not pass a custom `belonging_url` — the server ignores it and always uses the authenticated user's username.

**Auth Required:** Yes

#### Request Fiels


| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `entry_text` | string | `"My first post!"` | The content of the entry. Supports plain text or Markdown. |
| `content_type` | string | `"text/plain"` | MIME type. Use `text/plain` or `text/markdown`. |
| `visibility` | string | `"PUBLIC"` | `PUBLIC` for everyone, `FRIENDS` for mutual followers only. |

#### Response Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| redirect | HTTP 302 | `/social_distribution/` | On success, redirects to the home feed. |
| `errors` | object | `{"entry_text": ["This field is required."]}` | On validation failure, returns serializer errors with HTTP 400. |

#### Request Example


```
POST /social_distribution/api/addentry/
Content-Type: application/x-www-form-urlencoded

entry_text=My+first+post!&content_type=text/plain&visibility=PUBLIC
```


### POST `/editentry/{entry_id}/`

**When to use:** When the author of a post wants to update its text or content type after publishing.

**How to use:** POST with new `entry_text` and/or `content_type`. Only the owner (`belonging_url` matches username) can edit.

**Why to use:** Allows post authors to correct or update content after it has been published.

**Why NOT to use:** Returns 404 if the authenticated user is not the original author of the entry.

**Auth Required:** Yes

#### Request Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `entry_text` | string | `"Updated content"` | The new text content to replace the existing entry text. |
| `content_type` | string | `"text/markdown"` | Updated content type. Must be `text/plain` or `text/markdown`. |

#### Request Example

```
POST /social_distribution/editentry/42/
Content-Type: application/x-www-form-urlencoded

entry_text=Updated+content&content_type=text/markdown
```


## POST `/deleteentry/{entry_id}/`

**When to use:** When the author wants to remove their post from all feeds and detail views.

**How to use:** POST with CSRF token. The entry is soft-deleted (`is_deleted=True`) and hidden from all views. Only the owner can delete.

**Why to use:** Soft deletion preserves data integrity and allows potential recovery, while hiding the post from all views.

**Why NOT to use:** This does not permanaently remove the entry from the database. Do not rely on this for data erasure without extra cleanup.

**Auth Required:** Yes


#### Request Example

```
POST /social_distribution/deleteentry/42/
X-CSRFToken: abc123...
```

#### Response Example

```
HTTP 302 → /social_distribution/
```

## Likes

### POST `/api/likes/add/{entry_id}/`

**When to use:** When a user clicks the Like/Unlike button on an entry's detail page.

**How to use:** POST with CSRF token. If not liked → creates a Like. If already liked → deletes the Like. Returns the new liked state.

**Why to use:** Single endpoint handles both liking and unliking. The frontend only needs to check the returned `liked` boolean to update the UI.

**Why NOT to use:** Do not poll this endpoint to check like status. entry detail view context is better. 

**Auth Required:** Yes

#### Response Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `success` | boolean | `true` | Always `true` if the request was processed correctly. |
| `liked` | boolean | `true` | `true` if the user just liked the entry. `false` if they just unliked it. |

#### Request Example

```
POST /social_distribution/api/likes/add/42/
X-CSRFToken: abc123...
```

#### Response Examples

```json
// After liking
{ "success": true, "liked": true }

// After unliking
{ "success": true, "liked": false }
```




### POST `/api/comments/{comment_id}/likes/`

**When to use:** When a user clicks the Like/Unlike button on a specific comment.

**How to use:** POST with CSRF token. Identical toggle behavior to entry likes.

**Why to use:** Allows users to react to individual comments, not just posts.

**Why NOT to use:** Do not use this for entry likes — use the entry-specific endpoint above.

**Auth Required:** Yes

#### Response Fields

| Field     |Type     | Example  | Description                                     |
|-----------|---------|----------|-------------------------------------------------|
| `success` | boolean | `true`   | `true` if the request was processed successfully. |
| `liked`   | boolean | `true`   | `true` if comment is now liked, `false` if unliked. |

#### Request Example

```
POST /social_distribution/api/comments/7/likes/
X-CSRFToken: abc123...
```

#### Response Example

```json
{ "success": true, "liked": true }
```


## GET `/api/likes/{object_url}/`

**When to use:** Use to retrieve all likes for any likeable object (entry or comment) identified by its full URL.

**How to use:** GET with the full object URL as the path parameter. Example: `/api/likes/http://localhost/social_distribution/entries/42/`

**Why to use:** Provides a standardized likes collection compatible with ActivityPub-style federation.

**Why NOT to use:** The `object_id` must be the full URL — passing just an integer ID will not match any likes.

**Auth Required:** No  
**Paginated:** Yes (currently single page — all results returned at once. `page_number`, `size`, and `count` fields are included for future cursor-based pagination.)

#### Response Fields

| Field     |Type     | Example  | Description                                     |
|-----------|---------|----------|-------------------------------------------------|
| `type`    | string  | `"likes"` | Always `"likes"`. Identifies the response type. |
| `id`      | string  |  `"{object_url}/likes"` | URL identifier for this likes collection. |
| `web`    | string  | `"{object_url}/likes"` | Web-accessible URL for this collection. |
|`page number' | integer  `"{object_url}/likes"` | Web-accessible URL for this collection. |
| `size` | integer | `3` | Number of likes returned in this response. |
| `count` | integer | `3` | Total number of likes for this object. |
| `src` | array | `[...]` | Array of Like objects. |
| `src[].type` | string | `"Like"` | Always `"Like"`. |
| `src[].author` | integer | `1` | Foreign key ID of the Author who liked the object. |
| `src[].published` | datetime | `"2026-03-01T10:00:00Z"` | timestamp of when the like was created. |
| `src[].id` | string | `"john_doe/likes/5"` | Unique identifier for this like record. |
| `src[].object` | string (URL) | `"http://localhost/.../entries/42"` | The full URL of the object that was liked. |


#### Response Example

```json
{
  "type": "likes",
  "id": "http://localhost/social_distribution/entries/42/likes",
  "web": "http://localhost/social_distribution/entries/42/likes",
  "page_number": 1,
  "size": 2,
  "count": 2,
  "src": [
    {
      "type": "Like",
      "author": 1,
      "published": "2026-03-01T10:00:00Z",
      "id": "john_doe/likes/5",
      "object": "http://localhost/social_distribution/entries/42"
    }
  ]
}
```

### POST `/api/likes/`

**When to use:** For liking any object by providing a custom object URL.

**How to use:** POST a JSON body with an `object` field set to the full URL of the object being liked.

**Why to use:** Enables liking objects from remote nodes in a network without requiring a local object ID.



**Why NOT to use:** For local entries, prefer `/api/likes/add/{entry_id}/` which handles toggle logic. This endpoint always creates a new like and does NOT toggle.

**Auth Required:** Yes

#### Request Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `object` | string (URL) | `"https://remote.node/entries/99"` | Full URL of the object being liked. Required. Missing this field returns HTTP 400. |

#### Response Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `type` | string | `"Like"` | Always `"Like"`. |
| `author` | integer | `1` | FK ID of the author who liked the object. |
| `published` | datetime | `"2026-03-01T10:00:00Z"` | Timestamp of when the like was created. |
| `id` | string | `"john_doe/likes/8"` | Unique identifier for this like record. |
| `object` | string (URL) | `"https://remote.node/entries/99"` | The URL of the object that was liked. |

#### Request Example

```
POST /social_distribution/api/likes/
Content-Type: application/json
X-CSRFToken: abc123...

{
  "object": "https://remote.node/entries/99"
}
```

#### Response Example

```json
{
  "type": "Like",
  "author": 1,
  "published": "2026-03-01T10:00:00Z",
  "id": "john_doe/likes/8",
  "object": "https://remote.node/entries/99"
}
```

---

## Comments

### GET `/api/entries/{entry_id}/comments/`

**When to use:** Use to fetch all comments on a specific entry, ordered newest first.

**How to use:** GET with the entry ID in the URL. Returns a JSON object with a comments collection.

**Why to use:** Provides a comment feed compatible with ActivityPub-style collection format.

**Why NOT to use:** This endpoint does not check entry visibility or authentication. Avoid exposing it for `FRIENDS`-only entries without adding an auth check.

**Auth Required:** No  
**Paginated:** Yes (currently single page. `page_number`, `size`, and `count` fields included for future cursor-based pagination.)

#### Response Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `type` | string | `"comments"` | Always `"comments"`. |
| `id` | string | `"/entries/42/comments"` | Relative URL identifier for this comment collection. |
| `web` | string | `"/entries/42/comments"` | Web path for this collection. |
| `page_number` | integer | `1` | Current page. Always `1` in current implementation. |
| `size` | integer | `4` | Number of comments returned. |
| `count` | integer | `4` | Total comment count for this entry. |
| `src` | array | `[...]` | Array of Comment objects. |
| `src[].type` | string | `"comment"` | Always `"comment"`. |
| `src[].author` | object | `{...}` | Nested author object with `displayName` and `url`. |
| `src[].author.displayName` | string | `"John Doe"` | Display name of the comment author. |
| `src[].author.url` | string | `"john_doe"` | Username/URL identifier of the author. |
| `src[].content` | string | `"Great post!"` | The text content of the comment. |
| `src[].content_type` | string | `"text/markdown"` | MIME type of the comment content. |
| `src[].published` | datetime | `"2026-03-01T12:00:00Z"` | ISO 8601 creation timestamp. |
| `src[].id` | string | `"john_doe/commented/3"` | Unique identifier for this comment. |
| `src[].comment_id` | integer | `3` | Numeric DB ID. Use this with the comment like endpoint. |
| `src[].entry` | integer | `42` | ID of the parent entry. |

#### Response Example

```json
{
  "type": "comments",
  "id": "/entries/42/comments",
  "web": "/entries/42/comments",
  "page_number": 1,
  "size": 1,
  "count": 1,
  "src": [
    {
      "type": "comment",
      "author": { "displayName": "John Doe", "url": "john_doe" },
      "content": "Great post!",
      "content_type": "text/markdown",
      "published": "2026-03-01T12:00:00Z",
      "id": "john_doe/commented/3",
      "comment_id": 3,
      "entry": 42
    }
  ]
}
```

---

### POST `/api/entries/{entry_id}/comments/add/`

**When to use:** When an authenticated user submits a comment on an entry from the entry detail page.

**How to use:** POST a JSON body with `comment` (the text) and optionally `contentType`. The author is set automatically from the session.

**Why to use:** Creates a new comment associated with the given entry and the logged-in author.

**Why NOT to use:** Returns 400 if comment is empty or missing. Do not pass an author field — it is set server-side and cannot be overridden.

**Auth Required:** Yes  
**Returns:** HTTP 201 on success

#### Request Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `comment` | string | `"Great post!"` | The text content of the comment. Required. Must not be empty or whitespace only. |
| `contentType` | string | `"text/markdown"` | MIME type. Defaults to `text/markdown` if not provided. |

#### Response Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `type` | string | `"comment"` | Always `"comment"`. |
| `author` | object | `{...}` | Nested author object with `displayName` and `url`. |
| `content` | string | `"Great post!"` | The comment text as submitted. |
| `content_type` | string | `"text/markdown"` | MIME type of the comment. |
| `published` | datetime | `"2026-03-01T12:05:00Z"` | ISO 8601 timestamp of creation. |
| `id` | string | `"john_doe/commented/3"` | Unique identifier for this comment. |
| `comment_id` | integer | `3` | Numeric DB ID. Used with the comment like endpoint. |
| `entry` | integer | `42` | ID of the parent entry. |

#### Request Example

```
POST /social_distribution/api/entries/42/comments/add/
Content-Type: application/json
X-CSRFToken: abc123...

{
  "comment": "Great post!",
  "contentType": "text/markdown"
}
```

#### Response Example

```json
{
  "type": "comment",
  "author": { "displayName": "John Doe", "url": "john_doe" },
  "content": "Great post!",
  "content_type": "text/markdown",
  "published": "2026-03-01T12:05:00Z",
  "id": "john_doe/commented/3",
  "comment_id": 3,
  "entry": 42
}
```

---

## Follow / Social

All follow endpoints are form-based, require authentication, and redirect rather than returning JSON.

> **Friend Definition:** Two users are considered friends when each has an approved follow of the other (mutual follow). This is checked via the `friends()` helper which queries for mutual approved `Follow` records.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/follow/{username}/` | GET | Send a follow request. Creates a Follow with `approved=False`. |
| `/unfollow/{username}/` | GET | Remove the follow relationship to the given user. |
| `/follow_requests/` | GET | View all pending incoming follow requests for the current user. |
| `/approve_follow/{username}/` | GET | Approve a follow request from the given user (sets `approved=True`). |
| `/reject_follow/{username}/` | GET | Reject and delete a pending follow request. |
| `/followers/` | GET | View the list of approved followers for the current user. |
| `/friends/` | GET | View mutual follows (friends = both parties have approved follows of each other). |
| `/authors/` | GET | View all other authors on the node, excluding yourself. |

All of the above require authentication and redirect to a relevant page on success.

---

## Error Reference

| HTTP Code | When | Example Response |
|-----------|------|-----------------|
| `400` | Missing required field | `{ "error": "Missing comment content" }` |
| `400` | Serializer validation failure | `{ "entry_text": ["This field is required."] }` |
| `302` | Successful form submission | Redirects to home or relevant page |
| `403` | Not authenticated | Redirects to `/social_distribution/login` |
| `404` | Object not found or not owned by user | Django 404 page |


