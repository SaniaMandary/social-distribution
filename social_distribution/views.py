from django.http import HttpResponse

# Later on, the index function will be used to handle incoming requests to polls/ and it will return the hello world string shown below.
def index(request):
    return HttpResponse("Hello, world. You're at the index page.")