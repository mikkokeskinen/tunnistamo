import logging
from collections import defaultdict
from urllib.parse import urlparse

import jwt
import datetime

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import Http404
from rest_framework import permissions, serializers, generics, mixins, views
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from rest_framework.decorators import permission_classes, authentication_classes, api_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, NotFound
from oauth2_provider.contrib.rest_framework import TokenHasReadWriteScope
from oauth2_provider.models import get_application_model
from hkijwt.models import AppToAppPermission
from users.models import Profile

logger = logging.getLogger(__name__)


class UserSerializer(serializers.ModelSerializer):
    ad_groups = serializers.SerializerMethodField()

    def get_ad_groups(self, obj):
        return [x.display_name for x in obj.ad_groups.order_by('display_name')]

    def to_representation(self, obj):
        ret = super(UserSerializer, self).to_representation(obj)
        if obj.first_name and obj.last_name:
            ret['display_name'] = '%s %s' % (obj.first_name, obj.last_name)
        request = self.context.get('request', None)
        if request:
            app = getattr(request.auth, 'application', None)
            if app and not app.include_ad_groups and 'ad_groups' in ret:
                del ret['ad_groups']
        return ret

    class Meta:
        fields = [
            'last_login', 'username', 'email', 'date_joined',
            'first_name', 'last_name', 'uuid', 'department_name',
            'ad_groups'
        ]
        model = get_user_model()


# ViewSets define the view behavior.
class UserView(generics.RetrieveAPIView,
               mixins.RetrieveModelMixin):
    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return self.queryset
        else:
            return self.queryset.filter(pk=user.pk)

    def get_object(self):
        username = self.kwargs.get('username', None)
        if username:
            qs = self.get_queryset()
            obj = generics.get_object_or_404(qs, username=username)
        else:
            obj = self.request.user
        return obj

    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    queryset = get_user_model().objects.all()
    serializer_class = UserSerializer


class GetJWTView(views.APIView):
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]

    def get(self, request, format=None):
        requester_app = request.auth.application
        target_app = request.query_params.get('target_app', '').strip()
        if target_app:
            qs = get_application_model().objects.all()
            target_app = generics.get_object_or_404(qs, client_id=target_app)
            try:
                perm = AppToAppPermission.objects.get(requester=requester_app,
                                                      target=target_app)
            except AppToAppPermission.DoesNotExist:
                raise PermissionDenied("no permissions for app %s" % target_app)
        else:
            target_app = requester_app

        secret = target_app.client_secret
        user = request.user

        payload = UserSerializer(user).data
        delete_fields = ['last_login', 'date_joined', 'uuid']
        for field in delete_fields:
            if field in payload:
                del payload[field]
        if not target_app.include_ad_groups:
            del payload['ad_groups']

        payload['iss'] = 'https://api.hel.fi/sso'  # FIXME: Make configurable
        payload['sub'] = str(user.uuid)
        payload['aud'] = target_app.client_id
        payload['exp'] = request.auth.expires
        encoded = jwt.encode(payload, secret, algorithm='HS256')

        ret = dict(token=encoded, expires_at=request.auth.expires)
        return Response(ret)


@api_view(['GET', 'POST'])
@authentication_classes((SessionAuthentication, BasicAuthentication))
@permission_classes((IsAuthenticated,))
def interested(request):
    if request.method == 'POST':
        divisions = request.POST.getlist('divisions', [])
        yso_strings = request.POST.getlist('yso', [])
    else:
        division_param = request.query_params.get('division', '').strip()
        yso_param = request.query_params.get('yso', '').strip()

        divisions = [i.strip() for i in division_param.split(',')] if division_param else None
        yso_strings = [i.strip() for i in yso_param.split(',')] if yso_param else []

    ysos = []
    for yso_string in yso_strings:
        # Use only the last path of the keyword string
        # e.g. https://api.hel.fi/linkedevents/v1/keyword/yso:p1235/?format=json -> yso:p1235
        parsed = urlparse(yso_string)
        ysos.append(parsed.path.strip('/').split('/')[-1])

    if not divisions and not ysos:
        raise NotFound()

    qs = Profile.objects.all().select_related('user')
    if divisions:
        qs = qs.filter(divisions_of_interest__ocd_id__in=divisions)

    if ysos:
        prefix_code_map = defaultdict(list)
        for yso_param in ysos:
            try:
                (prefix, code) = yso_param.split(':')
                prefix_code_map[prefix].append(code)
            except ValueError:
                pass

        q = Q()
        for prefix, codes in prefix_code_map.items():
            q |= Q(concepts_of_interest__code__in=codes, concepts_of_interest__vocabulary__prefix=prefix)

        qs = qs.filter(q)

    user_uuids = [p.user.uuid for p in qs]

    return Response(user_uuids)


@api_view(['GET', 'POST'])
@authentication_classes((SessionAuthentication, BasicAuthentication))
@permission_classes((IsAuthenticated,))
def contact_info(request):
    if request.method == 'POST':
        ids = request.POST.getlist('ids', [])
    else:
        ids_param = request.query_params.get('ids', '').strip()
        ids = [i.strip() for i in ids_param.split(',')] if ids_param else None

    if not ids:
        raise NotFound()

    users = get_user_model().objects.filter(uuid__in=ids)

    data = {}
    for user in users:
        try:
            profile = user.profile

            data[str(user.uuid)] = {
                "email": profile.email if profile else None,
                "pushbullet": profile.pushbullet_access_token,
                "phone": profile.phone,
                "language": profile.language,
                "contact_method": profile.contact_method,
            }
        except Profile.DoesNotExist:
            data[str(user.uuid)] = {
                "email": None,
                "pushbullet": None,
                "phone": None,
                "language": None,
                "contact_method": None,
            }

    return Response(data)

#router = routers.DefaultRouter()
#router.register(r'users', UserViewSet)
