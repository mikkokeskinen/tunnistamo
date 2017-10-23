from collections import defaultdict
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import Http404
from django.utils.translation import ugettext_lazy as _
from munigeo.models import AdministrativeDivision
from oidc_provider.lib.errors import BearerTokenError
from oidc_provider.lib.utils.oauth2 import extract_access_token
from oidc_provider.models import Token
from rest_framework import serializers, generics, permissions
from rest_framework.authentication import SessionAuthentication, BasicAuthentication, BaseAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import NotFound, AuthenticationFailed
from rest_framework.permissions import IsAuthenticated
from rest_framework.relations import RelatedField
from rest_framework.renderers import BrowsableAPIRenderer, JSONRenderer
from rest_framework.response import Response
from thesaurus.models import Concept

from tunnistamo.api import logger
from users.models import Profile


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

    user_uuids = {p.user.uuid for p in qs}

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
                "firebase": profile.firebase_token,
                "phone": profile.phone,
                "language": profile.language,
                "contact_method": profile.contact_method,
            }
        except Profile.DoesNotExist:
            data[str(user.uuid)] = {
                "email": None,
                "pushbullet": None,
                "firebase": None,
                "phone": None,
                "language": None,
                "contact_method": None,
            }

    return Response(data)


class BrowsableAPIRendererWithoutHtmlForm(BrowsableAPIRenderer):
    def get_rendered_html_form(self, data, view, method, request):
        """Prevent html form from showing because the concepts select would be too large."""
        return ""


class DivisionRelatedField(RelatedField):
    default_error_messages = {
        'required': _('This field is required.'),
        'does_not_exist': _('Invalid ocd_id "{value}" - object does not exist.'),
        'incorrect_type': _('Incorrect type. Expected ocd_id string, received {data_type}.'),
    }
    queryset = AdministrativeDivision.objects.all()

    def to_representation(self, value):
        return value.ocd_id

    def to_internal_value(self, data):
        try:
            return AdministrativeDivision.objects.get(ocd_id=data)
        except AdministrativeDivision.DoesNotExist:
            self.fail('does_not_exist', value=data)
        except (TypeError, ValueError):
            self.fail('incorrect_type', data_type=type(data).__name__)


class ConceptRelatedField(RelatedField):
    default_error_messages = {
        'required': _('This field is required.'),
        'does_not_exist': _('Invalid prefix and/or code in "{value}" - object does not exist.'),
        'incorrect_type': _('Incorrect type. Expected concept string in format "prefix:code", received {data_type}.'),
    }
    queryset = Concept.objects.all()

    def to_representation(self, value):
        return '{}:{}'.format(value.vocabulary.prefix, value.code)

    def to_internal_value(self, data):
        try:
            (prefix, code) = data.split(':')

            return Concept.objects.get(vocabulary__prefix=prefix, code=code)
        except Concept.DoesNotExist:
            self.fail('does_not_exist', value=data)
        except (TypeError, ValueError):
            self.fail('incorrect_type', data_type=type(data).__name__)


class ProfileSerializer(serializers.ModelSerializer):
    divisions_of_interest = DivisionRelatedField(many=True)
    concepts_of_interest = ConceptRelatedField(many=True)

    class Meta:
        exclude = ['id', 'user']
        model = Profile


class OidcTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        access_token = extract_access_token(request)
        scopes = ['openid']

        try:
            try:
                token = Token.objects.get(access_token=access_token)
            except Token.DoesNotExist:
                logger.debug('[UserInfo] Token does not exist: %s', access_token)
                raise BearerTokenError('invalid_token')

            if token.has_expired():
                logger.debug('[UserInfo] Token has expired: %s', access_token)
                raise BearerTokenError('invalid_token')

            if not set(scopes).issubset(set(token.scope)):
                logger.debug('[UserInfo] Missing openid scope.')
                raise BearerTokenError('insufficient_scope')
        except BearerTokenError as error:
            raise AuthenticationFailed(error.description)

        return (token.user, token)

    def authenticate_header(self, request):
        return "Bearer"


class OwnProfileView(generics.RetrieveUpdateAPIView):
    authentication_classes = [SessionAuthentication, BasicAuthentication, OidcTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    queryset = Profile.objects.all()
    serializer_class = ProfileSerializer
    renderer_classes = [JSONRenderer, BrowsableAPIRendererWithoutHtmlForm]

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def get_object(self):
        try:
            profile = self.get_queryset().get(user=self.request.user)
        except Profile.DoesNotExist:
            # TODO: create profile when the user is created, not here.
            profile = Profile.objects.create(user=self.request.user)
        except (TypeError, ValueError):
            raise Http404

        return profile

