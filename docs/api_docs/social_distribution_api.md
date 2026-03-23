# Social Distribution API Documentation

**Base URL:** `/social_distribution/`  
**Authentication:** Django session cookies. Obtain a session via the login endpoint first. 

## Table of Contents 
- [Authentication](#authentication)
- [Profile](#profile) 
- [Entries — Form UI](#entries--form-ui)
- [Entries — REST API](#entries--rest-api)
- [Image Entries](#image-entries)
- [Comments](#comments)
- [Likes](#likes)
- [Authors REST API](#authors-rest-api)
- [Follow / Social](#follow--social)
- [Error Reference](#error-reference)

---

## Authentication 

### POST `/api/loginregister/`

**When to use:** When a user wants to log in with existing credentials, or create a new account. Both flows are handled by this single endpoint.

**How to use:** POST with form-encoded `username` and `password`. If the user exists and credentials match, the session is established and the user is redirected home. If the user does not exist, a new Django `User` and `Author` record are created (pending admin approval).

**Why to use:** Combines login and registration into one endpoint, reducing round trips.

**Why NOT to use:** Do not use for password changes or account management. New accounts cannot log in until a node admin sets `is_approved=True` in the Django admin panel.

**Auth Required:** No

#### Request Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `username` | string | `"john_doe"` | The unique username. Also used as the `Author` primary key (`url` field). |
| `password` | string | `"hunter2"` | The account password. Stored as a Django hash. |

#### Response Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| redirect | HTTP 302 | `/social_distribution/` | On successful login with an approved account. |
| `message` | string | `"Account created for john_doe. Waiting for admin approval."` | On new registration — renders login page with this message. |
| `message` | string | `"Your account is pending admin approval."` | If the account exists but `is_approved=False`. |
| `message` | string | `"Invalid username or password"` | Wrong password for an existing user. |

#### Request Example
```
POST /social_distribution/api/loginregister/
Content-Type: application/x-www-form-urlencoded

username=john_doe&password=hunter2
```

#### Response Examples
```
// Approved user → HTTP 302 redirect to /social_distribution/

// New registration → renders login.html with message:
"Account created for john_doe. Waiting for admin approval."

// Existing but unapproved → renders login.html with message:
"Your account is pending admin approval."

// Wrong password → renders login.html with message:
"Invalid username or password"
```

---

### POST `/api/signout/`

**When to use:** When the authenticated user wants to log out and invalidate their session.

**How to use:** POST with a valid CSRF token. The server calls Django's `logout()`, clears the session, and redirects to the home page.

**Why to use:** Properly invalidates the server-side session, preventing unauthorized reuse of session cookies.

**Why NOT to use:** Do not call this on behalf of another user. It always signs out the currently authenticated session only.

**Auth Required:** Yes

#### Request Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `X-CSRFToken` | string (header) | `"abc123..."` | Required CSRF token from the session cookie. |

#### Request Example
```
POST /social_distribution/api/signout/
X-CSRFToken: abc123...
```

#### Response
```
HTTP 302 → /social_distribution/
```

---

## Profile

### POST `/api/editprofile/`

**When to use:** When the authenticated user wants to update their display name, bio, profile picture URL, or GitHub handle.

**How to use:** POST with form-encoded fields. Only `name` is required; the other fields are optional and will only be updated if a non-empty value is provided.

**Why to use:** Allows users to personalize their public profile as seen by other users on the platform.

**Why NOT to use:** Does not change username or password. Will re-render the form with an error if `name` is missing. Setting `github` here enables automatic GitHub activity import when the profile page is visited.

**Auth Required:** Yes

#### Request Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `name` | string | `"John Doe"` | Display name shown on posts and the profile page. **Required.** |
| `description` | string | `"I love almonds!"` | Short bio displayed on the public profile. Optional — ignored if blank. |
| `picture` | string (URL) | `"https://example.com/pic.jpg"` | URL to the user's profile picture. Optional — ignored if blank. |
| `github` | string (URL) | `"https://github.com/johndoe"` | GitHub profile URL. Used to fetch public GitHub activity as entries. Optional - ignored if blank. |

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| redirect | HTTP 302 | On success, redirects to `/social_distribution/`. |
| `message` | string | On validation failure, re-renders `changeprofile.html` with `"Form requirements failed, change failed."` |

#### Request Example
```
POST /social_distribution/api/editprofile/
Content-Type: application/x-www-form-urlencoded

name=John+Doe&description=I+love+almonds&picture=https://example.com/pic.jpg&github=https://github.com/johndoe
```

---

## Entries — Form UI

These endpoints are used by the browser form UI. They accept `multipart/form-data` or `application/x-www-form-urlencoded` and return redirects rather than JSON.

---

### POST `/api/addentry/`

**When to use:** When the authenticated user submits the New Entry form in the browser.

**How to use:** POST with `entry_text`, `content_type`, `visibility`, and optionally an `image` file upload. The `belonging_url` is always set server-side from the logged-in user.

**Why to use:** Creates a new post for the current user. Supports plain text, Markdown, and image uploads.

**Why NOT to use:** Do not pass a custom `belonging_url` — it is ignored and always set from the session. For programmatic creation by API clients, use `POST /api/authors/{username}/entries/` instead.

**Auth Required:** Yes

#### Request Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `entry_text` | string | `"My first post!"` | The text content of the entry. Can be empty if an image is provided. |
| `content_type` | string | `"text/plain"` | MIME type. One of: `text/plain`, `text/markdown`, `image/png`, `image/jpeg`, `image/gif`. |
| `visibility` | string | `"PUBLIC"` | One of: `PUBLIC`, `FRIENDS`, `UNLISTED`. Defaults to `PUBLIC`. |
| `image` | file | *(multipart)* | Optional image upload. Stored server-side under `/media/entries/`. |

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| redirect | HTTP 302 | On success, redirects to `/social_distribution/`. |
| `errors` | object | On serializer validation failure, returns field-level errors with HTTP 400. |

#### Request Example
```
POST /social_distribution/api/addentry/
Content-Type: multipart/form-data

entry_text=My+first+post!&content_type=text%2Fplain&visibility=PUBLIC
```

---

## Entries — REST API

These endpoints accept and return JSON and are suitable for API clients (other nodes, a future Android app, etc.).

---

### GET `/api/entries/`

**When to use:** Use to retrieve all non-deleted entries on the node regardless of author. Useful for admin views or feed aggregation.

**How to use:** Send a GET request. No authentication or parameters required. Returns a flat JSON array of entry objects.

**Why to use:** Provides a public feed of all content on the node, enabling other nodes or public clients to read posts.

**Why NOT to use:** Returns ALL entries without visibility filtering. Do not use to render a personal feed instead use the filtered index view.

**Auth Required:** No  
**Paginated:** No

#### Response Fields (per entry object)

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `type` | string | `"entry"` | Always `"entry"`. |
| `id` | string (URL) | `"http://node/social_distribution/api/authors/john_doe/entries/42"` | Fully qualified URL identifier for this entry. |
| `belonging_url` | string | `"john_doe"` | Username (serial) of the author who owns this entry. |
| `entry_text` | string | `"Hello world!"` | The raw text content of the entry. |
| `pub_date` | datetime | `"2026-03-01T12:00:00Z"` | ISO 8601 timestamp of when the entry was published. |
| `content_type` | string | `"text/plain"` | MIME type. One of: `text/plain`, `text/markdown`, `image/png`, `image/jpeg`, `image/gif`. |
| `visibility` | string | `"PUBLIC"` | Visibility level: `PUBLIC`, `FRIENDS`, or `UNLISTED`. |
| `image` | string or null | `"/media/entries/photo.jpg"` | Server-relative URL of the uploaded image file, or `null` if no image. |

#### Response Example
```json
[
  {
    "type": "entry",
    "id": "http://localhost/social_distribution/api/authors/john_doe/entries/42",
    "belonging_url": "john_doe",
    "entry_text": "Hello world!",
    "pub_date": "2026-03-01T12:00:00Z",
    "content_type": "text/plain",
    "visibility": "PUBLIC",
    "image": null
  }
]
```

---

### GET `/api/entries/{entry_id}/`

**When to use:** Retrieve a single entry by its numeric database ID, with visibility enforcement.

**How to use:** GET with the entry's integer ID. Public and unlisted entries are accessible to anyone. Friends-only entries require the requester to be authenticated and a friend of the entry's author.

**Why to use:** Lets API clients fetch a single entry without knowing the author's username.

**Why NOT to use:** Returns 404 for deleted entries. Returns 403 for friends-only entries if the requester does not meet the access criteria.

**Auth Required:** No for PUBLIC/UNLISTED; Yes (+ friendship) for FRIENDS.

#### Response Fields

Same fields as listed in `GET /api/entries/` above.

#### Request Example
```
GET /social_distribution/api/entries/42/
```

#### Response Example
```json
{
  "type": "entry",
  "id": "http://localhost/social_distribution/api/authors/john_doe/entries/42",
  "belonging_url": "john_doe",
  "entry_text": "Hello world!",
  "pub_date": "2026-03-01T12:00:00Z",
  "content_type": "text/plain",
  "visibility": "PUBLIC",
  "image": null
}
```

---

### PUT `/api/entries/{entry_id}/`

**When to use:** When the entry's author wants to update its text, content type, or visibility.

**How to use:** PUT a JSON body with `entry_text` (required), and optionally `content_type` and `visibility`. Must be authenticated as the entry's owner.

**Why to use:** Allows authors to correct or update published entries without deleting and re-creating them.

**Why NOT to use:** Returns 403 if not authenticated or not the owner. Returns 400 if `entry_text` is empty. Does not update `belonging_url`, `pub_date`, or `image`.

**Auth Required:** Yes (must be the entry owner)

#### Request Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `entry_text` | string | `"Updated content"` | The new text content. **Required.** Cannot be empty. |
| `content_type` | string | `"text/markdown"` | Updated content type. One of: `text/plain`, `text/markdown`. Ignored if not one of these values. |
| `visibility` | string | `"FRIENDS"` | Updated visibility. One of: `PUBLIC`, `FRIENDS`, `UNLISTED`. Ignored if not one of these values. |

#### Response Fields

On success (HTTP 200), returns the updated entry object (same fields as `GET /api/entries/{entry_id}/`).

| Field | Type | Description |
|-------|------|-------------|
| `error` | string | On failure, a description of what went wrong. |

#### Request Example
```
PUT /social_distribution/api/entries/42/
Content-Type: application/json
X-CSRFToken: abc123...

{
  "entry_text": "Updated content",
  "content_type": "text/markdown",
  "visibility": "PUBLIC"
}
```

#### Response Examples
```json
// Success HTTP 200
{
  "type": "entry",
  "id": "http://localhost/social_distribution/api/authors/john_doe/entries/42",
  "belonging_url": "john_doe",
  "entry_text": "Updated content",
  "pub_date": "2026-03-01T12:00:00Z",
  "content_type": "text/markdown",
  "visibility": "PUBLIC",
  "image": null
}

// Not the owner → HTTP 403
{ "error": "You do not own this entry." }

// Empty entry_text → HTTP 400
{ "error": "entry_text is required and cannot be empty." }
```

---

### DELETE `/api/entries/{entry_id}/`

**When to use:** When the entry's author wants to remove their post from all feeds and detail views.

**How to use:** DELETE with CSRF token. The entry is soft-deleted (`is_deleted=True`) and hidden from all views and API responses. Must be authenticated as the owner.

**Why to use:** Soft deletion preserves data integrity in the database while hiding the entry everywhere in the UI and API.

**Why NOT to use:** Does not permanently remove the entry from the database. Do not rely on this for data erasure, only node admins can see deleted entries. Returns 404 if the entry is already deleted.

**Auth Required:** Yes (must be the entry owner)

#### Request Example
```
DELETE /social_distribution/api/entries/42/
X-CSRFToken: abc123...
```

#### Response Examples
```json
// Success HTTP 200
{ "success": true, "message": "Entry deleted." }

// Not the owner → HTTP 403
{ "error": "You do not own this entry." }

// Not found or already deleted → HTTP 404
```

---

### GET `/api/authors/{username}/entries/`

**When to use:** Retrieve a list of entries belonging to a specific author, with access rules based on the requester's relationship to that author.

**How to use:** GET with the author's username in the URL. What is returned depends on who is asking:
- **Unauthenticated:** public entries only.
- **Authenticated as the author:** all entries (public, unlisted, friends-only).
- **Authenticated as a follower of the author:** public and unlisted entries.
- **Authenticated as a friend of the author:** all entries.
- **Authenticated but neither follower nor friend:** public entries only.

**Why to use:** The primary endpoint for reading another author's posts with proper visibility enforcement.

**Why NOT to use:** Does not support remote node access, authentication is local session only.

**Auth Required:** No (for public entries); Yes (for unlisted/friends-only)
**Paginated:** No (returns all matching entries ordered by `-pub_date`)

#### Response Fields

Returns a flat JSON array of entry objects. Same fields as `GET /api/entries/`.

#### Request Example
```
GET /social_distribution/api/authors/john_doe/entries/
```

#### Response Example
```json
[
  {
    "type": "entry",
    "id": "http://localhost/social_distribution/api/authors/john_doe/entries/42",
    "belonging_url": "john_doe",
    "entry_text": "Hello world!",
    "pub_date": "2026-03-01T12:00:00Z",
    "content_type": "text/plain",
    "visibility": "PUBLIC",
    "image": null
  }
]
```

---

### POST `/api/authors/{username}/entries/`

**When to use:** Programmatically create a new entry for the authenticated user via the API.

**How to use:** POST a JSON body. Must be authenticated as `{username}`.

**Why to use:** Allows API clients (not just the browser form) to create entries.

**Why NOT to use:** Returns 403 if not authenticated or if the authenticated user is not `{username}`. Delegates to `addentry` internally, so the same field rules apply.

**Auth Required:** Yes (must be authenticated as `{username}`)

#### Request Fields

Same as `POST /api/addentry/`.

#### Response

Returns HTTP 200 with `"Added entry."` on success, or the same error codes as `addentry`.

---

### GET `/api/authors/{username}/entries/{entry_id}`

**When to use:** Retrieve a single entry belonging to a specific author by both username and entry ID.

**How to use:** GET. Access rules are the same as for the `/api/entries/{entry_id}/` endpoint — friends-only entries require authentication and friendship.

**Why to use:** Useful when you already know both the author username and the entry ID (e.g. from a stored FQID).

**Why NOT to use:** Returns 404 if the entry does not belong to `{username}` or is deleted.

**Auth Required:** No for PUBLIC/UNLISTED; Yes (+ friendship) for FRIENDS.

#### Request Example
```
GET /social_distribution/api/authors/john_doe/entries/42
```

#### Response Example
```json
{
  "type": "entry",
  "id": "http://localhost/social_distribution/api/authors/john_doe/entries/42",
  "belonging_url": "john_doe",
  "entry_text": "Hello world!",
  "pub_date": "2026-03-01T12:00:00Z",
  "content_type": "text/plain",
  "visibility": "PUBLIC",
  "image": null
}
```

---

### PUT `/api/authors/{username}/entries/{entry_id}`

**When to use:** Update a specific entry, identified by both author username and entry ID.

**How to use:** PUT a JSON body. Must be authenticated as `{username}`.

**Why to use:** Alternative to `PUT /api/entries/{entry_id}/` when you have the author-scoped URL.

**Auth Required:** Yes (must be authenticated as `{username}`)

#### Request / Response

Same fields and behavior as `PUT /api/entries/{entry_id}/`.

---

### DELETE `/api/authors/{username}/entries/{entry_id}`

**When to use:** Soft-delete a specific entry, identified by both author username and entry ID.

**How to use:** DELETE. Must be authenticated as `{username}`.

**Why to use:** Alternative to `DELETE /api/entries/{entry_id}/` when you have the author-scoped URL.

**Auth Required:** Yes (must be authenticated as `{username}`)

#### Request / Response

Same behavior as `DELETE /api/entries/{entry_id}/`.

---

### GET `/api/entries/{entry_id}` *(no trailing slash)*

**When to use:** Retrieve a single entry by numeric ID without the author scope. Useful when you have a stored entry FQID and need to look it up.

**How to use:** GET. Access rules are the same as `/api/entries/{entry_id}/` — public and unlisted are open; friends-only requires authentication and friendship.

**Auth Required:** No for PUBLIC/UNLISTED; Yes (+ friendship) for FRIENDS.

#### Request Example
```
GET /social_distribution/api/entries/42
```

---

## Image Entries

### GET `/api/authors/{username}/entries/{entry_id}/image`

**When to use:** Retrieve the raw binary image from an entry that has an uploaded image file.

**How to use:** GET. Returns the image bytes directly with the entry's `content_type` as the `Content-Type` header. This allows the URL to be used directly in an HTML `<img>` tag or Markdown image link.

**Why to use:** Decouples image delivery from entry metadata. Lets CommonMark entries reference images stored on this node using a stable URL.

**Why NOT to use:** Returns 404 if the entry exists but has no uploaded image (`image` field is null). Friends-only image entries require authentication and friendship.

**Auth Required:** No for PUBLIC/UNLISTED image entries; Yes (+ friendship) for FRIENDS.

#### Response

Raw binary image data. `Content-Type` is set to the entry's `content_type` field (e.g. `image/png`, `image/jpeg`).

#### Response Error Examples
```json
// No image on this entry → HTTP 404
{ "error": "This entry does not have an image." }

// Friends-only, not authenticated → HTTP 403
{ "error": "Authentication required." }

// Friends-only, not a friend → HTTP 403
{ "error": "You are not friends with this author." }
```

#### Request Example
```
GET /social_distribution/api/authors/john_doe/entries/17/image
```

---

## Comments

### GET `/api/entries/{entry_id}/comments/`

**When to use:** Fetch all comments on a specific entry, ordered newest first.

**How to use:** GET with the entry's integer ID. Returns a `comments` collection object. Friends-only entries require authentication and friendship to access comments.

**Why to use:** Provides a structured comment feed compatible with the ActivityPub-style collection format used in this project.

**Why NOT to use:** Currently returns all comments in a single page (no true pagination — `page_number` is always 1). For friends-only entries, unauthenticated requests receive a 403.

**Auth Required:** No for PUBLIC/UNLISTED; Yes (+ friendship) for FRIENDS.
**Paginated:** No (all comments returned at once; pagination fields included for future use)

#### Response Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `type` | string | `"comments"` | Always `"comments"`. |
| `id` | string | `"/entries/42/comments"` | Relative path identifier for this comments collection. |
| `web` | string | `"/entries/42/comments"` | Same as `id` in current implementation. |
| `page_number` | integer | `1` | Current page number. Always `1` in current implementation. |
| `size` | integer | `4` | Number of comments returned in this response. |
| `count` | integer | `4` | Total number of comments for this entry. Equals `size` in current implementation. |
| `src` | array | `[...]` | Array of comment objects. |
| `src[].type` | string | `"comment"` | Always `"comment"`. |
| `src[].author` | object | `{...}` | Nested author object. |
| `src[].author.type` | string | `"author"` | Always `"author"`. |
| `src[].author.id` | string (URL) | `"http://node/social_distribution/api/authors/john_doe"` | Fully qualified author ID. |
| `src[].author.displayName` | string | `"John Doe"` | Display name of the comment author. |
| `src[].author.url` | string | `"john_doe"` | Username (serial) of the comment author. |
| `src[].author.host` | string | `"http://node/social_distribution/api/"` | Host API prefix of the comment author's node. |
| `src[].content` | string | `"Great post!"` | The text content of the comment. |
| `src[].content_type` | string | `"text/markdown"` | MIME type of the comment. |
| `src[].published` | datetime | `"2026-03-01T12:00:00Z"` | ISO 8601 timestamp of when the comment was created. |
| `src[].id` | string | `"http://node/social_distribution/api/authors/john_doe/commented/3"` | Fully qualified identifier for this comment. |
| `src[].comment_id` | integer | `3` | Numeric database ID of the comment. Use this with the comment like endpoint. |
| `src[].entry` | integer | `42` | Database ID of the parent entry. |

#### Request Example
```
GET /social_distribution/api/entries/42/comments/
```

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
      "author": {
        "type": "author",
        "id": "http://localhost/social_distribution/api/authors/john_doe",
        "displayName": "John Doe",
        "url": "john_doe",
        "host": "http://localhost/social_distribution/api/"
      },
      "content": "Great post!",
      "content_type": "text/markdown",
      "published": "2026-03-01T12:00:00Z",
      "id": "http://localhost/social_distribution/api/authors/john_doe/commented/3",
      "comment_id": 3,
      "entry": 42
    }
  ]
}
```

---

### POST `/api/entries/{entry_id}/comments/add/`

**When to use:** When an authenticated user submits a comment on an entry from the entry detail page.

**How to use:** POST a JSON body with `comment` (the text content) and optionally `contentType`. The author is resolved from the session.

**Why to use:** Creates a new comment linked to the given entry and the logged-in author. Returns the full comment object on success (HTTP 201).

**Why NOT to use:** Returns 400 if `comment` is empty or whitespace only. Returns 403 if the entry is friends-only and the requester is not a friend. Do not pass an `author` field — it is always set server-side.

**Auth Required:** Yes
**Returns:** HTTP 201 on success.

#### Request Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `comment` | string | `"Great post!"` | The text content of the comment. **Required.** Must not be empty or whitespace only. |
| `contentType` | string | `"text/markdown"` | MIME type of the comment. Defaults to `text/markdown` if not provided. |

#### Response Fields

On success (HTTP 201), returns a comment object with the same fields as those listed in `src[]` under the GET comments endpoint above.

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
  "author": {
    "type": "author",
    "id": "http://localhost/social_distribution/api/authors/john_doe",
    "displayName": "John Doe",
    "url": "john_doe",
    "host": "http://localhost/social_distribution/api/"
  },
  "content": "Great post!",
  "content_type": "text/markdown",
  "published": "2026-03-01T12:05:00Z",
  "id": "http://localhost/social_distribution/api/authors/john_doe/commented/3",
  "comment_id": 3,
  "entry": 42
}
```

---

## Likes

### POST `/api/likes/add/{entry_id}/`

**When to use:** When a user clicks the Like/Unlike button on an entry's detail page.

**How to use:** POST with CSRF token. If not liked → creates a Like. If already liked → deletes the Like. Returns the new liked state.

**Why to use:** Single endpoint handles both liking and unliking. The frontend only needs to check the returned `liked` boolean to update the UI.

**Why NOT to use:** Do not poll this endpoint to check like status. Entry detail view context is better. 

**Auth Required:** Yes

#### Response Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `success` | boolean | `true` | Always `true` if the request was processed correctly. |
| `liked` | boolean | `true` | `true` if the user just liked the entry; `false` if they just unliked it. |

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

---

### POST `/api/comments/{comment_id}/likes/`

**When to use:** When a user clicks the Like/Unlike button on a specific comment.

**How to use:** POST with a valid CSRF token. Toggle behavior is identical to entry likes. The liked object URL is `{scheme}://{host}/social_distribution/comments/{comment_id}`.

**Why to use:** Allows users to react to individual comments, not just posts.

**Why NOT to use:** Do not use this for entry likes — use `POST /api/likes/add/{entry_id}/` instead.

**Auth Required:** Yes

#### Response Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `success` | boolean | `true` | `true` if the request was processed successfully. |
| `liked` | boolean | `true` | `true` if the comment is now liked; `false` if unliked. |

#### Request Example
```
POST /social_distribution/api/comments/7/likes/
X-CSRFToken: abc123...
```

#### Response Example
```json
{ "success": true, "liked": true }
```

---

### POST `/api/likes/`

**When to use:** For liking any object by providing a fully qualified object URL. Intended for federation use cases where the liked object may live on a remote node.

**How to use:** POST a JSON body with an `object` field set to the full URL of the object being liked.

**Why to use:** Enables liking objects from remote nodes without requiring a local numeric entry ID.

**Why NOT to use:** For local entries, prefer `POST /api/likes/add/{entry_id}/`, which handles the toggle. This endpoint **always creates a new like** and does NOT toggle — calling it twice will create two Like records.

**Auth Required:** Yes

#### Request Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `object` | string (URL) | `"https://remote.node/social_distribution/entries/99"` | Full URL of the object being liked. **Required.** Returns HTTP 400 if missing. |

#### Response Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `type` | string | `"Like"` | Always `"Like"`. |
| `author` | integer | `1` | Foreign key ID of the Author who liked the object. |
| `published` | datetime | `"2026-03-01T10:00:00Z"` | ISO 8601 timestamp of when the like was created. |
| `id` | string | `"http://node/social_distribution/api/authors/john_doe/liked/8"` | Fully qualified identifier for this like. |
| `object` | string (URL) | `"https://remote.node/social_distribution/entries/99"` | The URL of the object that was liked. |

#### Request Example
```
POST /social_distribution/api/likes/
Content-Type: application/json
X-CSRFToken: abc123...

{
  "object": "https://remote.node/social_distribution/entries/99"
}
```

#### Response Example
```json
{
  "type": "Like",
  "author": 1,
  "published": "2026-03-01T10:00:00Z",
  "id": "http://localhost/social_distribution/api/authors/john_doe/liked/8",
  "object": "https://remote.node/social_distribution/entries/99"
}
```

---

### GET `/api/likes/{object_url}/`

**When to use:** Retrieve all likes for any object (entry or comment) identified by its full URL.

**How to use:** GET with the full object URL as the path parameter. Example: `GET /social_distribution/api/likes/http://localhost/social_distribution/entries/42/`

**Why to use:** Provides a standardized likes collection for any object regardless of type, compatible with ActivityPub-style federation.

**Why NOT to use:** The `object_url` must be the exact full URL stored in the database — passing just an integer ID will not match anything. This uses a `<path:object_id>` route so the full URL is captured as-is.

**Auth Required:** No
**Paginated:** No (all likes returned at once; pagination fields included for future use)

#### Response Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `type` | string | `"likes"` | Always `"likes"`. |
| `id` | string | `"{object_url}/likes"` | Constructed URL identifier for this likes collection. |
| `web` | string | `"{object_url}/likes"` | Same as `id` in current implementation. |
| `page_number` | integer | `1` | Current page. Always `1` in current implementation. |
| `size` | integer | `2` | Number of likes returned in this response. |
| `count` | integer | `2` | Total number of likes for this object. Equals `size` in current implementation. |
| `src` | array | `[...]` | Array of Like objects. |
| `src[].type` | string | `"Like"` | Always `"Like"`. |
| `src[].author` | integer | `1` | Foreign key ID of the Author who liked the object. |
| `src[].published` | datetime | `"2026-03-01T10:00:00Z"` | ISO 8601 timestamp of when the like was created. |
| `src[].id` | string | `"http://node/social_distribution/api/authors/john_doe/liked/5"` | Fully qualified identifier for this like. |
| `src[].object` | string (URL) | `"http://localhost/social_distribution/entries/42"` | The full URL of the object that was liked. |

#### Request Example
```
GET /social_distribution/api/likes/http://localhost/social_distribution/entries/42/
```

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
      "id": "http://localhost/social_distribution/api/authors/john_doe/liked/5",
      "object": "http://localhost/social_distribution/entries/42"
    }
  ]
}
```

---

## Authors REST API

### GET `/api/authors/`

**When to use:** Retrieve a paginated list of all Author profiles on this node.

**How to use:** GET with optional `page` and `size` query parameters. Defaults to page 1, size 10. Authors are ordered by `url` (username).

**Why to use:** Lets clients discover all authors on the node, compatible with the ActivityPub-style authors collection format.

**Auth Required:** No
**Paginated:** Yes — use `?page={n}&size={n}` query parameters.

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | integer | `1` | Page number (1-based). |
| `size` | integer | `10` | Number of authors per page. |

#### Response Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `type` | string | `"authors"` | Always `"authors"`. |
| `page_number` | integer | `1` | Current page number. |
| `size` | integer | `10` | Page size requested. |
| `count` | integer | `42` | Total number of authors on this node. |
| `authors` | array | `[...]` | Array of Author objects for this page. |
| `authors[].type` | string | `"author"` | Always `"author"`. |
| `authors[].id` | string (URL) | `"http://node/social_distribution/api/authors/john_doe"` | Fully qualified author ID (FQID). |
| `authors[].host` | string | `"http://node/social_distribution/api/"` | Host API prefix for this author's node. |
| `authors[].displayName` | string | `"John Doe"` | The author's display name. |
| `authors[].github` | string | `"http://github.com/johndoe"` | The author's GitHub profile URL. |
| `authors[].profileImage` | string | `"https://example.com/pic.jpg"` | URL of the author's profile picture. |
| `authors[].web` | string | `"http://node/social_distribution/profiles/john_doe"` | URL of the author's HTML profile page. |
| `authors[].url` | string | `"john_doe"` | The author's username / serial. |

#### Request Example
```
GET /social_distribution/api/authors/?page=1&size=5
```

#### Response Example
```json
{
  "type": "authors",
  "page_number": 1,
  "size": 5,
  "count": 12,
  "authors": [
    {
      "type": "author",
      "id": "http://localhost/social_distribution/api/authors/john_doe",
      "host": "http://localhost/social_distribution/api/",
      "displayName": "John Doe",
      "github": "http://github.com/johndoe",
      "profileImage": "https://example.com/pic.jpg",
      "web": "http://localhost/social_distribution/profiles/john_doe",
      "url": "john_doe"
    }
  ]
}
```

---
### GET `/api/authors/{uuid}/`

**When to use:** Retrieve detailed information about a specific author by their id.

**How to use**: GET with the author's uuid. Returns information about the author.

**Auth Required:** No
**Paginated:** No

#### Response Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `type`| string | `"authors"` | Always `"authors"`. |
| `id` | string | `"https://blanchedalmond-node1-0f1bf9c33bf8.herokuapp.com/social_distribution/api/authors/410baaaf-6974-4a09-a708-34eb4396e813"` | Author uuid. |
| `host` | string | `"https://blanchedalmond-node1-0f1bf9c33bf8.herokuapp.com/social_distribution/api/"` | API url of the node. |
| `displayName` | string | `"testuser#2"` | The author's username. |
| `github` | string | `""` | Github profile link (can be empty). |
| `profileImage` | string | `""` | profile image url (can be empty). |
| `web` | string | `"https://blanchedalmond-node1-0f1bf9c33bf8.herokuapp.com/social_distribution/authors/testuser#2"` | Link to the author's profile page. |

#### Request Example
```
GET /social_distribution/api/authors/410baaaf-6974-4a09-a708-34eb4396e813/
```

####Respone Example
```json
{
    "type": "author",
    "id": "https://blanchedalmond-node1-0f1bf9c33bf8.herokuapp.com/social_distribution/api/authors/410baaaf-6974-4a09-a708-34eb4396e813",
    "host": "https://blanchedalmond-node1-0f1bf9c33bf8.herokuapp.com/social_distribution/api/",
    "displayName": "testuser#2",
    "github": "",
    "profileImage": "",
    "web": "https://blanchedalmond-node1-0f1bf9c33bf8.herokuapp.com/social_distribution/authors/testuser#2"
}

```
### GET `/api/authors/{username}/followers/`

**When to use:** Retrieve the list of authors who are approved followers of `{username}`.

**How to use:** GET with the author's username. Returns a `followers` collection.

**Auth Required:** No
**Paginated:** No

#### Response Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `type` | string | `"followers"` | Always `"followers"`. |
| `followers` | array | `[...]` | Array of Author objects (same structure as `authors[]` in `/api/authors/`). |

#### Request Example
```
GET /social_distribution/api/authors/john_doe/followers/
```

#### Response Example
```json
{
  "type": "followers",
  "followers": [
    {
      "type": "author",
      "id": "http://localhost/social_distribution/api/authors/jane_doe",
      "host": "http://localhost/social_distribution/api/",
      "displayName": "Jane Doe",
      "github": "",
      "profileImage": "",
      "web": "http://localhost/social_distribution/profiles/jane_doe",
      "url": "jane_doe"
    }
  ]
}
```

---

### GET `/api/authors/{username}/following/`

**When to use:** Retrieve the list of authors that `{username}` is currently following (approved follows only).

**How to use:** GET with the author's username. Returns a `following` collection.

**Auth Required:** No
**Paginated:** No

#### Response Fields

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `type` | string | `"following"` | Always `"following"`. |
| `following` | array | `[...]` | Array of Author objects (same structure as `authors[]` in `/api/authors/`). |

#### Request Example
```
GET /social_distribution/api/authors/john_doe/following/
```

#### Response Example
```json
{
  "type": "following",
  "following": [
    {
      "type": "author",
      "id": "http://localhost/social_distribution/api/authors/steph",
      "host": "http://localhost/social_distribution/api/",
      "displayName": "Steph",
      "github": "",
      "profileImage": "",
      "web": "http://localhost/social_distribution/profiles/steph",
      "url": "steph"
    }
  ]
}
```

---

## Follow / Social

All follow endpoints are form-based browser endpoints, require authentication, and redirect on success rather than returning JSON.

> **Friend Definition:** Two users are considered friends when each has an approved follow of the other (mutual follow). This is checked via the `friends()` helper which queries for mutual approved `Follow` records.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `POST /follow/{username}/` | POST | Send a follow request to `{username}`. Creates a `Follow` record with `approved=False`. No-ops if a follow already exists (uses `get_or_create`). |
| `POST /unfollow/{username}/` | POST | Remove the follow relationship from the current user to `{username}`. Deletes any matching `Follow` record regardless of `approved` state. |
| `GET /follow_requests/` | GET | View all pending incoming follow requests for the current user (where `approved=False`). |
| `POST /approve_follow/{username}/` | POST | Approve a follow request from `{username}` (sets `approved=True` on the matching `Follow`). |
| `POST /reject_follow/{username}/` | POST | Reject and delete a pending follow request from `{username}`. |
| `GET /followers/` | GET | View the list of approved followers for the current user. |
| `GET /following/` | GET | View the list of authors the current user is following (approved follows). |
| `GET /friends/` | GET | View mutual follows (authors where each party has an approved follow of the other). |
| `GET /authors/` | GET | View all other authors registered on this node, excluding yourself. |
| `GET /nodes/` | GET | View all nodes known to this server. |

All of the above require authentication and redirect to a relevant page on success. The follow/unfollow endpoints only accept `POST` — a `GET` to `/follow/{username}/` will redirect to the target author's profile page without creating a follow.

---

## Error Reference

| HTTP Code | When | Example Response |
|-----------|------|-----------------|
| `200` | Successful soft-delete | `{ "success": true, "message": "Entry deleted." }` |
| `201` | Comment successfully created | Comment object |
| `302` | Successful form submission or auth action | Redirect to home or relevant page |
| `400` | Missing required field | `{ "error": "Missing comment content" }` |
| `400` | Serializer validation failure | `{ "entry_text": ["This field is required."] }` |
| `400` | Author not found on entries list | `"Target author does not exist"` |
| `403` | Not authenticated (on protected endpoint) | `{ "error": "Authentication required." }` |
| `403` | Authenticated but not the entry owner | `{ "error": "You do not own this entry." }` |
| `403` | Friends-only content, requester is not a friend | `{ "error": "You are not friends with this author." }` |
| `404` | Entry not found, already deleted, or wrong author | Django 404 page or `{ "error": "Entry does not exist." }` |
| `404` | Image entry has no image file | `{ "error": "This entry does not have an image." }` |
