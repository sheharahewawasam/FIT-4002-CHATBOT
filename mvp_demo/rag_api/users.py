from django.http import JsonResponse
from rest_framework.decorators import api_view
    
userList = {"John" : ["Sample Superannuation Fund", "Summers Family Super Fund", "General"],
            "Emily" : ["Ausis Super Fund", "General"],
            "Jake" : ["Triple A Super", "General"],
            "Shrek" : ["General"]
            }

@api_view(['GET'])
def get_users(request):
    users = list(userList.keys())
    return JsonResponse({"users": users})

@api_view(['GET'])
def get_funds(request, name):
    data = userList.get(name)

    if data is None:
        return JsonResponse({"error": "User not found"}, status=404)

    return JsonResponse({"data": data})