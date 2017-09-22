import logging
import jwt
import datetime

from django.contrib.auth import get_user_model
from django.http import Http404
from rest_framework import permissions, serializers, generics, mixins, views
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


class InterestedView(views.APIView):
    def get(self, request):
        division = request.query_params.get('division', '').strip()
        yso = request.query_params.get('yso', '').strip()

        if not division and not yso:
            raise NotFound()

        divisions = [i.strip() for i in division.split(',')] if division else None
        ysos = [i.strip() for i in yso.split(',')] if yso else None

        qs = Profile.objects.all()
        if divisions:
            qs = qs.filter(divisions_of_interest__ocd_id__in=divisions)

        if ysos:
            qs = qs.filter(ysos_of_interest__yso_id__in=ysos)

        user_uuids = [p.user.uuid for p in qs]

        return Response(user_uuids)


class ContactInfoView(views.APIView):
    def get(self, request):
        ids_param = request.query_params.get('ids', '').strip()
        ids = [i.strip() for i in ids_param.split(',')] if ids_param else None

        users = get_user_model().objects.filter(uuid__in=ids)

        data = {}
        for user in users:
            profile = None
            try:
                profile = user.profile

                data[str(user.uuid)] = {
                    "email": profile.email if profile else None,
                    "phone": profile.phone,
                    "language": profile.language,
                    "contact_method": profile.contact_method,
                }
            except Profile.DoesNotExist:
                data[str(user.uuid)] = {
                    "email": None,
                    "phone": None,
                    "language": None,
                    "contact_method": None,
                }

        return Response(data)

#router = routers.DefaultRouter()
#router.register(r'users', UserViewSet)
